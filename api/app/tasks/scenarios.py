import sys
import uuid

from celery import Task

from app.core.logging import get_logger
from app.services.scenario import DIFFICULTIES, run_scenario_generation
from app.workers.celery_app import celery_app

logger = get_logger("app.tasks.scenarios")

MAX_ATTEMPTS = 3


@celery_app.task(bind=True, name="scenarios.generate", max_retries=MAX_ATTEMPTS - 1)
def generate_scenario(self: Task, disease_version_id: str, difficulty: str) -> None:
    try:
        run_scenario_generation(uuid.UUID(disease_version_id), difficulty)
    except Exception as exc:
        retries = getattr(self.request, "retries", 0)
        if retries >= MAX_ATTEMPTS - 1:
            logger.exception(
                "scenario_generation_gave_up",
                disease_version_id=disease_version_id,
                difficulty=difficulty,
            )
            return
        countdown = 60 * (2**retries)
        logger.warning(
            "scenario_generation_retry_scheduled",
            disease_version_id=disease_version_id,
            difficulty=difficulty,
            retry_in_seconds=countdown,
            error=repr(exc),
        )
        raise self.retry(exc=exc, countdown=countdown)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.tasks.scenarios <disease_version_id> [difficulty]")
        raise SystemExit(1)
    disease_version_id = uuid.UUID(sys.argv[1])
    difficulties = [sys.argv[2]] if len(sys.argv) > 2 else list(DIFFICULTIES)
    for difficulty in difficulties:
        run_scenario_generation(disease_version_id, difficulty)
