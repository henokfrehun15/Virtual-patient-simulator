import json
from types import SimpleNamespace

import httpx
import pytest

openai = pytest.importorskip("openai")

from app.llm import groq as groq_module
from app.llm.groq import GroqProvider
from app.llm.provider import ProviderError


def _http_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", "https://api.groq.com/t"))


def _completion(text: str, prompt_tokens: int = 5, completion_tokens: int = 7):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class FakeCompletions:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.handler(kwargs, len(self.calls))


def make_provider(monkeypatch: pytest.MonkeyPatch, handler) -> FakeCompletions:
    completions = FakeCompletions(handler)

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            self.chat = SimpleNamespace(completions=completions)

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(groq_module, "_JSON_SCHEMA_UNSUPPORTED_MODELS", set())
    return completions


def test_complete_free_text(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = make_provider(
        monkeypatch, lambda kwargs, call: _completion("I have a cough.", 3, 9)
    )
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)

    text, input_tokens, output_tokens = provider.complete(
        model="llama-3.3-70b-versatile",
        system="system prompt",
        user="user prompt",
        max_tokens=512,
        json_schema=None,
    )

    assert text == "I have a cough."
    assert input_tokens == 3
    assert output_tokens == 9
    call = completions.calls[0]
    assert call["model"] == "llama-3.3-70b-versatile"
    assert call["max_completion_tokens"] == 512
    assert call["messages"][0] == {"role": "system", "content": "system prompt"}
    assert call["messages"][1] == {"role": "user", "content": "user prompt"}
    assert "response_format" not in call


def test_complete_structured_uses_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = make_provider(
        monkeypatch, lambda kwargs, call: _completion('{"diseases": []}')
    )
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)
    schema = {"type": "object", "properties": {"diseases": {}}}

    text, _, _ = provider.complete(
        model="llama-3.3-70b-versatile",
        system="system",
        user="user",
        max_tokens=256,
        json_schema=schema,
    )

    assert json.loads(text) == {"diseases": []}
    call = completions.calls[0]
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["schema"] == schema
    assert call["messages"][0]["content"] == "system"


def test_complete_falls_back_to_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(kwargs, call):
        if call == 1:
            raise openai.BadRequestError(
                "response_format json_schema is not supported",
                response=_http_response(400),
                body=None,
            )
        return _completion('{"diseases": []}')

    completions = make_provider(monkeypatch, handler)
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)
    schema = {"type": "object", "properties": {"diseases": {}}}

    text, _, _ = provider.complete(
        model="llama-3.3-70b-versatile",
        system="system",
        user="user",
        max_tokens=256,
        json_schema=schema,
    )

    assert json.loads(text) == {"diseases": []}
    assert len(completions.calls) == 2
    fallback = completions.calls[1]
    assert fallback["response_format"] == {"type": "json_object"}
    assert "JSON schema" in fallback["messages"][0]["content"]
    assert "llama-3.3-70b-versatile" in groq_module._JSON_SCHEMA_UNSUPPORTED_MODELS

    provider.complete(
        model="llama-3.3-70b-versatile",
        system="system",
        user="user",
        max_tokens=256,
        json_schema=schema,
    )
    assert completions.calls[2]["response_format"] == {"type": "json_object"}


def test_complete_unrelated_bad_request_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(kwargs, call):
        raise openai.BadRequestError(
            "prompt is too long", response=_http_response(400), body=None
        )

    completions = make_provider(monkeypatch, handler)
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(
            model="llama-3.3-70b-versatile",
            system="system",
            user="user",
            max_tokens=256,
            json_schema={"type": "object"},
        )
    assert exc_info.value.error_code == "LLM_BAD_REQUEST"
    assert len(completions.calls) == 1


def test_auth_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(kwargs, call):
        raise openai.AuthenticationError(
            "invalid api key", response=_http_response(401), body=None
        )

    make_provider(monkeypatch, handler)
    provider = GroqProvider(api_key="gsk_bad", timeout_seconds=1, max_retries=0)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(
            model="llama-3.3-70b-versatile",
            system="system",
            user="user",
            max_tokens=64,
            json_schema=None,
        )
    assert exc_info.value.error_code == "LLM_AUTH_ERROR"


def test_stream_yields_deltas_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    def chunk(content=None, usage=None):
        return SimpleNamespace(
            choices=(
                [SimpleNamespace(delta=SimpleNamespace(content=content))] if content else []
            ),
            usage=usage,
        )

    def handler(kwargs, call):
        assert kwargs["stream"] is True
        assert kwargs["stream_options"] == {"include_usage": True}
        return [
            chunk(content="Hello"),
            chunk(content=" there"),
            chunk(usage=SimpleNamespace(prompt_tokens=11, completion_tokens=2)),
        ]

    make_provider(monkeypatch, handler)
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)

    stream = provider.stream(
        model="llama-3.3-70b-versatile",
        system="system",
        user="user",
        max_tokens=128,
    )
    parts = list(stream)

    assert parts == ["Hello", " there"]
    assert stream.input_tokens == 11
    assert stream.output_tokens == 2


def test_stream_retries_without_stream_options(monkeypatch: pytest.MonkeyPatch) -> None:
    def chunk(content):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))],
            usage=None,
        )

    def handler(kwargs, call):
        if "stream_options" in kwargs:
            raise openai.BadRequestError(
                "stream_options is not supported",
                response=_http_response(400),
                body=None,
            )
        return [chunk("Hi")]

    completions = make_provider(monkeypatch, handler)
    provider = GroqProvider(api_key="gsk_test", timeout_seconds=1, max_retries=0)

    stream = provider.stream(
        model="llama-3.3-70b-versatile",
        system="system",
        user="user",
        max_tokens=128,
    )
    assert list(stream) == ["Hi"]
    assert "stream_options" not in completions.calls[1]
