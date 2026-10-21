from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/ready")
def ready(db: DbSession = Depends(get_db)):
    checks = {"database": False, "redis": False}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    try:
        redis_client = Redis.from_url(get_settings().redis_url)
        redis_client.ping()
        redis_client.close()
        checks["redis"] = True
    except Exception:
        pass

    if not all(checks.values()):
        return JSONResponse(status_code=503, content={"status": "unavailable", "checks": checks})
    return {"status": "ready", "checks": checks}
