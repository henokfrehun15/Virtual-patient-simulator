import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.progress import UserProgress
from app.models.report import SessionReport
from app.models.rubric import RubricItem
from app.models.score import SessionRubricResult
from app.models.session import DiagnosisAttempt, Session as SessionModel

logger = get_logger("app.progress")

CATEGORY_MAP = {
    "chief_complaint": "history_hpi",
    "hpi": "history_hpi",
    "pmh": "history_past_medical",
    "medications": "history_medications",
    "allergies": "history_allergies",
    "family_history": "history_family",
    "social_history": "history_social",
    "ros": "history_ros",
    "red_flag_screen": "red_flag_screening",
    "communication": "communication",
    "clinical_reasoning": "clinical_reasoning",
}

STATUS_MULTIPLIERS = {
    "satisfied": 1.0,
    "partially_satisfied": 0.5,
    "attempted": 0.25,
    "poorly_asked": 0.0,
    "unsafe": 0.0,
    "not_attempted": 0.0,
    "not_applicable": 0.0,
}


def update_user_progress(db: DbSession, user_id: uuid.UUID) -> None:
    settings = get_settings()
    sessions = (
        db.scalars(
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.status == "completed")
            .order_by(SessionModel.ended_at.desc())
            .limit(settings.progress_window_sessions)
        )
        .unique()
        .all()
    )
    sessions.reverse()
    session_ids = [session.id for session in sessions]

    category_scores: dict[str, list[float]] = defaultdict(list)
    if session_ids:
        rows = db.execute(
            select(SessionRubricResult.rubric_item_id, SessionRubricResult.session_id,
                   SessionRubricResult.status, SessionRubricResult.weight, RubricItem.category)
            .join(RubricItem, RubricItem.id == SessionRubricResult.rubric_item_id)
            .where(SessionRubricResult.session_id.in_(session_ids))
        ).all()

        per_session: dict[uuid.UUID, dict[str, tuple[float, float]]] = defaultdict(dict)
        for row in rows:
            progress_category = CATEGORY_MAP.get(row.category)
            if progress_category is None or row.status == "not_applicable":
                continue
            weight = float(row.weight or 1)
            points, total = per_session[row.session_id].get(progress_category, (0.0, 0.0))
            per_session[row.session_id][progress_category] = (
                points + weight * STATUS_MULTIPLIERS.get(row.status, 0.0),
                total + weight,
            )
        for session_id, categories in per_session.items():
            for category, (points, total) in categories.items():
                if total > 0:
                    category_scores[category].append(round(points / total * 100, 1))

        reports = db.scalars(
            select(SessionReport).where(SessionReport.session_id.in_(session_ids))
        ).all()
        for report in reports:
            if report.diagnosis_score is not None:
                category_scores["diagnosis"].append(float(report.diagnosis_score))

    for row in (
        db.scalars(select(UserProgress).where(UserProgress.user_id == user_id)).all()
    ):
        db.delete(row)

    for category, scores in category_scores.items():
        rolling = round(sum(scores) / len(scores), 1) if scores else None
        db.add(
            UserProgress(
                user_id=user_id,
                category=category,
                rolling_score=rolling,
                rolling_attempts=len(scores),
                trend=_trend(scores),
            )
        )
    db.flush()
    logger.info("user_progress_updated", user_id=str(user_id), categories=len(category_scores))


def _trend(scores: list[float]) -> str | None:
    if len(scores) < 4:
        return None
    midpoint = len(scores) // 2
    first_half = sum(scores[:midpoint]) / midpoint
    second_half = sum(scores[midpoint:]) / (len(scores) - midpoint)
    difference = second_half - first_half
    if difference >= 5:
        return "improving"
    if difference <= -5:
        return "declining"
    return "stable"
