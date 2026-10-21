from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("vps", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    imports=("app.tasks",),
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 3600},
    result_expires=86400,
)
