from __future__ import annotations

from types import SimpleNamespace

from chat_agent_cli.llm import ChatModel


class _FakeResponsesApi:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(
            output_text="Привет",
            usage=SimpleNamespace(input_tokens=7, output_tokens=3, total_tokens=10),
        )

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)

        class _Stream:
            def __enter__(self):
                return self

            def __iter__(self):
                return iter(
                    [
                        SimpleNamespace(type="response.output_text.delta", delta="Х"),
                        SimpleNamespace(type="response.output_text.delta", delta="ей"),
                    ]
                )

            def __exit__(self, exc_type, exc, tb):
                return False

            def get_final_response(self):
                return SimpleNamespace(
                    output_text="Хей",
                    usage=SimpleNamespace(input_tokens=7, output_tokens=2, total_tokens=9),
                )

        return _Stream()


class _FakeOpenAI:
    last_kwargs: dict[str, object] | None = None

    def __init__(self, *_args, **kwargs) -> None:
        _FakeOpenAI.last_kwargs = dict(kwargs)
        self.responses = _FakeResponsesApi()


def test_chat_model_uses_responses_api_for_localhost_reply(monkeypatch) -> None:
    monkeypatch.setattr("chat_agent_cli.llm.OpenAI", _FakeOpenAI)

    model = ChatModel(
        api_key="local",
        model="qwen/qwen3.5-9b",
        base_url="http://localhost:1234/v1",
    )

    reply = model.reply(
        [
            {"role": "system", "content": "You are a practical assistant in a terminal chat."},
            {"role": "user", "content": "Хей"},
        ]
    )

    assert reply.text == "Привет"
    assert reply.usage is not None
    assert reply.usage.input_tokens == 7
    assert reply.usage.output_tokens == 3
    timeout = _FakeOpenAI.last_kwargs["timeout"]
    assert timeout.connect == 300.0
    assert timeout.write == 300.0
    assert timeout.pool == 300.0
    assert timeout.read == 300.0


def test_chat_model_uses_responses_api_for_localhost_stream(monkeypatch) -> None:
    monkeypatch.setattr("chat_agent_cli.llm.OpenAI", _FakeOpenAI)

    model = ChatModel(
        api_key="local",
        model="qwen/qwen3.5-9b",
        base_url="http://127.0.0.1:1234/v1",
    )

    chunks: list[str] = []
    reply = model.reply_stream(
        [
            {"role": "system", "content": "You are a practical assistant in a terminal chat."},
            {"role": "user", "content": "Хей"},
        ],
        on_delta=chunks.append,
    )

    assert chunks == ["Х", "ей"]
    assert reply.text == "Хей"
    assert reply.usage is not None
    assert reply.usage.input_tokens == 7
    assert reply.usage.output_tokens == 2
