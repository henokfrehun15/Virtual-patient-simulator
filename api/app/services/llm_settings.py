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


def get_llm_settings_row(db: DbSession, user_id: uuid.UUID) -> UserLLMSettings | None:
    return db.scalar(select(UserLLMSettings).where(UserLLMSettings.user_id == user_id))


def update_llm_settings(
    db: DbSession, user_id: uuid.UUID, body: LLMSettingsUpdate
) -> UserLLMSettings:
    row = get_llm_settings_row(db, user_id)
    if row is None:
        row = UserLLMSettings(user_id=user_id)
        db.add(row)

    if body.clear_api_key:
        row.api_key_encrypted = None
    elif body.api_key is not None:
        row.api_key_encrypted = encrypt_secret(body.api_key.strip())

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

    api_key_set = False
    api_key_source: str | None = None
    if row is not None and row.api_key_encrypted:
        try:
            api_key_set = bool(decrypt_secret(row.api_key_encrypted).strip())
            api_key_source = "user" if api_key_set else None
        except Exception:
            api_key_set = False
    if not api_key_set and settings.anthropic_api_key and settings.anthropic_api_key != "replace-me":
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
        api_key_set=api_key_set,
        api_key_source=api_key_source,
        **models,
    )
