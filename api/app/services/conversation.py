import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.prompts import patient as patient_prompts
from app.models.message import Message
from app.models.scenario import ScenarioPatientState
from app.models.session import Session as SessionModel
from app.services.session import record_session_event

logger = get_logger("app.conversation")

PATIENT_VISIBLE_STATE_KEYS = (
    "demographics",
    "chief_complaint",
    "hpi",
    "pmh",
    "medications",
    "allergies",
    "family_history",
    "social_history",
    "ros",
    "red_flags",
    "communication_style",
    "emotional_state",
)


def patient_state_for_prompt(state: dict) -> dict:
    return {key: state[key] for key in PATIENT_VISIBLE_STATE_KEYS if key in state}


@dataclass
class PreparedTurn:
    doctor_message_id: uuid.UUID
    turn: int
    system: str
    user_content: str


def prepare_turn(db: DbSession, session: SessionModel, content: str) -> PreparedTurn:
    settings = get_settings()
    turn = session.current_turn + 1

    doctor_message = Message(
        session_id=session.id, role="doctor", content=content, turn_number=turn
    )
    db.add(doctor_message)
    session.last_activity_at = datetime.now(timezone.utc)
    db.flush()
    record_session_event(
        db,
        session.id,
        "student_message_created",
        {"message_id": str(doctor_message.id), "turn": turn},
    )
    db.commit()

    state_row = db.scalar(
        select(ScenarioPatientState).where(ScenarioPatientState.scenario_id == session.scenario_id)
    )
    state = patient_state_for_prompt(state_row.state) if state_row is not None else {}

    recent = (
        db.scalars(
            select(Message)
            .where(Message.session_id == session.id, Message.id != doctor_message.id)
            .order_by(Message.created_at.desc())
            .limit(settings.conversation_context_turns * 2)
        )
        .all()
    )
    recent.reverse()

    return PreparedTurn(
        doctor_message_id=doctor_message.id,
        turn=turn,
        system=patient_prompts.SYSTEM_PROMPT,
        user_content=patient_prompts.build_user_content(state, recent, content),
    )


def complete_turn(
    *,
    session_id: uuid.UUID,
    turn: int,
    text: str,
) -> uuid.UUID:
    with SessionLocal() as db:
        session = db.get(SessionModel, session_id)
        if session is None:
            raise AppError("SESSION_NOT_FOUND", "Session not found.", status_code=404)
        patient_message = Message(
            session_id=session_id, role="patient", content=text, turn_number=turn
        )
        db.add(patient_message)
        session.current_turn = turn
        session.last_activity_at = datetime.now(timezone.utc)
        db.flush()
        record_session_event(
            db,
            session_id,
            "patient_message_created",
            {"message_id": str(patient_message.id), "turn": turn},
        )
        db.commit()
        return patient_message.id


def abort_turn(*, session_id: uuid.UUID, doctor_message_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        message = db.get(Message, doctor_message_id)
        if message is not None and message.session_id == session_id:
            db.delete(message)
            db.commit()
    logger.info(
        "turn_aborted", session_id=str(session_id), doctor_message_id=str(doctor_message_id)
    )
