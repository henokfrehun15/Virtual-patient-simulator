import inspect

import anthropic

from app.core.logging import get_logger

logger = get_logger("app.llm.provider")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


class ProviderError(Exception):
    def __init__(self, message: str, error_code: str, retryable: bool = False) -> None:
        self.error_code = error_code
        self.retryable = retryable
        super().__init__(message)


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(self, *, api_key: str, timeout_seconds: float, max_retries: int) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._supports_output_config = (
            "output_config" in inspect.signature(self._client.messages.create).parameters
        )
        if not self._supports_output_config:
            logger.warning("structured_outputs_unsupported_by_sdk")

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_schema: dict | None,
    ) -> tuple[str, int | None, int | None]:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if json_schema is not None:
            if self._supports_output_config:
                kwargs["output_config"] = {
                    "format": {"type": "json_schema", "schema": json_schema}
                }
            else:
                import json

                kwargs["system"] = (
                    f"{system}\n\nReturn only a JSON object that conforms to this JSON "
                    f"schema:\n{json.dumps(json_schema)}"
                )

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            status_code = exc.status_code
            if status_code == 429:
                raise ProviderError(
                    f"Anthropic rate limit (HTTP {status_code}).",
                    error_code="LLM_RATE_LIMITED",
                    retryable=True,
                ) from exc
            if status_code in (401, 403):
                raise ProviderError(
                    f"Anthropic authentication failed (HTTP {status_code}).",
                    error_code="LLM_AUTH_ERROR",
                ) from exc
            if status_code in RETRYABLE_STATUS_CODES:
                raise ProviderError(
                    f"Anthropic server error (HTTP {status_code}).",
                    error_code="LLM_PROVIDER_ERROR",
                    retryable=True,
                ) from exc
            raise ProviderError(
                f"Anthropic request rejected (HTTP {status_code}).",
                error_code="LLM_BAD_REQUEST",
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(
                "Could not connect to the Anthropic API.",
                error_code="LLM_TIMEOUT",
                retryable=True,
            ) from exc
        except anthropic.AnthropicError as exc:
            raise ProviderError(
                f"Unexpected Anthropic SDK error: {exc!r}",
                error_code="LLM_PROVIDER_ERROR",
            ) from exc

        text = "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", "") == "text"
        )
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
        return text, input_tokens, output_tokens
