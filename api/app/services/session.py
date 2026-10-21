import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.idempotency import load_result, store_result
from app.core.ratelimit import enforce_rate_limit
from app.models.disease import Disease, DiseaseVersion
from app.models.message import Message
from app.models.scenario import Scenario, ScenarioPatientState
from app.models.session import ExaminationRequest, InvestigationRequest
from app.models.session import Session as SessionModel
from app.models.session import SessionEvent
from app.models.user import User
from app.schemas.session import (
    ExaminationResponse,
    InvestigationResponse,
    MessageResponse,
    SessionPatientInfo,
    SessionResponse,
    SessionScenarioInfo,
)
from app.services.audit import record_audit_event
from app.services.scenario import scenario_title


def record_session_event(
    db: DbSession,
    session_id: uuid.UUID,
    event_type: str,
    event_data: dict | None = None,
) -> None:
    db.add(SessionEvent(session_id=session_id, event_type=event_type, event_data=event_data))


def get_owned_session_or_404(db: DbSession, user: User, session_id: uuid.UUID) -> SessionModel:
    session = db.get(SessionModel, session_id)
    if session is None or session.user_id != user.id:
        raise AppError("SESSION_NOT_FOUND", "Session not found.", status_code=404)
    return session


def ensure_session_active(db: DbSession, session: SessionModel) -> None:
    if session.status == "completed":
        raise AppError("SESSION_ALREADY_COMPLETED", "This session is already completed.", 409)
    if session.status != "active":
        raise AppError("SESSION_NOT_ACTIVE", "This session is not active.", 409)

    if session.started_at is not None and session.time_limit_seconds is not None:
        expires_at = session.started_at + timedelta(seconds=session.time_limit_seconds)
        if datetime.now(timezone.utc) > expires_at:
            session.status = "abandoned"
            session.completed_reason = "time_limit"
            session.ended_at = datetime.now(timezone.utc)
            record_session_event(db, session.id, "session_abandoned", {"reason": "time_limit"})
            db.commit()
            raise AppError("SESSION_NOT_ACTIVE", "This session has expired.", 409)


def start_session(
    db: DbSession,
    user: User,
    *,
    scenario_id: uuid.UUID,
    mode: str,
    idempotency_key: str | None,
) -> SessionModel:
    settings = get_settings()
    enforce_rate_limit(
        "session_start",
        str(user.id),
        settings.session_start_rate_limit_count,
        settings.session_start_rate_limit_window_seconds,
    )

    if idempotency_key:
        stored = load_result(f"idem:start:{user.id}:{idempotency_key}")
        if stored is not None:
            existing = db.get(SessionModel, uuid.UUID(stored["session_id"]))
            if existing is not None and existing.user_id == user.id:
                return existing

    scenario = db.get(Scenario, scenario_id)
    if scenario is None or scenario.status != "published":
        raise AppError("SCENARIO_INVALID", "Scenario not found or unavailable.", status_code=404)

    now = datetime.now(timezone.utc)
    session = SessionModel(
        user_id=user.id,
        scenario_id=scenario.id,
        scenario_version=scenario.version,
        mode=mode,
        status="active",
        current_turn=0,
        turn_limit=settings.max_session_turns,
        time_limit_seconds=settings.session_time_limit_seconds,
        started_at=now,
        last_activity_at=now,
    )
    db.add(session)
    db.flush()
    record_session_event(db, session.id, "session_started", {"mode": mode})
    record_audit_event(
        db,
        user_id=user.id,
        action="session.started",
        resource_type="session",
        resource_id=session.id,
        metadata={"mode": mode, "scenario_id": str(scenario.id)},
    )
    db.commit()
    db.refresh(session)

    if idempotency_key:
        store_result(f"idem:start:{user.id}:{idempotency_key}", {"session_id": str(session.id)})
    return session


def build_session_response(db: DbSession, session: SessionModel) -> SessionResponse:
    settings = get_settings()
    scenario = db.get(Scenario, session.scenario_id)
    state_row = db.scalar(
        select(ScenarioPatientState).where(ScenarioPatientState.scenario_id == session.scenario_id)
    )
    state = state_row.state if state_row is not None else {}
    demographics = state.get("demographics") or {}
    age = demographics.get("age")

    disease_version = db.get(DiseaseVersion, scenario.disease_version_id)
    disease = db.get(Disease, disease_version.disease_id)

    messages = db.scalars(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.turn_number, Message.created_at)
    ).all()

    exam_requests = (
        db.scalars(
            select(ExaminationRequest)
            .where(ExaminationRequest.session_id == session.id)
            .order_by(ExaminationRequest.created_at)
        )
        .unique()
        .all()
    )
    inv_requests = (
        db.scalars(
            select(InvestigationRequest)
            .where(InvestigationRequest.session_id == session.id)
            .order_by(InvestigationRequest.created_at)
        )
        .unique()
        .all()
    )

    return SessionResponse(
        id=session.id,
        mode=session.mode,
        status=session.status,
        current_turn=session.current_turn,
        turn_limit=session.turn_limit,
        time_limit_seconds=session.time_limit_seconds,
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        ended_at=session.ended_at,
        completed_reason=session.completed_reason,
        scenario=SessionScenarioInfo(
            id=scenario.id,
            title=scenario_title(state),
            difficulty=scenario.difficulty,
            estimated_duration_minutes=settings.scenario_estimated_duration_minutes,
        ),
        patient=SessionPatientInfo(
            name=demographics.get("name"),
            age=age if isinstance(age, int) else None,
            sex=demographics.get("sex"),
        ),
        chief_complaint=state.get("chief_complaint") or "",
        diagnosis=disease_version.name if session.mode == "practice" else None,
        messages=[MessageResponse.model_validate(message) for message in messages],
        examination_requests=[
            ExaminationResponse(
                id=request.id,
                exam_name=request.exam_name,
                result=request.result or {},
                created_at=request.created_at,
            )
            for request in exam_requests
        ],
        investigation_requests=[
            InvestigationResponse(
                id=request.id,
                test_name=request.test_name,
                result=request.result or {},
                created_at=request.created_at,
            )
            for request in inv_requests
        ],
    )
