import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.idempotency import load_result, store_result
from app.models.scenario import ScenarioExamination
from app.models.session import ExaminationRequest, Session as SessionModel
from app.services.session import ensure_session_active, record_session_event


def _normalize(value: str) -> str:
    value = re.sub(r"[^a-z0-9 ]", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def _matches(requested: str, available: str) -> bool:
    requested_norm = _normalize(requested)
    available_norm = _normalize(available)
    if len(requested_norm) < 2 or len(available_norm) < 2:
        return False
    return requested_norm in available_norm or available_norm in requested_norm


def request_examination(
    db: DbSession,
    session: SessionModel,
    exam_name: str,
    idempotency_key: str | None,
) -> ExaminationRequest:
    settings = get_settings()
    ensure_session_active(db, session)

    if idempotency_key:
        stored = load_result(f"idem:exam:{session.id}:{idempotency_key}")
        if stored is not None:
            existing = db.get(ExaminationRequest, uuid.UUID(stored["request_id"]))
            if existing is not None and existing.session_id == session.id:
                return existing

    count = (
        db.scalar(
            select(func.count())
            .select_from(ExaminationRequest)
            .where(ExaminationRequest.session_id == session.id)
        )
        or 0
    )
    if count >= settings.max_examinations_per_session:
        raise AppError(
            "EXAMINATION_LIMIT",
            f"Maximum of {settings.max_examinations_per_session} examinations per session.",
            status_code=409,
        )

    catalog = (
        db.scalars(
            select(ScenarioExamination).where(
                ScenarioExamination.scenario_id == session.scenario_id,
                ScenarioExamination.available.is_(True),
            )
        )
        .unique()
        .all()
    )
    match = next(
        (entry for entry in catalog if _matches(exam_name, entry.exam_name)), None
    )
    if match is None:
        raise AppError(
            "EXAMINATION_UNAVAILABLE",
            "That examination is not available for this encounter.",
            status_code=404,
        )

    request_row = ExaminationRequest(
        session_id=session.id, exam_name=match.exam_name, result=match.findings or {}
    )
    db.add(request_row)
    db.flush()
    record_session_event(db, session.id, "examination_requested", {"exam_name": match.exam_name})
    record_session_event(
        db,
        session.id,
        "examination_returned",
        {"exam_name": match.exam_name, "request_id": str(request_row.id)},
    )
    db.commit()
    db.refresh(request_row)

    if idempotency_key:
        store_result(
            f"idem:exam:{session.id}:{idempotency_key}", {"request_id": str(request_row.id)}
        )
    return request_row
