from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.llm.router import get_llm_router
from app.models.user import User
from app.schemas.settings import (
    LLMSettingsResponse,
    LLMSettingsTestResponse,
    LLMSettingsUpdate,
    ModelTestResult,
)
from app.services.llm_settings import llm_settings_response, update_llm_settings

router = APIRouter(prefix="/api/v1/users/me", tags=["settings"])


@router.get("/llm-settings", response_model=LLMSettingsResponse)
def get_settings_current(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LLMSettingsResponse:
    return llm_settings_response(db, user.id)


@router.put("/llm-settings", response_model=LLMSettingsResponse)
def update_settings_current(
    body: LLMSettingsUpdate,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LLMSettingsResponse:
    update_llm_settings(db, user.id, body)
    return llm_settings_response(db, user.id)


@router.post("/llm-settings/test", response_model=LLMSettingsTestResponse)
def test_settings_current(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LLMSettingsTestResponse:
    llm_router = get_llm_router(user.id)
    results = llm_router.test_models()
    if not results:
        results = [{"model": "", "ok": False, "error": "LLM_NOT_CONFIGURED"}]
    return LLMSettingsTestResponse(
        results=[ModelTestResult(**result) for result in results]
    )
