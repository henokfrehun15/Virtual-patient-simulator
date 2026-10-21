import uuid

from celery import Task

from app.core.logging import get_logger
from app.services.completion import run_completion
from app.workers.celery_app import celery_app

logger = get_logger("app.tasks.completion")


@celery_app.task(bind=True, name="sessions.complete_session", max_retries=2)
def complete_session(self: Task, session_id: str, user_id: str) -> None:
    try:
        run_completion(uuid.UUID(session_id), uuid.UUID(user_id))
    except Exception as exc:
        retries = getattr(self.request, "retries", 0)
        if retries >= 2:
            logger.exception("completion_gave_up", session_id=session_id)
            return
        logger.warning(
            "completion_retry_scheduled",
            session_id=session_id,
            error=repr(exc),
        )
        raise self.retry(exc=exc, countdown=30 * (2**retries))
