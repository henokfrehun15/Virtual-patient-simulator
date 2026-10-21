import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import PaginationParams, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models.disease import Disease, DiseaseVersion
from app.models.scenario import Scenario, ScenarioPatientState
from app.models.user import User
from app.schemas.common import Page
from app.schemas.scenario import (
    ScenarioDetailResponse,
    ScenarioDiseaseInfo,
    ScenarioPatientInfo,
    ScenarioSummaryResponse,
)
from app.services.scenario import scenario_title

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])
disease_router = APIRouter(prefix="/api/v1/diseases/{disease_id}/scenarios", tags=["scenarios"])


def _patient_state(db: DbSession, scenario_id: uuid.UUID) -> dict:
    row = db.scalar(
        select(ScenarioPatientState).where(ScenarioPatientState.scenario_id == scenario_id)
    )
    return row.state if row is not None else {}


def _summary(db: DbSession, scenario: Scenario) -> ScenarioSummaryResponse:
    settings = get_settings()
    state = _patient_state(db, scenario.id)
    return ScenarioSummaryResponse(
        id=scenario.id,
        difficulty=scenario.difficulty,
        title=scenario_title(state),
        estimated_duration_minutes=settings.scenario_estimated_duration_minutes,
        status=scenario.status,
        created_at=scenario.created_at,
    )


@disease_router.get("", response_model=Page[ScenarioSummaryResponse])
def list_disease_scenarios(
    disease_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[ScenarioSummaryResponse]:
    disease = db.get(Disease, disease_id)
    if disease is None:
        raise AppError("DISEASE_NOT_FOUND", "Disease not found.", status_code=404)

    subquery = (
        select(Scenario.id)
        .join(DiseaseVersion, DiseaseVersion.id == Scenario.disease_version_id)
        .where(DiseaseVersion.disease_id == disease_id, Scenario.status == "published")
    )
    total = (
        db.scalar(select(func.count()).select_from(Scenario).where(Scenario.id.in_(subquery)))
        or 0
    )
    rows = (
        db.scalars(
            select(Scenario)
            .where(Scenario.id.in_(subquery))
            .order_by(Scenario.difficulty, Scenario.version)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .unique()
        .all()
    )

    return Page(
        items=[_summary(db, row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{scenario_id}", response_model=ScenarioDetailResponse)
def get_scenario(
    scenario_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScenarioDetailResponse:
    scenario = db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != "published":
        raise AppError("SCENARIO_NOT_FOUND", "Scenario not found.", status_code=404)

    disease_version = db.get(DiseaseVersion, scenario.disease_version_id)
    disease = db.get(Disease, disease_version.disease_id)
    state = _patient_state(db, scenario.id)
    demographics = state.get("demographics") or {}
    age = demographics.get("age")

    summary = _summary(db, scenario)
    return ScenarioDetailResponse(
        **summary.model_dump(),
        disease=ScenarioDiseaseInfo(
            id=disease.id,
            canonical_name=disease.canonical_name,
            name=disease_version.name,
        ),
        disease_version=disease_version.version,
        chief_complaint=state.get("chief_complaint") or "",
        patient=ScenarioPatientInfo(
            name=demographics.get("name"),
            age=age if isinstance(age, int) else None,
            sex=demographics.get("sex"),
        ),
        modes=["practice", "test"],
    )
