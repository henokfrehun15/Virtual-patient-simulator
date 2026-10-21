import uuid

from celery import Task

import redis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.scoring import pending_scoring_key, run_message_scoring
from app.workers.celery_app import celery_app

logger = get_logger("app.tasks.scoring")

MAX_ATTEMPTS = 3


@celery_app.task(bind=True, name="scoring.score_message", max_retries=MAX_ATTEMPTS - 1)
def score_message(self: Task, session_id: str, doctor_message_id: str, user_id: str) -> None:
    try:
        run_message_scoring(
            uuid.UUID(session_id), uuid.UUID(doctor_message_id), uuid.UUID(user_id)
        )
    except Exception as exc:
        retries = getattr(self.request, "retries", 0)
        if retries < MAX_ATTEMPTS - 1:
            logger.warning(
                "scoring_retry_scheduled",
                session_id=session_id,
                message_id=doctor_message_id,
                error=repr(exc),
            )
            raise self.retry(exc=exc, countdown=15 * (2**retries))
        logger.exception(
            "scoring_gave_up", session_id=session_id, message_id=doctor_message_id
        )

    try:
        client = redis.Redis.from_url(get_settings().redis_url)
        client.decr(pending_scoring_key(uuid.UUID(session_id)))
    except Exception:
        logger.warning("scoring_counter_decr_failed", session_id=session_id)
