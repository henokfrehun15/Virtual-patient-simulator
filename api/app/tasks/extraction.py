import sys
import uuid

from celery import Task

from app.core.logging import get_logger
from app.services.clinical_content import run_clinical_content
from app.workers.celery_app import celery_app

logger = get_logger("app.tasks.extraction")

MAX_ATTEMPTS = 3


@celery_app.task(bind=True, name="ingestion.extract_clinical_content", max_retries=MAX_ATTEMPTS - 1)
def extract_clinical_content(self: Task, material_version_id: str) -> None:
    try:
        run_clinical_content(uuid.UUID(material_version_id))
    except Exception as exc:
        retries = getattr(self.request, "retries", 0)
        if retries >= MAX_ATTEMPTS - 1:
            logger.exception(
                "clinical_content_gave_up", material_version_id=material_version_id
            )
            return
        countdown = 60 * (2**retries)
        logger.warning(
            "clinical_content_retry_scheduled",
            material_version_id=material_version_id,
            retry_in_seconds=countdown,
            error=repr(exc),
        )
        raise self.retry(exc=exc, countdown=countdown)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.tasks.extraction <material_version_id>")
        raise SystemExit(1)
    run_clinical_content(uuid.UUID(sys.argv[1]))
