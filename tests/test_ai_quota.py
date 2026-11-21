"""Daily AI request/token quotas: service behaviour, concurrency and route integration."""

import threading
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.routes.ai as ai_routes
from src.ai import usage as ai_usage
from src.api.main import app
from src.auth.dependencies import get_current_user
from src.config.settings import settings
from src.database.base import Base
from src.database.session import get_db
from src.models import AiUsageDaily, Chat, User
from src.services import ai_quota_service as quota


def seed_users(engine, count=25):
    """reserve() refuses accounts that do not exist (deletion safety), so the quota tests that
    use fixed ids 1..N need real rows for them."""
    with Session(bind=engine) as s:
        s.add_all(User(id=i, username=f"quota{i}", email=f"quota{i}@example.com", hashed_password="x") for i in range(1, count + 1))
        s.commit()


def usage_row(db, scope):
    db.expire_all()
    return db.scalars(select(AiUsageDaily).where(AiUsageDaily.scope == scope)).first()


def counters(db, scope):
    row = usage_row(db, scope)
    return (row.requests, row.tokens) if row else (0, 0)


@pytest.fixture
def file_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(bind=engine)
    seed_users(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(file_engine):
    session = Session(bind=file_engine)
    yield session
    session.close()


@pytest.fixture
def limits(monkeypatch):
    def apply(per_user=10, global_requests=1000, global_tokens=10_000_000):
        monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_PER_USER", per_user)
        monkeypatch.setattr(settings, "AI_DAILY_REQUESTS_GLOBAL", global_requests)
        monkeypatch.setattr(settings, "AI_DAILY_TOKENS_GLOBAL", global_tokens)

    return apply


# ------------------------------------------------------------------- service
def test_reserve_counts_request_and_tokens_for_user_and_global(db, limits):
    limits()
    quota.reserve(db, 1, 500)
    assert counters(db, "user:1") == (1, 500)
    assert counters(db, quota.GLOBAL_SCOPE) == (1, 500)


def test_request_quota_per_user_is_enforced(db, limits):
    limits(per_user=2)
    quota.reserve(db, 1, 100)
    quota.reserve(db, 1, 100)
    with pytest.raises(quota.QuotaExceeded) as exc:
        quota.reserve(db, 1, 100)
    assert exc.value.scope == "user"
    assert 1 <= exc.value.retry_after <= 86400
    assert counters(db, "user:1") == (2, 200)  # the rejected attempt left no trace
    assert counters(db, quota.GLOBAL_SCOPE) == (2, 200)


def test_quota_is_isolated_per_user(db, limits):
    limits(per_user=1)
    quota.reserve(db, 1, 100)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, 1, 100)
    quota.reserve(db, 2, 100)  # another user is unaffected
    assert counters(db, "user:2") == (1, 100)
    assert counters(db, quota.GLOBAL_SCOPE)[0] == 2


def test_global_request_quota_is_shared_and_rolls_back_the_user_increment(db, limits):
    limits(global_requests=2)
    quota.reserve(db, 1, 100)
    quota.reserve(db, 2, 100)
    with pytest.raises(quota.QuotaExceeded) as exc:
        quota.reserve(db, 3, 100)
    assert exc.value.scope == "global"
    assert counters(db, "user:3") == (0, 0)  # user row increment undone with the failed admission


def test_global_token_quota_is_enforced_against_the_reservation(db, limits):
    limits(global_tokens=10_000)
    quota.reserve(db, 1, 6_000)
    with pytest.raises(quota.QuotaExceeded) as exc:
        quota.reserve(db, 2, 6_000)
    assert exc.value.scope == "global"
    assert counters(db, "user:2") == (0, 0)
    quota.reserve(db, 2, 4_000)  # exactly fills the budget


def test_settle_replaces_reservation_with_measured_tokens(db, limits):
    limits()
    low = quota.reserve(db, 1, 6_500)
    quota.settle(db, low, 1_200)
    assert counters(db, "user:1") == (1, 1_200)
    high = quota.reserve(db, 2, 1_000)
    quota.settle(db, high, 3_000)  # tool rounds can exceed the reservation
    assert counters(db, "user:2") == (1, 3_000)
    assert counters(db, quota.GLOBAL_SCOPE) == (2, 4_200)


def test_release_refunds_a_failed_request_and_is_idempotent(db, limits):
    limits(per_user=1)
    reservation = quota.reserve(db, 1, 5_000)
    quota.release(db, reservation)
    quota.release(db, reservation)
    quota.settle(db, reservation, 999)  # a finished reservation ignores later calls
    assert counters(db, "user:1") == (0, 0)
    assert counters(db, quota.GLOBAL_SCOPE) == (0, 0)
    quota.reserve(db, 1, 100)  # the refund freed the user's only request


def test_counters_reset_on_the_next_utc_day(db, limits, monkeypatch):
    limits(per_user=1)
    monkeypatch.setattr(quota, "utc_today", lambda: date(2026, 11, 18))
    quota.reserve(db, 1, 100)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, 1, 100)
    monkeypatch.setattr(quota, "utc_today", lambda: date(2026, 11, 19))
    quota.reserve(db, 1, 100)


def test_measured_tokens_prefers_provider_usage_over_the_estimate():
    assert quota.measured_tokens({"provider_tokens": 321, "prompt_chars": 4000}, 4000) == 321
    assert quota.measured_tokens({"prompt_chars": 400}, 400) == 200  # (400 + 400) / 4
    assert quota.measured_tokens({"provider_tokens": 0, "prompt_chars": 40}, 40) == 20
    assert quota.measured_tokens({}, 0) == 0


# --------------------------------------------------------------- concurrency
def run_threads(file_engine, user_ids):
    outcomes, lock, barrier = [], threading.Lock(), threading.Barrier(len(user_ids))

    def worker(user_id):
        session = Session(bind=file_engine)
        try:
            barrier.wait()
            try:
                quota.reserve(session, user_id, 100)
                result = "ok"
            except quota.QuotaExceeded as exc:
                result = exc.scope
            with lock:
                outcomes.append(result)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(uid,)) for uid in user_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return outcomes


def test_concurrent_requests_cannot_exceed_the_per_user_quota(file_engine, db, limits):
    limits(per_user=5)
    outcomes = run_threads(file_engine, [1] * 20)
    assert outcomes.count("ok") == 5
    assert outcomes.count("user") == 15
    assert counters(db, "user:1")[0] == 5


def test_concurrent_requests_cannot_exceed_the_global_quota(file_engine, db, limits):
    limits(global_requests=4)
    outcomes = run_threads(file_engine, list(range(1, 13)))
    assert outcomes.count("ok") == 4
    assert outcomes.count("global") == 8
    assert counters(db, quota.GLOBAL_SCOPE)[0] == 4


# ------------------------------------------------------------ route integration
@pytest.fixture
def api(tmp_path, monkeypatch, limits):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False, "timeout": 30})
    Session_ = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    seed = Session_()
    users = [User(username=f"user{i}", email=f"user{i}@example.com", hashed_password="x") for i in (1, 2)]
    seed.add_all(users)
    seed.commit()
    ids = [u.id for u in users]
    seed.close()

    state = {"user_id": ids[0]}

    def override_get_db():
        session = Session_()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = Session_()
        try:
            return session.get(User, state["user_id"])
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    limits()
    helper = SimpleNamespace(client=TestClient(app, raise_server_exceptions=False), Session=Session_, ids=ids, state=state)
    try:
        yield helper
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def reads(api, scope):
    with api.Session() as s:
        return counters(s, scope)


def stub_chat(monkeypatch, reply="a short reply", calls=None):
    def fake(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return reply

    monkeypatch.setattr(ai_routes, "chat_with_ai", fake)


def stub_stream(monkeypatch, chunks=("Hello ", "world"), finish="stop", fail_after=None, provider_tokens=None, calls=None):
    def fake(outcome=None, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        outcome["prompt_chars"] = 800
        if provider_tokens is not None:
            outcome["provider_tokens"] = provider_tokens
        for i, chunk in enumerate(chunks):
            if fail_after is not None and i == fail_after:
                raise RuntimeError("provider-internal-detail sk-SECRET")
            yield chunk
        outcome["finish_reason"] = finish

    monkeypatch.setattr(ai_routes, "stream_chat_with_ai", fake)


def post_chat(api, path="/ai/chat"):
    return api.client.post(path, json={"message": "hello there"})


def test_chat_counts_one_request_and_estimated_tokens(api, monkeypatch):
    stub_chat(monkeypatch, reply="x" * 400)
    assert post_chat(api).status_code == 200
    requests, tokens = reads(api, f"user:{api.ids[0]}")
    assert requests == 1
    assert tokens == 100  # no provider usage: 400 reply chars / 4, prompt not measured by the stub


def test_chat_uses_provider_reported_usage_when_available(api, monkeypatch):
    def fake(**kwargs):
        ai_usage.note_prompt([{"content": "p" * 4000}])
        ai_usage.note_response(SimpleNamespace(usage=SimpleNamespace(total_tokens=300)))
        ai_usage.note_response(SimpleNamespace(usage=SimpleNamespace(total_tokens=450)))  # a second tool round
        return "ok"

    monkeypatch.setattr(ai_routes, "chat_with_ai", fake)
    assert post_chat(api).status_code == 200
    assert reads(api, f"user:{api.ids[0]}") == (1, 750)


def test_request_quota_returns_429_with_retry_after_and_never_calls_the_provider(api, monkeypatch, limits):
    limits(per_user=2)
    calls = []
    stub_chat(monkeypatch, calls=calls)
    assert post_chat(api).status_code == 200
    assert post_chat(api).status_code == 200
    blocked = post_chat(api)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 86400
    assert "daily AI request limit" in blocked.json()["detail"]
    assert len(calls) == 2


def test_global_token_quota_returns_429(api, monkeypatch, limits):
    limits(global_tokens=quota.reservation_tokens(quota.CHAT_OUTPUT_TOKENS) + 10)
    calls = []
    stub_chat(monkeypatch, reply="r" * 4000, calls=calls)  # settles at 1000 tokens
    assert post_chat(api).status_code == 200
    blocked = post_chat(api)  # 1000 used + new reservation > budget
    assert blocked.status_code == 429
    assert "shared daily AI capacity" in blocked.json()["detail"]
    assert len(calls) == 1


def test_quota_is_per_authenticated_user_through_the_api(api, monkeypatch, limits):
    limits(per_user=1)
    stub_chat(monkeypatch)
    assert post_chat(api).status_code == 200
    assert post_chat(api).status_code == 429
    api.state["user_id"] = api.ids[1]
    assert post_chat(api).status_code == 200
    assert reads(api, quota.GLOBAL_SCOPE)[0] == 2


def test_chat_and_stream_share_the_same_daily_counter(api, monkeypatch, limits):
    limits(per_user=2)
    stub_chat(monkeypatch)
    stub_stream(monkeypatch)
    assert post_chat(api).status_code == 200
    assert post_chat(api, "/ai/chat/stream").status_code == 200
    assert post_chat(api, "/ai/chat/stream").status_code == 429
    assert post_chat(api).status_code == 429


def test_failed_chat_is_refunded_and_leaks_nothing(api, monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("upstream said: key sk-SECRET-VALUE is invalid")

    monkeypatch.setattr(ai_routes, "chat_with_ai", boom)
    with caplog.at_level("INFO"):
        response = post_chat(api)
    assert response.status_code == 502
    assert response.json() == {"detail": "The AI provider could not complete the request. Please try again."}
    assert "sk-SECRET-VALUE" not in response.text + caplog.text
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)
    assert reads(api, quota.GLOBAL_SCOPE) == (0, 0)
    with api.Session() as s:
        assert s.query(Chat).count() == 0


def test_stream_success_counts_and_uses_provider_usage(api, monkeypatch):
    stub_stream(monkeypatch, provider_tokens=640)
    response = post_chat(api, "/ai/chat/stream")
    assert response.status_code == 200 and response.text.endswith("stop")
    assert reads(api, f"user:{api.ids[0]}") == (1, 640)


def test_stream_without_provider_usage_is_estimated_from_prompt_and_output(api, monkeypatch):
    stub_stream(monkeypatch, chunks=("a" * 200, "b" * 200))
    post_chat(api, "/ai/chat/stream")
    assert reads(api, f"user:{api.ids[0]}") == (1, (800 + 400) // 4)


def test_stream_failing_before_any_output_is_refunded(api, monkeypatch):
    stub_stream(monkeypatch, fail_after=0)
    response = post_chat(api, "/ai/chat/stream")
    assert response.status_code == 200 and response.text.endswith("error")
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)


def test_stream_failing_midway_counts_what_was_produced_and_hides_the_error(api, monkeypatch, caplog):
    stub_stream(monkeypatch, chunks=("partial answer ", "never sent"), fail_after=1)
    with caplog.at_level("INFO"):
        response = post_chat(api, "/ai/chat/stream")
    assert "partial answer" in response.text
    assert "sk-SECRET" not in response.text + caplog.text and "provider-internal-detail" not in response.text + caplog.text
    requests, tokens = reads(api, f"user:{api.ids[0]}")
    assert requests == 1 and tokens > 0


def test_ai_per_minute_limit_is_enforced_per_user(api, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AI_PER_MINUTE", 2)
    stub_chat(monkeypatch)
    assert post_chat(api).status_code == 200
    assert post_chat(api).status_code == 200
    blocked = post_chat(api)
    assert blocked.status_code == 429 and 1 <= int(blocked.headers["Retry-After"]) <= 60
    api.state["user_id"] = api.ids[1]
    assert post_chat(api).status_code == 200


# ------------------------------------------------- settlement failure and retry safety
class _FailCommit:
    """Make the next N commits on a session raise, then behave normally."""

    def __init__(self, session, times):
        self.session, self.times, self._real = session, times, session.commit
        session.commit = self

    def __call__(self):
        if self.times > 0:
            self.times -= 1
            raise RuntimeError("db down password=hunter2")
        return self._real()


def test_failed_settle_commit_keeps_the_reservation_counted_and_retryable(db, limits, caplog):
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    _FailCommit(db, 1)
    with caplog.at_level("ERROR", logger="AIEngineeringLab.quota"):
        assert quota.settle(db, reservation, 800) is quota.Settlement.FAILED
    assert reservation.finished is False
    assert counters(db, "user:1") == (1, 5_000)  # still reserved: no bypass
    assert "RuntimeError" in caplog.text and "hunter2" not in caplog.text and "user:1" not in caplog.text
    assert quota.settle(db, reservation, 800) is quota.Settlement.APPLIED  # retry succeeds
    assert counters(db, "user:1") == (1, 800)
    assert reservation.finished is True


def test_failed_release_commit_is_retryable_and_never_double_refunds(db, limits):
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    _FailCommit(db, 1)
    assert quota.release(db, reservation) is quota.Settlement.FAILED
    assert counters(db, "user:1") == (1, 5_000)
    assert quota.release(db, reservation) is quota.Settlement.APPLIED
    assert quota.release(db, reservation) is quota.Settlement.ALREADY_FINISHED  # no second refund
    assert counters(db, "user:1") == (0, 0)
    assert counters(db, quota.GLOBAL_SCOPE) == (0, 0)


def test_settle_after_release_and_release_after_settle_are_ignored(db, limits):
    limits()
    a = quota.reserve(db, 1, 5_000)
    quota.settle(db, a, 700)
    quota.release(db, a)
    assert counters(db, "user:1") == (1, 700)
    b = quota.reserve(db, 2, 5_000)
    quota.release(db, b)
    quota.settle(db, b, 700)
    assert counters(db, "user:2") == (0, 0)


def test_concurrent_settle_calls_apply_exactly_once(file_engine, limits):
    limits()
    setup = Session(bind=file_engine)
    reservation = quota.reserve(setup, 1, 5_000)
    barrier = threading.Barrier(8)

    def worker():
        s = Session(bind=file_engine)
        try:
            barrier.wait()
            quota.settle(s, reservation, 900)
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert counters(setup, "user:1") == (1, 900)  # one delta applied, not eight
    setup.close()


def test_settlement_may_exceed_the_reservation_and_logs_a_warning(db, limits, caplog):
    limits(global_tokens=10_000)
    reservation = quota.reserve(db, 1, 5_000)
    with caplog.at_level("WARNING", logger="AIEngineeringLab.quota"):
        quota.settle(db, reservation, 12_000)
    assert counters(db, quota.GLOBAL_SCOPE) == (1, 12_000)  # documented: not a strict hard cap
    assert "exceeded its reservation by 7000" in caplog.text


def test_repeated_settle_with_a_huge_value_changes_nothing_and_does_not_warn(db, limits, caplog):
    """Regression: a no-op repeat used to log an overshoot warning for the ignored value."""
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    with caplog.at_level("WARNING", logger="AIEngineeringLab.quota"):
        assert quota.settle(db, reservation, 800) is quota.Settlement.APPLIED
        assert caplog.text == ""  # 800 < 5,000 reserved: no overshoot, no warning
        assert quota.settle(db, reservation, 99_999) is quota.Settlement.ALREADY_FINISHED
        assert quota.settle(db, reservation, 10_000_000) is quota.Settlement.ALREADY_FINISHED
    assert "exceeded" not in caplog.text and caplog.text == ""
    assert counters(db, "user:1") == (1, 800)
    assert counters(db, quota.GLOBAL_SCOPE) == (1, 800)


def test_overshoot_warning_is_logged_once_when_the_settlement_is_applied(db, limits, caplog):
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    with caplog.at_level("WARNING", logger="AIEngineeringLab.quota"):
        assert quota.settle(db, reservation, 12_000) is quota.Settlement.APPLIED
        assert quota.settle(db, reservation, 50_000) is quota.Settlement.ALREADY_FINISHED
    assert caplog.text.count("exceeded its reservation") == 1
    assert "by 7000 tokens" in caplog.text
    assert counters(db, "user:1") == (1, 12_000)


def test_failed_settle_does_not_warn_and_the_retry_warns_exactly_once(db, limits, caplog):
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    _FailCommit(db, 1)
    with caplog.at_level("WARNING", logger="AIEngineeringLab.quota"):
        assert quota.settle(db, reservation, 9_000) is quota.Settlement.FAILED
        assert "exceeded" not in caplog.text
        assert quota.settle(db, reservation, 9_000) is quota.Settlement.APPLIED
    assert caplog.text.count("exceeded its reservation") == 1


def test_settlement_result_values_are_distinct():
    assert len({quota.Settlement.APPLIED, quota.Settlement.ALREADY_FINISHED, quota.Settlement.FAILED}) == 3


def test_a_lost_commit_acknowledgement_is_documented_as_not_exactly_once(db, limits):
    """The commit succeeds on the server but the call raises: the outcome is ambiguous.
    This test pins the documented limitation (a retry applies the change a second time);
    it must be updated together with the docs if durable idempotency is ever added."""
    limits()
    reservation = quota.reserve(db, 1, 5_000)
    real_commit = db.commit

    def commit_then_lose_the_ack():
        real_commit()
        raise RuntimeError("connection reset after COMMIT")

    db.commit = commit_then_lose_the_ack
    assert quota.release(db, reservation) is quota.Settlement.FAILED  # looks failed, but was committed
    assert counters(db, "user:1") == (0, 0)
    db.commit = real_commit
    assert quota.release(db, reservation) is quota.Settlement.APPLIED  # retry refunds again
    assert counters(db, "user:1") == (-1, -5_000)  # double refund: the documented ambiguity


# ------------------------------------------- real provider failure shapes (SDK level)
# Unlike the stubs above these run the real stream parser in ai_service against a fake
# Groq client, so they cover what the SDK actually raises or sends.
def _groq_error(cls, status, message="upstream says key gsk_SECRET_KEY_VALUE is bad"):
    import httpx

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls(message, response=httpx.Response(status, request=request), body={"error": {"message": message}})


def _fake_provider(monkeypatch, create):
    from src.services import ai_service

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(ai_service, "get_ai_client", lambda: client)


def _chunk(content=None, finish=None, reasoning=None):
    delta = SimpleNamespace(content=content, reasoning=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=None, x_groq=None)


@pytest.mark.parametrize("status,name", [(401, "AuthenticationError"), (429, "RateLimitError"), (500, "InternalServerError"), (503, "InternalServerError")])
def test_sdk_http_errors_on_chat_are_refunded_generic_and_secret_free(api, monkeypatch, caplog, status, name):
    import groq

    def create(**kwargs):
        raise _groq_error(getattr(groq, name), status)

    _fake_provider(monkeypatch, create)
    with caplog.at_level("INFO"):
        response = post_chat(api)
    assert response.status_code == 502
    assert response.json() == {"detail": "The AI provider could not complete the request. Please try again."}
    assert "gsk_SECRET_KEY_VALUE" not in response.text + caplog.text
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)
    assert reads(api, quota.GLOBAL_SCOPE) == (0, 0)


def test_sdk_connection_error_and_timeout_on_chat_are_refunded(api, monkeypatch):
    import groq
    import httpx

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    for exc in (groq.APIConnectionError(request=request), groq.APITimeoutError(request=request)):
        def create(**kwargs):
            raise exc

        _fake_provider(monkeypatch, create)
        assert post_chat(api).status_code == 502
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)


def test_stream_provider_401_ends_with_error_marker_and_is_refunded(api, monkeypatch, caplog):
    import groq

    def create(**kwargs):
        raise _groq_error(groq.AuthenticationError, 401)

    _fake_provider(monkeypatch, create)
    with caplog.at_level("INFO"):
        response = post_chat(api, "/ai/chat/stream")
    assert response.status_code == 200 and response.text.endswith("error")
    assert "gsk_SECRET_KEY_VALUE" not in response.text + caplog.text
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)
    with api.Session() as s:
        assert s.query(Chat).count() == 0


def test_reasoning_only_stream_cut_by_max_tokens_is_empty_length_refunded_and_not_saved(api, monkeypatch):
    """A reasoning model can spend the whole output budget thinking. The stream then has
    no visible content and finish_reason 'length': the client must see 'length', the
    request must not be charged, and no empty answer may be saved to history."""
    def create(**kwargs):
        return iter([_chunk(reasoning="thinking..."), _chunk(reasoning="more thinking"), _chunk(finish="length")])

    _fake_provider(monkeypatch, create)
    response = post_chat(api, "/ai/chat/stream")
    assert response.status_code == 200 and response.text.endswith("length")
    assert response.text.replace("\x1eLATZ-STREAM-END:length", "").strip() == ""
    assert reads(api, f"user:{api.ids[0]}") == (0, 0)
    with api.Session() as s:
        assert s.query(Chat).count() == 0


def test_stream_that_never_sends_finish_reason_is_incomplete_but_keeps_its_text(api, monkeypatch):
    def create(**kwargs):
        return iter([_chunk(content="partial "), _chunk(content="text")])

    _fake_provider(monkeypatch, create)
    response = post_chat(api, "/ai/chat/stream")
    assert response.text.startswith("partial text") and response.text.endswith("incomplete")
    requests, tokens = reads(api, f"user:{api.ids[0]}")
    assert requests == 1 and tokens > 0


def test_daily_cap_is_a_hard_stop_through_the_api_and_the_provider_is_not_called_past_it(api, monkeypatch, limits):
    """API-level companion to the thread-level quota tests above: the cap is a
    hard stop on the Nth+1 request and the provider is never called for it."""
    limits(per_user=3)
    calls = []
    stub_chat(monkeypatch, calls=calls)
    codes = [post_chat(api).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429] and len(calls) == 3
