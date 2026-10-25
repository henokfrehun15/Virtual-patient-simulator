import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.llm import UserLLMSettings
from app.schemas.settings import LLMSettingsResponse, LLMSettingsUpdate

MODEL_FIELDS = (
    "extraction_model",
    "scenario_model",
    "patient_model",
    "scoring_model",
    "feedback_model",
)

SUPPORTED_PROVIDERS = ("anthropic", "groq")


def get_llm_settings_row(db: DbSession, user_id: uuid.UUID) -> UserLLMSettings | None:
    return db.scalar(select(UserLLMSettings).where(UserLLMSettings.user_id == user_id))


def resolve_provider(row: UserLLMSettings | None) -> str:
    provider = (row.provider if row is not None else None) or get_settings().llm_provider
    return provider if provider in SUPPORTED_PROVIDERS else "anthropic"


def env_api_key_for(provider: str) -> str | None:
    settings = get_settings()
    if provider == "groq":
        key = settings.groq_api_key
    else:
        key = settings.anthropic_api_key
    return key if key and key != "replace-me" else None


def update_llm_settings(
    db: DbSession, user_id: uuid.UUID, body: LLMSettingsUpdate
) -> UserLLMSettings:
    row = get_llm_settings_row(db, user_id)
    if row is None:
        row = UserLLMSettings(user_id=user_id)
        db.add(row)

    previous_provider = row.provider
    if body.provider is not None:
        row.provider = body.provider

    if body.clear_api_key:
        row.api_key_encrypted = None
    elif body.api_key is not None:
        row.api_key_encrypted = encrypt_secret(body.api_key.strip())
    elif body.provider is not None and previous_provider != body.provider:
        row.api_key_encrypted = None

    for field in MODEL_FIELDS:
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() or None)

    db.commit()
    db.refresh(row)
    return row


def llm_settings_response(db: DbSession, user_id: uuid.UUID) -> LLMSettingsResponse:
    settings = get_settings()
    row = get_llm_settings_row(db, user_id)
    provider = resolve_provider(row)

    api_key_set = False
    api_key_source: str | None = None
    if row is not None and row.api_key_encrypted:
        try:
            api_key_set = bool(decrypt_secret(row.api_key_encrypted).strip())
            api_key_source = "user" if api_key_set else None
        except Exception:
            api_key_set = False
    if not api_key_set and env_api_key_for(provider) is not None:
        api_key_set = True
        api_key_source = "env"

    env_values = {
        "extraction_model": settings.llm_extraction_model,
        "scenario_model": settings.llm_scenario_model,
        "patient_model": settings.llm_patient_model,
        "scoring_model": settings.llm_scoring_model,
        "feedback_model": settings.llm_feedback_model,
    }
    models = {
        field: (getattr(row, field) if row is not None else None) or env_values[field] or ""
        for field in MODEL_FIELDS
    }

    return LLMSettingsResponse(
        provider=provider,
        api_key_set=api_key_set,
        api_key_source=api_key_source,
        **models,
    )
