import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from src.api.feature_flags import require_ai_enabled
from src.ai.usage import collect_usage
from src.auth.dependencies import get_current_user
from src.config.settings import settings
from src.database.session import get_db
from src.models.conversation import Conversation
from src.models.user import User
from src.schemas.ai import ChatRequest, ChatResponse
from src.schemas.chat import ChatHistory
from src.schemas.memory_candidate import (
    MemoryCandidateRequest,
    MemoryCandidateResponse,
    MemoryConfirmRequest,
    MemoryConfirmResponse,
)
from src.security.rate_limit import limit_ai_for_user
from src.security.stream_limiter import stream_limiter
from src.services import ai_quota_service as quota
from src.services.ai_service import MAX_OUTPUT_TOKENS, chat_with_ai, stream_chat_with_ai
from src.services.chat_service import save_chat, get_chat_history, get_recent_chats
from src.services.context_service import get_user_context
from src.services.memory_extraction_service import detect_memory_candidate
from src.services.memory_service import get_memories, create_memory, find_duplicate_memory
from src.services.project_service import get_project

router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


def describe_error(exc: Exception) -> str:
    """Log-safe description of a provider error: the class and HTTP status only.
    Provider error text can echo request details, so it is never logged."""
    status = getattr(exc, "status_code", None)
    return type(exc).__name__ + (f", status {status}" if isinstance(status, int) else "")


def build_request_context(db: Session, user: User, project_id: int | None):
    context = get_user_context(db=db, user=user)
    if project_id is None:
        context["current_project"] = None
        return context
    project = get_project(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    context["current_project"] = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "engine": project.engine,
        "tech_stack": project.tech_stack,
    }
    return context


def validate_conversation(db: Session, user: User, conversation_id: int | None, project_id: int | None):
    if conversation_id is None:
        return None
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user.id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if project_id is not None and conversation.project_id != project_id:
        raise HTTPException(status_code=400, detail="Conversation does not belong to the selected project")
    return conversation


@router.post("/memory-candidate", response_model=MemoryCandidateResponse)
def memory_candidate(request: MemoryCandidateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidate = detect_memory_candidate(request.message)
    if candidate is None:
        return MemoryCandidateResponse(candidate=None, duplicate=False)
    duplicate = find_duplicate_memory(db=db, user=current_user, memory_type=candidate["memory_type"], content=candidate["content"])
    return MemoryCandidateResponse(candidate=candidate, duplicate=duplicate is not None)


@router.post("/memory-confirm", response_model=MemoryConfirmResponse)
def memory_confirm(request: MemoryConfirmRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    duplicate = find_duplicate_memory(db=db, user=current_user, memory_type=request.memory_type, content=request.content)
    if duplicate is not None:
        return MemoryConfirmResponse(saved=False, duplicate=True, message="This memory is already saved.")
    create_memory(db=db, user=current_user, memory_type=request.memory_type, content=request.content)
    return MemoryConfirmResponse(saved=True, duplicate=False, message="Memory saved successfully.")


def reserve_quota_or_429(db: Session, user_id: int, tokens: int) -> quota.QuotaReservation:
    """Admit the request against the daily quotas, or raise HTTP 429 with Retry-After."""
    try:
        return quota.reserve(db, user_id, tokens)
    except quota.QuotaExceeded as exc:
        logger.info("AI daily quota exhausted scope=%s user_id=%s", exc.scope, user_id)
        raise HTTPException(status_code=429, detail=exc.detail, headers={"Retry-After": str(exc.retry_after)})


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_ai_enabled)])
def chat(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    limit_ai_for_user(user_id)
    conversation = validate_conversation(db, current_user, request.conversation_id, request.project_id)
    effective_project_id = request.project_id if conversation is None else conversation.project_id
    history = get_recent_chats(db=db, user=current_user, project_id=effective_project_id, conversation_id=request.conversation_id)
    memories = get_memories(db=db, user=current_user)
    context = build_request_context(db=db, user=current_user, project_id=effective_project_id)

    reservation = reserve_quota_or_429(db, user_id, quota.reservation_tokens(quota.CHAT_OUTPUT_TOKENS))
    try:
        with collect_usage() as usage:
            response = chat_with_ai(message=request.message, history=history, memories=memories, context=context, engine=request.engine, action=request.action)
    except Exception as exc:
        # A failed call is not counted as consumption. Only the exception class is
        # logged: provider error text can echo request details.
        quota.release(db, reservation)
        logger.error("AI chat failed (%s)", describe_error(exc))
        raise HTTPException(status_code=502, detail="The AI provider could not complete the request. Please try again.")
    quota.settle(db, reservation, quota.measured_tokens(usage, len(response or "")))
    save_chat(db=db, user=current_user, user_message=request.message, ai_response=response, project_id=effective_project_id, conversation_id=request.conversation_id)
    return ChatResponse(response=response)

# The stream body is plain text, so completion is signalled in-band: the last
# thing sent is STREAM_END_MARKER + one of stop | length | error | incomplete. Only an explicit
# provider finish_reason of "stop" yields "stop". A stream
# without it was cut off (network/server) and must be treated as incomplete.
STREAM_END_MARKER = "\x1eLATZ-STREAM-END:"
INCOMPLETE_NOTES = {
    "length": "\n\n_[Response incomplete: the model reached its output length limit.]_",
    "error": "\n\n_[Response incomplete: generation was interrupted.]_",
    "incomplete": "\n\n_[Response may be incomplete: the model did not confirm it finished.]_",
    "timeout": "\n\n_[Response incomplete: the stream exceeded its time limit.]_",
}


STREAM_BUSY_RETRY_AFTER_SECONDS = 5


def generate_stream(db: Session, user: User, request: ChatRequest, project_id: int | None, history, memories, context, slot, reservation):
    """Body of /ai/chat/stream. Whatever ends it (success, provider error, client
    disconnect or cancellation) the stream slot is released and the quota
    reservation is settled (output produced) or refunded (no output)."""
    chunks = []    # delivered: yielded to the response stream and accepted; this is the saved history
    produced = []  # generated by the provider, delivered or not; quota is settled on this (it cost tokens)
    outcome = {}
    status = "incomplete"

    def account():
        # settle()/release() are idempotent and only mark the reservation finished after a
        # successful commit, so calling this again (finally) retries a failed commit.
        if reservation.finished:
            return
        text = "".join(produced)
        if text.strip():
            quota.settle(db, reservation, quota.measured_tokens(outcome, len(text)))
        else:
            quota.release(db, reservation)

    try:
        try:
            try:
                for chunk in stream_chat_with_ai(message=request.message, history=history, memories=memories, context=context, engine=request.engine, action=request.action, outcome=outcome):
                    produced.append(chunk)
                    if not slot.renew():
                        # Lease lost or maximum duration exceeded: stop so the concurrency cap holds.
                        # This chunk is not delivered, so it must not reach the saved history.
                        status = "timeout"
                        break
                    yield chunk
                    chunks.append(chunk)  # only after the consumer took it and asked for more
                if status != "timeout":
                    # Fail-safe: only an explicit finish_reason of "stop" counts as complete.
                    reason = outcome.get("finish_reason")
                    status = reason if reason in ("stop", "length") else "incomplete"
            except Exception as exc:
                # Provider failure mid-stream: keep what arrived, report it in-band.
                # Only the class name is logged; provider messages can echo request details.
                logger.error("AI stream failed (%s)", describe_error(exc))
                status = "error"
            response_text = "".join(chunks)
            if status != "stop" and response_text.strip():
                response_text += INCOMPLETE_NOTES[status]
            if response_text.strip():
                save_chat(db=db, user=user, user_message=request.message, ai_response=response_text, project_id=project_id, conversation_id=request.conversation_id)
            account()
            yield f"{STREAM_END_MARKER}{status}"
        except Exception:
            db.rollback()
            raise
    finally:
        account()  # no-op after normal completion; covers disconnect and cancellation
        slot.release()
        db.close()


@router.post("/chat/stream", dependencies=[Depends(require_ai_enabled)])
def stream_chat(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    limit_ai_for_user(user_id)
    conversation = validate_conversation(db, current_user, request.conversation_id, request.project_id)
    effective_project_id = request.project_id if conversation is None else conversation.project_id
    history = get_recent_chats(db=db, user=current_user, project_id=effective_project_id, conversation_id=request.conversation_id)
    memories = get_memories(db=db, user=current_user)
    context = build_request_context(db=db, user=current_user, project_id=effective_project_id)

    slot = stream_limiter.acquire(settings.AI_MAX_CONCURRENT_STREAMS)
    if slot is None:
        raise HTTPException(
            status_code=429,
            detail="Too many AI responses are in progress. Please try again in a few seconds.",
            headers={"Retry-After": str(STREAM_BUSY_RETRY_AFTER_SECONDS)},
        )
    reservation = None
    try:
        reservation = reserve_quota_or_429(db, user_id, quota.reservation_tokens(MAX_OUTPUT_TOKENS))
        body = generate_stream(db, current_user, request, effective_project_id, history, memories, context, slot, reservation)
        # slot.release is idempotent. As a second safety net it also runs when the
        # response finishes even if the body generator never started; the slot lease
        # in StreamLimiter is the last resort.
        return StreamingResponse(body, media_type="text/plain; charset=utf-8", background=BackgroundTask(slot.release))
    except BaseException:
        slot.release()
        if reservation is not None:
            quota.release(db, reservation)
        raise


@router.get("/history", response_model=list[ChatHistory])
def history(project_id: int | None = None, conversation_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if project_id is not None:
        project = get_project(db=db, user=current_user, project_id=project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    validate_conversation(db, current_user, conversation_id, project_id)
    return get_chat_history(db=db, user=current_user, project_id=project_id, conversation_id=conversation_id)
