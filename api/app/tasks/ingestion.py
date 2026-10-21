import uuid

from celery import Task

from app.core.logging import get_logger
from app.services.ingestion import mark_extraction_failed, run_extraction
from app.workers.celery_app import celery_app

logger = get_logger("app.tasks.ingestion")

MAX_ATTEMPTS = 4


@celery_app.task(bind=True, name="ingestion.extract_material", max_retries=MAX_ATTEMPTS - 1)
def extract_material(self: Task, material_version_id: str) -> None:
    try:
        run_extraction(uuid.UUID(material_version_id))
    except Exception as exc:
        retries = getattr(self.request, "retries", 0)
        if retries >= MAX_ATTEMPTS - 1:
            logger.exception("extraction_gave_up", material_version_id=material_version_id)
            mark_extraction_failed(uuid.UUID(material_version_id), repr(exc))
            return
        countdown = 30 * (2**retries)
        logger.warning(
            "extraction_retry_scheduled",
            material_version_id=material_version_id,
            retry_in_seconds=countdown,
            error=repr(exc),
        )
        raise self.retry(exc=exc, countdown=countdown)

    try:
        from app.tasks.extraction import extract_clinical_content

        extract_clinical_content.delay(material_version_id)
    except Exception:
        logger.error(
            "clinical_content_enqueue_failed", material_version_id=material_version_id
        )
