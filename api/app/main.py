import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.routes import auth, courses, diseases, health, materials, scenarios
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger

configure_logging()

logger = get_logger("app")
settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    clear_contextvars()
    request_id = str(uuid.uuid4())
    bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled_request_error",
            path=request.url.path,
            method=request.method,
        )
        response = JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error."}},
        )

    latency_ms = round((time.perf_counter() - start) * 1000)
    logger.info(
        "request_completed",
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(materials.router)
app.include_router(materials.upload_router)
app.include_router(diseases.router)
app.include_router(diseases.course_router)
app.include_router(scenarios.router)
app.include_router(scenarios.disease_router)
