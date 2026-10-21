import json
import uuid

import redis
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
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
from app.models.report import SessionReport
from app.models.rubric import RubricItem
from app.models.score import SessionRubricResult
from app.models.session import DiagnosisAttempt
from app.models.user import User
from app.schemas.report import DiagnosisSummary, ReportResponse, RubricResultResponse
from app.schemas.session import (
    CompleteSessionRequest,
    DiagnosisSubmitRequest,
    DiagnosisSubmitResponse,
    ExaminationRequest,
    ExaminationResponse,
    InvestigationRequest,
    InvestigationResponse,
    SessionResponse,
    StartSessionRequest,
    StreamMessageRequest,
)
from app.services import conversation
from app.services import examinations as examination_service
from app.services import investigations as investigation_service
from app.services.completion import request_completion
from app.services.diagnosis import submit_diagnosis
from app.services.scoring import enqueue_message_scoring
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

    from app.services.session import ensure_session_active

    ensure_session_active(db, session)

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
            user_id=user.id,
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


@router.post(
    "/{session_id}/examinations",
    response_model=ExaminationResponse,
    status_code=201,
)
def request_examination(
    session_id: uuid.UUID,
    body: ExaminationRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExaminationResponse:
    session = get_owned_session_or_404(db, user, session_id)
    request_row = examination_service.request_examination(
        db, session, body.exam_name, body.idempotency_key
    )
    return ExaminationResponse(
        id=request_row.id,
        exam_name=request_row.exam_name,
        result=request_row.result or {},
        created_at=request_row.created_at,
    )


@router.post(
    "/{session_id}/investigations",
    response_model=InvestigationResponse,
    status_code=201,
)
def request_investigation(
    session_id: uuid.UUID,
    body: InvestigationRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InvestigationResponse:
    session = get_owned_session_or_404(db, user, session_id)
    request_row = investigation_service.request_investigation(
        db, session, body.test_name, body.idempotency_key
    )
    return InvestigationResponse(
        id=request_row.id,
        test_name=request_row.test_name,
        result=request_row.result or {},
        created_at=request_row.created_at,
    )


@router.post(
    "/{session_id}/diagnosis",
    response_model=DiagnosisSubmitResponse,
    status_code=201,
)
def submit_session_diagnosis(
    session_id: uuid.UUID,
    body: DiagnosisSubmitRequest,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiagnosisSubmitResponse:
    session = get_owned_session_or_404(db, user, session_id)
    attempt = submit_diagnosis(db, session, body.guess, body.idempotency_key)
    return DiagnosisSubmitResponse(
        id=attempt.id,
        guess=attempt.guess,
        verdict=attempt.verdict if session.mode == "practice" else None,
        created_at=attempt.created_at,
    )


@router.post("/{session_id}/complete", response_model=SessionResponse)
def complete_session(
    session_id: uuid.UUID,
    body: CompleteSessionRequest,
    response: Response,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    session = get_owned_session_or_404(db, user, session_id)
    already_done = session.status in ("completed", "completing")
    session = request_completion(db, session)
    if not already_done:
        response.status_code = status.HTTP_202_ACCEPTED
    return build_session_response(db, session)


@router.get("/{session_id}/report", response_model=ReportResponse)
def get_session_report(
    session_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportResponse:
    session = get_owned_session_or_404(db, user, session_id)
    if session.status != "completed":
        raise AppError("REPORT_NOT_READY", "The report is not ready yet.", status_code=404)

    report = db.scalar(
        select(SessionReport).where(SessionReport.session_id == session.id)
    )
    if report is None:
        raise AppError("REPORT_NOT_READY", "The report is not ready yet.", status_code=404)

    from app.services.scenario import scenario_title
    from app.models.scenario import Scenario, ScenarioPatientState

    scenario = db.get(Scenario, session.scenario_id)
    state_row = db.scalar(
        select(ScenarioPatientState).where(
            ScenarioPatientState.scenario_id == session.scenario_id
        )
    )
    state = state_row.state if state_row is not None else {}

    results = (
        db.execute(
            select(SessionRubricResult, RubricItem)
            .join(RubricItem, RubricItem.id == SessionRubricResult.rubric_item_id)
            .where(SessionRubricResult.session_id == session.id)
            .order_by(RubricItem.category, RubricItem.created_at)
        )
        .all()
    )

    last_attempt = (
        db.scalars(
            select(DiagnosisAttempt)
            .where(DiagnosisAttempt.session_id == session.id)
            .order_by(DiagnosisAttempt.created_at.desc())
            .limit(1)
        )
        .first()
    )

    def as_float(value) -> float | None:
        return float(value) if value is not None else None

    return ReportResponse(
        session_id=session.id,
        mode=session.mode,
        scenario_title=scenario_title(state),
        completed_at=session.ended_at,
        overall_score=as_float(report.overall_score),
        history_score=as_float(report.history_score),
        communication_score=as_float(report.communication_score),
        reasoning_score=as_float(report.reasoning_score),
        diagnosis_score=as_float(report.diagnosis_score),
        critical_misses=report.critical_misses or [],
        strengths=report.strengths or [],
        gaps=report.gaps or [],
        narrative=report.narrative,
        recommended_focus=report.recommended_focus,
        diagnosis=DiagnosisSummary(
            guess=last_attempt.guess,
            normalized_label=last_attempt.normalized_label,
            verdict=last_attempt.verdict,
        )
        if last_attempt is not None
        else None,
        rubric_results=[
            RubricResultResponse(
                category=item.category,
                question=item.question_text,
                status=result.status,
                weight=float(result.weight or item.weight or 1),
                critical=item.critical,
                quality_score=as_float(result.quality_score),
            )
            for result, item in results
        ],
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
    user_id: uuid.UUID,
    doctor_message_id: uuid.UUID,
    turn: int,
    system: str,
    user_content: str,
    idempotency_key: str | None,
    lock_key: str,
):
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    router = get_llm_router(user_id)
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
            logger.warning("patient_stream_failed", session_id=str(session_id), code=exc.code)
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

        try:
            enqueue_message_scoring(session_id, doctor_message_id, user_id)
        except Exception:
            logger.error("scoring_enqueue_failed", session_id=str(session_id))

        yield _sse("done", {"message_id": str(patient_message_id), "turn": turn})
    finally:
        lock_client.delete(lock_key)
