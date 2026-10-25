import json

import openai

from app.core.logging import get_logger
from app.llm.provider import RETRYABLE_STATUS_CODES, ProviderError

logger = get_logger("app.llm.groq")

GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

_JSON_SCHEMA_UNSUPPORTED_MODELS: set[str] = set()


def map_groq_status_error(exc: openai.APIStatusError) -> ProviderError:
    status_code = exc.status_code
    if status_code == 429:
        return ProviderError(
            f"Groq rate limit (HTTP {status_code}).",
            error_code="LLM_RATE_LIMITED",
            retryable=True,
        )
    if status_code in (401, 403):
        return ProviderError(
            f"Groq authentication failed (HTTP {status_code}).",
            error_code="LLM_AUTH_ERROR",
        )
    if status_code in RETRYABLE_STATUS_CODES:
        return ProviderError(
            f"Groq server error (HTTP {status_code}).",
            error_code="LLM_PROVIDER_ERROR",
            retryable=True,
        )
    return ProviderError(
        f"Groq request rejected (HTTP {status_code}).",
        error_code="LLM_BAD_REQUEST",
    )


def _is_structured_output_rejection(exc: openai.BadRequestError) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("response_format", "json_schema", "json_object", "structured output")
    )


def _schema_prompt(system: str, json_schema: dict) -> str:
    return (
        f"{system}\n\nReturn only a JSON object that conforms to this JSON schema:\n"
        f"{json.dumps(json_schema)}"
    )


class GroqProvider:
    """OpenAI-compatible provider targeting Groq Cloud."""

    provider_name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
        base_url: str | None = None,
    ) -> None:
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or GROQ_DEFAULT_BASE_URL,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def _create(self, **kwargs):
        return self._client.chat.completions.create(**kwargs)

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_schema: dict | None,
    ) -> tuple[str, int | None, int | None]:
        try:
            if json_schema is None:
                response = self._create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_completion_tokens=max_tokens,
                )
            else:
                response = self._complete_structured(
                    model=model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    json_schema=json_schema,
                )
        except openai.APIStatusError as exc:
            raise map_groq_status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the Groq API.",
                error_code="LLM_TIMEOUT",
                retryable=True,
            ) from exc
        except openai.OpenAIError as exc:
            raise ProviderError(
                f"Unexpected Groq SDK error: {exc!r}",
                error_code="LLM_PROVIDER_ERROR",
            ) from exc

        choices = getattr(response, "choices", None)
        text = ""
        if choices:
            message = getattr(choices[0], "message", None)
            text = getattr(message, "content", None) or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        output_tokens = (
            getattr(usage, "completion_tokens", None) if usage is not None else None
        )
        return text, input_tokens, output_tokens

    def _complete_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_schema: dict,
    ) -> object:
        schema_system = _schema_prompt(system, json_schema)
        user_message = {"role": "user", "content": user}

        attempts: list[dict] = []
        if model not in _JSON_SCHEMA_UNSUPPORTED_MODELS:
            attempts.append(
                {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response",
                            "strict": True,
                            "schema": json_schema,
                        },
                    },
                    "system": system,
                }
            )
        attempts.append(
            {"response_format": {"type": "json_object"}, "system": schema_system}
        )
        attempts.append({"response_format": None, "system": schema_system})

        last_error: openai.BadRequestError | None = None
        for index, attempt in enumerate(attempts):
            kwargs: dict = {
                "model": model,
                "messages": [
                    {"role": "system", "content": attempt["system"]},
                    user_message,
                ],
                "max_completion_tokens": max_tokens,
            }
            if attempt["response_format"] is not None:
                kwargs["response_format"] = attempt["response_format"]
            try:
                return self._create(**kwargs)
            except openai.BadRequestError as exc:
                last_error = exc
                if index < len(attempts) - 1 and _is_structured_output_rejection(exc):
                    if index == 0:
                        _JSON_SCHEMA_UNSUPPORTED_MODELS.add(model)
                        logger.info(
                            "groq_json_schema_fallback",
                            model=model,
                            error=str(exc)[:200],
                        )
                    continue
                break
        assert last_error is not None
        raise last_error

    def stream(self, *, model: str, system: str, user: str, max_tokens: int) -> "OpenAICompatStream":
        return OpenAICompatStream(
            self._client,
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )


class OpenAICompatStream:
    def __init__(self, client, *, model: str, system: str, user: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._system = system
        self._user = user
        self._max_tokens = max_tokens
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None

    def _open_stream(self):
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": self._user},
            ],
            "max_completion_tokens": self._max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            return self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "stream_options" in str(exc).lower():
                kwargs.pop("stream_options")
                return self._create_guarded(**kwargs)
            raise map_groq_status_error(exc) from exc
        except openai.APIStatusError as exc:
            raise map_groq_status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the Groq API.",
                error_code="LLM_TIMEOUT",
                retryable=True,
            ) from exc

    def _create_guarded(self, **kwargs):
        try:
            return self._client.chat.completions.create(**kwargs)
        except openai.APIStatusError as exc:
            raise map_groq_status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the Groq API.",
                error_code="LLM_TIMEOUT",
                retryable=True,
            ) from exc

    def __iter__(self):
        stream = self._open_stream()
        try:
            for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    self.input_tokens = getattr(usage, "prompt_tokens", None)
                    self.output_tokens = getattr(usage, "completion_tokens", None)
                choices = getattr(chunk, "choices", None)
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None)
                    if content:
                        yield content
        except openai.APIStatusError as exc:
            raise map_groq_status_error(exc) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the Groq API.",
                error_code="LLM_TIMEOUT",
                retryable=True,
            ) from exc
        except openai.OpenAIError as exc:
            raise ProviderError(
                f"Unexpected Groq SDK error: {exc!r}",
                error_code="LLM_PROVIDER_ERROR",
            ) from exc
