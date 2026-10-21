import redis

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger("app.ratelimit")


def enforce_rate_limit(scope: str, identifier: str, limit: int, window_seconds: int) -> None:
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        key = f"ratelimit:{scope}:{identifier}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
    except Exception:
        logger.warning("rate_limit_unavailable", scope=scope)
        return

    if count > limit:
        raise AppError("RATE_LIMITED", "Too many requests. Please try again later.", status_code=429)
