import json
import uuid

import redis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.core.errors import AppError
from app.core.idempotency import load_result, store_result
from app.core.logging import get_logger
from app.core.ratelimit import enforce_rate_limit
from app.llm.prompts import patient as patient_prompts
from app.llm.router import LLMRequest, get_llm_router
from app.models.message import Message
from app.models.user import User
from app.schemas.session import SessionResponse, StartSessionRequest, StreamMessageRequest
from app.services import conversation
from app.services.session import (
    build_session_response,
    get_owned_session_or_404,
    start_session,
)

logger = get_logger("app.sessions")

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
PATIENT_UNAVAILABLE_MESSAGE = (
    "The patient is unable to respond right now. Please retry this turn."
)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(
    body: StartSessionRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    session = start_session(
        db,
        user,
        scenario_id=body.scenario_id,
        mode=body.mode,
        idempotency_key=body.idempotency_key,
    )
    return build_session_response(db, session)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    session = get_owned_session_or_404(db, user, session_id)
    return build_session_response(db, session)


@router.post("/{session_id}/messages/stream")
def stream_session_message(
    session_id: uuid.UUID,
    body: StreamMessageRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    settings = get_settings()
    session = get_owned_session_or_404(db, user, session_id)
    enforce_rate_limit(
        "session_message",
        str(user.id),
        settings.message_rate_limit_count,
        settings.message_rate_limit_window_seconds,
    )

    if body.idempotency_key:
        stored = load_result(f"idem:msg:{session.id}:{body.idempotency_key}")
        if stored is not None:
            return StreamingResponse(
                _replay_events(uuid.UUID(stored["patient_message_id"]), stored["turn"]),
                media_type="text/event-stream",
                headers=STREAM_HEADERS,
            )

    if session.status == "completed":
        raise AppError("SESSION_ALREADY_COMPLETED", "This session is already completed.", 409)
    if session.status != "active":
        raise AppError("SESSION_NOT_ACTIVE", "This session is not active.", 409)
    if session.current_turn >= (session.turn_limit or settings.max_session_turns):
        raise AppError(
            "SESSION_TURN_LIMIT", "The turn limit for this session has been reached.", 409
        )

    lock_client = redis.Redis.from_url(settings.redis_url)
    lock_key = f"lock:turn:{session.id}"
    if not lock_client.set(lock_key, "1", nx=True, ex=settings.turn_lock_ttl_seconds):
        raise AppError(
            "SESSION_CONCURRENT_TURN",
            "A message for this session is already being processed.",
            409,
        )

    try:
        prepared = conversation.prepare_turn(db, session, body.content)
    except Exception:
        lock_client.delete(lock_key)
        raise

    return StreamingResponse(
        _stream_events(
            session_id=session.id,
            doctor_message_id=prepared.doctor_message_id,
            turn=prepared.turn,
            system=prepared.system,
            user_content=prepared.user_content,
            idempotency_key=body.idempotency_key,
            lock_key=lock_key,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


def _replay_events(patient_message_id: uuid.UUID, turn: int):
    with SessionLocal() as db:
        message = db.get(Message, patient_message_id)
        text = message.content if message is not None else ""
    yield _sse("token", {"text": text})
    yield _sse("done", {"message_id": str(patient_message_id), "turn": turn})


def _stream_events(
    *,
    session_id: uuid.UUID,
    doctor_message_id: uuid.UUID,
    turn: int,
    system: str,
    user_content: str,
    idempotency_key: str | None,
    lock_key: str,
):
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    router = get_llm_router()
    chunks: list[str] = []

    try:
        request = LLMRequest(
            system=system,
            user=user_content,
            prompt_version=patient_prompts.PROMPT_VERSION,
            schema_model=None,
            max_tokens=patient_prompts.MAX_TOKENS,
            session_id=session_id,
        )
        try:
            for delta in router.stream("patient_roleplay", request):
                chunks.append(delta)
                yield _sse("token", {"text": delta})
        except AppError as exc:
            logger.warning(
                "patient_stream_failed", session_id=str(session_id), code=exc.code
            )
            conversation.abort_turn(session_id=session_id, doctor_message_id=doctor_message_id)
            yield _sse("error", {"code": exc.code, "message": PATIENT_UNAVAILABLE_MESSAGE})
            return

        text = "".join(chunks).strip()
        if not text:
            logger.warning("patient_stream_empty", session_id=str(session_id))
            conversation.abort_turn(session_id=session_id, doctor_message_id=doctor_message_id)
            yield _sse(
                "error", {"code": "LLM_EMPTY_RESPONSE", "message": PATIENT_UNAVAILABLE_MESSAGE}
            )
            return

        patient_message_id = conversation.complete_turn(
            session_id=session_id, turn=turn, text=text
        )

        if idempotency_key:
            store_result(
                f"idem:msg:{session_id}:{idempotency_key}",
                {
                    "doctor_message_id": str(doctor_message_id),
                    "patient_message_id": str(patient_message_id),
                    "turn": turn,
                },
            )

        yield _sse("done", {"message_id": str(patient_message_id), "turn": turn})
    finally:
        lock_client.delete(lock_key)
