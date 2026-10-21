import json

import redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.idempotency")

DEFAULT_TTL_SECONDS = 86400


def store_result(key: str, payload: dict, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    try:
        client = redis.Redis.from_url(get_settings().redis_url)
        client.set(key, json.dumps(payload), ex=ttl_seconds)
    except Exception:
        logger.warning("idempotency_store_failed", key=key)


def load_result(key: str) -> dict | None:
    try:
        client = redis.Redis.from_url(get_settings().redis_url)
        raw = client.get(key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
