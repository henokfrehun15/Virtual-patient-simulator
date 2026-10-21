import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import PaginationParams, get_current_user
from app.core.database import get_db
from app.models.progress import UserProgress
from app.models.report import SessionReport
from app.models.scenario import Scenario, ScenarioPatientState
from app.models.session import DiagnosisAttempt, Session as SessionModel
from app.models.user import User
from app.schemas.common import Page
from app.schemas.report import ProgressCategoryResponse, ProgressResponse, SessionHistoryItem
from app.services.scenario import scenario_title

router = APIRouter(prefix="/api/v1/users/me", tags=["progress"])


@router.get("/progress", response_model=ProgressResponse)
def get_progress(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProgressResponse:
    rows = (
        db.scalars(
            select(UserProgress)
            .where(UserProgress.user_id == user.id)
            .order_by(UserProgress.category)
        )
        .unique()
        .all()
    )
    categories = [
        ProgressCategoryResponse(
            category=row.category,
            rolling_score=float(row.rolling_score) if row.rolling_score is not None else None,
            rolling_attempts=row.rolling_attempts,
            trend=row.trend,
        )
        for row in rows
    ]

    sessions_completed = (
        db.scalar(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user.id, SessionModel.status == "completed")
        )
        or 0
    )

    diagnosis_scores = [
        float(report.diagnosis_score)
        for report in db.scalars(
            select(SessionReport).join(SessionModel, SessionModel.id == SessionReport.session_id)
            .where(SessionModel.user_id == user.id, SessionModel.status == "completed")
        ).all()
        if report.diagnosis_score is not None
    ]
    diagnosis_accuracy = (
        round(sum(diagnosis_scores) / len(diagnosis_scores), 1) if diagnosis_scores else None
    )

    return ProgressResponse(
        categories=categories,
        diagnosis_accuracy=diagnosis_accuracy,
        sessions_completed=sessions_completed,
    )


@router.get("/history", response_model=Page[SessionHistoryItem])
def get_history(
    pagination: PaginationParams = Depends(),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[SessionHistoryItem]:
    total = (
        db.scalar(
            select(func.count())
            .select_from(SessionModel)
            .where(SessionModel.user_id == user.id, SessionModel.status == "completed")
        )
        or 0
    )
    sessions = (
        db.scalars(
            select(SessionModel)
            .where(SessionModel.user_id == user.id, SessionModel.status == "completed")
            .order_by(SessionModel.ended_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .unique()
        .all()
    )

    items: list[SessionHistoryItem] = []
    for session in sessions:
        report = db.scalar(
            select(SessionReport).where(SessionReport.session_id == session.id)
        )
        state_row = db.scalar(
            select(ScenarioPatientState).where(
                ScenarioPatientState.scenario_id == session.scenario_id
            )
        )
        state = state_row.state if state_row is not None else {}
        last_attempt = (
            db.scalars(
                select(DiagnosisAttempt)
                .where(DiagnosisAttempt.session_id == session.id)
                .order_by(DiagnosisAttempt.created_at.desc())
                .limit(1)
            )
            .first()
        )
        items.append(
            SessionHistoryItem(
                id=session.id,
                scenario_title=scenario_title(state),
                mode=session.mode,
                overall_score=float(report.overall_score)
                if report is not None and report.overall_score is not None
                else None,
                diagnosis_verdict=last_attempt.verdict if last_attempt is not None else None,
                ended_at=session.ended_at,
            )
        )

    return Page(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
