from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services import ai_service


def test_chat_with_ai_returns_provider_response(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Mocked LATZ response")
            )
        ]
    )

    monkeypatch.setattr(ai_service, "get_ai_client", lambda: fake_client)
    orchestrator_calls = []

    def fake_orchestrator(client, messages):
        orchestrator_calls.append((client, messages))
        return "Mocked LATZ response"

    monkeypatch.setattr(ai_service, "run_tool_calling", fake_orchestrator)
    monkeypatch.setattr(
        ai_service,
        "get_relevant_context",
        lambda **kwargs: {"memories": [], "life_roles": [], "goals": []},
    )
    monkeypatch.setattr(
        ai_service,
        "build_messages",
        lambda **kwargs: [{"role": "user", "content": "Hello"}],
    )

    result = ai_service.chat_with_ai(message="Hello")

    assert result == "Mocked LATZ response"
    assert len(orchestrator_calls) == 1
    assert orchestrator_calls[0][0] is fake_client
    assert orchestrator_calls[0][1] == [{"role": "user", "content": "Hello"}]
    fake_client.chat.completions.create.assert_not_called()


def test_stream_chat_with_ai_yields_text_chunks(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Hello ")
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="from LATZ")
                )
            ]
        ),
    ]

    monkeypatch.setattr(ai_service, "get_ai_client", lambda: fake_client)
    monkeypatch.setattr(
        ai_service,
        "get_relevant_context",
        lambda **kwargs: {"memories": [], "life_roles": [], "goals": []},
    )
    monkeypatch.setattr(
        ai_service,
        "build_messages",
        lambda **kwargs: [{"role": "user", "content": "Hello"}],
    )

    result = list(ai_service.stream_chat_with_ai(message="Hello"))

    assert result == ["Hello ", "from LATZ"]
    fake_client.chat.completions.create.assert_called_once()
    assert fake_client.chat.completions.create.call_args.kwargs["stream"] is True


def _chunk(content=None, finish_reason=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=finish_reason)]
    )


def _stream_with(monkeypatch, chunks):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = chunks
    monkeypatch.setattr(ai_service, "get_ai_client", lambda: fake_client)
    monkeypatch.setattr(
        ai_service, "get_relevant_context",
        lambda **kwargs: {"memories": [], "life_roles": [], "goals": []},
    )
    monkeypatch.setattr(ai_service, "build_messages", lambda **kwargs: [{"role": "user", "content": "Hi"}])
    return fake_client


def test_stream_chat_with_ai_reports_length_finish_reason(monkeypatch):
    _stream_with(monkeypatch, [_chunk("Section 6: Integration of "), _chunk(None, "length")])
    outcome = {}

    result = list(ai_service.stream_chat_with_ai(message="Hi", outcome=outcome))

    assert result == ["Section 6: Integration of "]
    assert outcome["finish_reason"] == "length"


def test_stream_chat_with_ai_reports_stop_finish_reason(monkeypatch):
    _stream_with(monkeypatch, [_chunk("Done."), _chunk(None, "stop")])
    outcome = {}

    list(ai_service.stream_chat_with_ai(message="Hi", outcome=outcome))

    assert outcome["finish_reason"] == "stop"


def test_output_token_limit_fits_a_seven_section_report():
    assert ai_service.MAX_OUTPUT_TOKENS >= 2500
