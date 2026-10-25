from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import pydantic
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.provider import AnthropicProvider, ProviderError
from app.models.llm import LlmRequest as LlmRequestModel
from app.models.llm import UserLLMSettings

if TYPE_CHECKING:
    from app.llm.groq import GroqProvider

logger = get_logger("app.llm.router")

TASK_MODEL_KEYS = {
    "disease_extraction": "extraction_model",
    "rubric_extraction": "extraction_model",
    "scenario_generation": "scenario_model",
    "patient_roleplay": "patient_model",
    "rubric_matching": "scoring_model",
    "diagnosis_normalization": "scoring_model",
    "feedback_generation": "feedback_model",
    "longitudinal_feedback": "feedback_model",
}


@dataclass
class LLMRequest:
    system: str
    user: str
    prompt_version: str
    schema_model: type[pydantic.BaseModel] | None = None
    max_tokens: int = 4096
    schema_version: str = "v1"
    session_id: uuid.UUID | None = None


def extract_json(text: str) -> Any:
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced is not None:
        candidates.append(fenced.group(1))
    for start_marker, end_marker in (("{", "}"), ("[", "]")):
        start = text.find(start_marker)
        end = text.rfind(end_marker)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    raise AppError(
        "LLM_SCHEMA_INVALID",
        "The model response was not valid JSON.",
        status_code=502,
    )


def build_json_schema(model: type[pydantic.BaseModel]) -> dict:
    return _strictify(model.model_json_schema())


def _strictify(node: Any) -> Any:
    if isinstance(node, dict):
        if "properties" in node:
            node.setdefault("additionalProperties", False)
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for item in node:
            _strictify(item)
    return node


class LLMRouter:
    def __init__(self, provider: AnthropicProvider | GroqProvider, models: dict[str, str]) -> None:
        self._provider = provider
        self._models = models

    def model_for_task(self, task: str) -> str:
        model = self._models.get(task)
        if not model:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                f"No model configured for LLM task '{task}'.",
                status_code=503,
            )
        return model

    def configured_models(self) -> list[str]:
        return sorted({model for model in self._models.values() if model})

    def test_models(self) -> list[dict]:
        results: list[dict] = []
        for model in self.configured_models():
            try:
                self._provider.complete(
                    model=model,
                    system="You are a connectivity test.",
                    user="Reply with the single word OK.",
                    max_tokens=16,
                    json_schema=None,
                )
                results.append({"model": model, "ok": True, "error": None})
            except AppError as exc:
                results.append({"model": model, "ok": False, "error": exc.code})
            except ProviderError as exc:
                results.append({"model": model, "ok": False, "error": exc.error_code})
            except Exception as exc:
                results.append({"model": model, "ok": False, "error": repr(exc)})
        return results

    def generate(self, task: str, request: LLMRequest) -> pydantic.BaseModel | str:
        model = self.model_for_task(task)
        schema = build_json_schema(request.schema_model) if request.schema_model else None

        status = "succeeded"
        error_code: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        started = time.perf_counter()
        try:
            text, input_tokens, output_tokens = self._provider.complete(
                model=model,
                system=request.system,
                user=request.user,
                max_tokens=request.max_tokens,
                json_schema=schema,
            )
            if request.schema_model is None:
                return text
            data = extract_json(text)
            return request.schema_model.model_validate(data)
        except AppError as exc:
            status = "failed"
            error_code = exc.code
            raise
        except ProviderError as exc:
            status = "failed"
            error_code = exc.error_code
            raise AppError(exc.error_code, str(exc), status_code=502) from exc
        except pydantic.ValidationError as exc:
            status = "failed"
            error_code = "LLM_SCHEMA_INVALID"
            raise AppError(
                "LLM_SCHEMA_INVALID",
                "The model response failed schema validation.",
                status_code=502,
            ) from exc
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000)
            _record_llm_request(
                task=task,
                provider=self._provider.provider_name,
                model=model,
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                session_id=request.session_id,
            )

    def stream(self, task: str, request: LLMRequest):
        model = self.model_for_task(task)
        provider_stream = self._provider.stream(
            model=model,
            system=request.system,
            user=request.user,
            max_tokens=request.max_tokens,
        )

        status = "succeeded"
        error_code: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        started = time.perf_counter()
        try:
            for delta in provider_stream:
                yield delta
            input_tokens = provider_stream.input_tokens
            output_tokens = provider_stream.output_tokens
        except AppError as exc:
            status = "failed"
            error_code = exc.code
            raise
        except ProviderError as exc:
            status = "failed"
            error_code = exc.error_code
            raise AppError(exc.error_code, str(exc), status_code=502) from exc
        finally:
            latency_ms = round((time.perf_counter() - started) * 1000)
            _record_llm_request(
                task=task,
                provider=self._provider.provider_name,
                model=model,
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
                session_id=request.session_id,
            )


def _record_llm_request(
    *,
    task: str,
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    input_tokens: int | None,
    output_tokens: int | None,
    latency_ms: int,
    status: str,
    error_code: str | None,
    session_id: uuid.UUID | None,
) -> None:
    try:
        with SessionLocal() as db:
            db.add(
                LlmRequestModel(
                    session_id=session_id,
                    task=task,
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    status=status,
                    error_code=error_code,
                )
            )
            db.commit()
    except Exception:
        logger.warning("llm_request_record_failed", task=task)


def _load_user_llm_settings(user_id: uuid.UUID | None) -> UserLLMSettings | None:
    if user_id is None:
        return None
    try:
        with SessionLocal() as db:
            return db.scalar(
                select(UserLLMSettings).where(UserLLMSettings.user_id == user_id)
            )
    except Exception:
        return None


def _build_models(row: UserLLMSettings | None) -> dict[str, str]:
    settings = get_settings()
    values = {
        "extraction_model": (row.extraction_model if row is not None else None)
        or settings.llm_extraction_model,
        "scenario_model": (row.scenario_model if row is not None else None)
        or settings.llm_scenario_model,
        "patient_model": (row.patient_model if row is not None else None)
        or settings.llm_patient_model,
        "scoring_model": (row.scoring_model if row is not None else None)
        or settings.llm_scoring_model,
        "feedback_model": (row.feedback_model if row is not None else None)
        or settings.llm_feedback_model,
    }
    return {task: values[key] for task, key in TASK_MODEL_KEYS.items()}


def _resolve_api_key(row: UserLLMSettings | None, provider: str) -> str | None:
    if row is not None and row.api_key_encrypted:
        try:
            from app.core.crypto import decrypt_secret

            key = decrypt_secret(row.api_key_encrypted).strip()
            if key:
                return key
        except Exception:
            logger.warning("llm_settings_decrypt_failed")
    settings = get_settings()
    env_key = settings.groq_api_key if provider == "groq" else settings.anthropic_api_key
    if env_key and env_key != "replace-me":
        return env_key
    return None


def _resolve_provider(row: UserLLMSettings | None) -> str:
    provider = (row.provider if row is not None else None) or get_settings().llm_provider
    return provider if provider in ("anthropic", "groq") else "anthropic"


@lru_cache(maxsize=256)
def _cached_router(user_id: uuid.UUID | None, version: str) -> LLMRouter:
    settings = get_settings()
    row = _load_user_llm_settings(user_id)
    provider_name = _resolve_provider(row)
    api_key = _resolve_api_key(row, provider_name) or "not-configured"
    provider: AnthropicProvider | GroqProvider
    if provider_name == "groq":
        try:
            from app.llm.groq import GroqProvider
        except ImportError as exc:
            raise AppError(
                "LLM_PROVIDER_UNAVAILABLE",
                "The Groq provider requires the 'openai' package. "
                "Rebuild the API image (docker compose build api) to install it.",
                status_code=503,
            ) from exc
        provider = GroqProvider(
            api_key=api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            base_url=settings.groq_base_url,
        )
    else:
        provider = AnthropicProvider(
            api_key=api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return LLMRouter(provider, _build_models(row))


def get_llm_router(user_id: uuid.UUID | None = None) -> LLMRouter:
    row = _load_user_llm_settings(user_id)
    version = row.updated_at.isoformat() if row is not None else "env"
    return _cached_router(user_id, version)
