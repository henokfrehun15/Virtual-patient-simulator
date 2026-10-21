import time
import uuid
from datetime import datetime, timezone

import redis
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.prompts import feedback as feedback_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.llm.schemas import FeedbackResult
from app.models.report import SessionReport
from app.models.rubric import RubricItem
from app.models.score import SessionRubricResult
from app.models.scenario import Scenario
from app.models.session import DiagnosisAttempt, Session as SessionModel
from app.services.scoring import STATUS_MULTIPLIERS, pending_scoring_key
from app.services.session import ensure_session_active, record_session_event

logger = get_logger("app.completion")

COMPLETION_LOCK_TTL_SECONDS = 900

HISTORY_CATEGORIES = {
    "chief_complaint",
    "hpi",
    "pmh",
    "medications",
    "allergies",
    "family_history",
    "social_history",
    "ros",
    "red_flag_screen",
}
COMMUNICATION_CATEGORIES = {"communication"}
REASONING_CATEGORIES = {"clinical_reasoning"}


def request_completion(db, session: SessionModel) -> SessionModel:
    if session.status in ("completed", "completing"):
        return session
    ensure_session_active(db, session)

    session.status = "completing"
    session.completed_reason = "student_requested"
    db.flush()
    record_session_event(db, session.id, "session_completing", {})
    db.commit()
    db.refresh(session)

    try:
        from app.tasks.completion import complete_session

        complete_session.delay(str(session.id), str(session.user_id))
    except Exception:
        logger.error("completion_enqueue_failed", session_id=str(session.id))
        session.status = "active"
        session.completed_reason = None
        db.commit()
        raise AppError("INTERNAL_ERROR", "Could not start session completion.", 503)

    return session


def run_completion(session_id: uuid.UUID, user_id: uuid.UUID) -> None:
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    lock_key = f"lock:complete:{session_id}"
    if not lock_client.set(lock_key, "1", nx=True, ex=COMPLETION_LOCK_TTL_SECONDS):
        logger.info("completion_skipped_locked", session_id=str(session_id))
        return

    try:
        _wait_for_scoring(session_id)

        with SessionLocal() as db:
            session = db.get(SessionModel, session_id)
            if session is None or session.status != "completing":
                return
            _finalize(db, session, user_id)
    finally:
        lock_client.delete(lock_key)


def _wait_for_scoring(session_id: uuid.UUID) -> bool:
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url)
    deadline = time.time() + settings.scoring_wait_timeout_seconds
    while time.time() < deadline:
        try:
            pending = int(client.get(pending_scoring_key(session_id)) or 0)
        except Exception:
            pending = 0
        if pending <= 0:
            return True
        time.sleep(2)
    logger.warning("scoring_wait_timeout", session_id=str(session_id))
    return False


def _finalize(db, session: SessionModel, user_id: uuid.UUID) -> None:
    settings = get_settings()
    scenario = db.get(Scenario, session.scenario_id)
    items = (
        db.scalars(
            select(RubricItem).where(RubricItem.disease_version_id == scenario.disease_version_id)
        )
        .unique()
        .all()
    )
    item_by_id = {item.id: item for item in items}

    existing_results = (
        db.scalars(
            select(SessionRubricResult).where(SessionRubricResult.session_id == session.id)
        )
        .unique()
        .all()
    )
    results_by_item = {result.rubric_item_id: result for result in existing_results}

    for item in items:
        if item.id not in results_by_item:
            result = SessionRubricResult(
                session_id=session.id,
                rubric_item_id=item.id,
                status="not_attempted",
                weight=item.weight,
            )
            db.add(result)
            results_by_item[item.id] = result
    db.flush()

    def group_score(categories: set[str]) -> float | None:
        total_weight = 0.0
        points = 0.0
        for result in results_by_item.values():
            item = item_by_id.get(result.rubric_item_id)
            if item is None or item.category not in categories:
                continue
            if result.status == "not_applicable":
                continue
            weight = float(result.weight or item.weight or 1)
            total_weight += weight
            points += weight * STATUS_MULTIPLIERS.get(result.status, 0.0)
        if total_weight == 0:
            return None
        return round(points / total_weight * 100, 1)

    history_score = group_score(HISTORY_CATEGORIES)
    communication_score = group_score(COMMUNICATION_CATEGORIES)
    reasoning_score = group_score(REASONING_CATEGORIES)

    total_weight = 0.0
    points = 0.0
    critical_misses: list[str] = []
    for result in results_by_item.values():
        item = item_by_id.get(result.rubric_item_id)
        if item is None or result.status == "not_applicable":
            continue
        weight = float(result.weight or item.weight or 1)
        total_weight += weight
        points += weight * STATUS_MULTIPLIERS.get(result.status, 0.0)
        if item.critical and result.status not in ("satisfied", "partially_satisfied"):
            critical_misses.append(item.question_text)

    overall_score: float | None = None
    if total_weight > 0:
        base = points / total_weight * 100
        overall_score = round(
            max(0.0, base - settings.critical_miss_penalty * len(critical_misses)), 1
        )

    last_attempt = (
        db.scalars(
            select(DiagnosisAttempt)
            .where(DiagnosisAttempt.session_id == session.id)
            .order_by(DiagnosisAttempt.created_at.desc())
            .limit(1)
        )
        .first()
    )
    diagnosis_score = (
        {"correct": 100.0, "partial": 50.0, "incorrect": 0.0}.get(last_attempt.verdict, 0.0)
        if last_attempt is not None
        else 0.0
    )

    feedback = None
    feedback_model = None
    try:
        router = get_llm_router(user_id)
        payload = {
            "mode": session.mode,
            "scores": {
                "overall": overall_score,
                "history": history_score,
                "communication": communication_score,
                "reasoning": reasoning_score,
                "diagnosis": diagnosis_score,
            },
            "rubric_results": [
                {
                    "category": item_by_id[result.rubric_item_id].category,
                    "question": item_by_id[result.rubric_item_id].question_text,
                    "status": result.status,
                    "weight": float(result.weight or 1),
                    "critical": item_by_id[result.rubric_item_id].critical,
                }
                for result in results_by_item.values()
                if result.rubric_item_id in item_by_id
            ],
            "critical_misses": critical_misses,
            "diagnosis": {
                "student_guess": last_attempt.guess,
                "verdict": last_attempt.verdict,
            }
            if last_attempt is not None
            else None,
        }
        feedback = router.generate(
            "feedback_generation",
            LLMRequest(
                system=feedback_prompts.SYSTEM_PROMPT,
                user=feedback_prompts.build_user_content(payload),
                schema_model=FeedbackResult,
                max_tokens=feedback_prompts.MAX_TOKENS,
                prompt_version=feedback_prompts.PROMPT_VERSION,
                session_id=session.id,
            ),
        )
        feedback_model = router.model_for_task("feedback_generation")
    except AppError as exc:
        logger.warning("feedback_generation_failed", session_id=str(session.id), code=exc.code)

    report = SessionReport(
        session_id=session.id,
        overall_score=overall_score,
        history_score=history_score,
        communication_score=communication_score,
        reasoning_score=reasoning_score,
        diagnosis_score=diagnosis_score,
        critical_misses=critical_misses,
        strengths=feedback.strengths if feedback else [],
        gaps=feedback.gaps if feedback else [],
        narrative=feedback.narrative if feedback else None,
        recommended_focus=feedback.one_recommended_focus if feedback else None,
        generated_by_model=feedback_model,
        generated_prompt_version=feedback_prompts.PROMPT_VERSION if feedback else None,
    )
    db.add(report)

    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    record_session_event(
        db, session.id, "session_completed", {"overall_score": overall_score}
    )
    if feedback is not None:
        record_session_event(db, session.id, "feedback_generated", {})

    from app.services.progress import update_user_progress

    db.flush()
    update_user_progress(db, session.user_id)

    db.commit()
    logger.info(
        "session_completed",
        session_id=str(session.id),
        overall_score=overall_score,
        critical_misses=len(critical_misses),
    )
