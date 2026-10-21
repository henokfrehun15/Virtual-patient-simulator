import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class Session(UUIDMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("mode IN ('practice', 'test')", name="ck_sessions_mode"),
        CheckConstraint(
            "status IN ('created', 'active', 'paused', 'completing', 'completed', 'abandoned', 'failed')",
            name="ck_sessions_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scenario_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    current_turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    turn_limit: Mapped[int | None] = mapped_column(Integer)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_reason: Mapped[str | None] = mapped_column(Text)


class SessionEvent(UUIDMixin, Base):
    __tablename__ = "session_events"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExaminationRequest(UUIDMixin, Base):
    __tablename__ = "examination_requests"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_name: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class InvestigationRequest(UUIDMixin, Base):
    __tablename__ = "investigation_requests"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_name: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DiagnosisAttempt(UUIDMixin, Base):
    __tablename__ = "diagnosis_attempts"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('correct', 'partial', 'incorrect')",
            name="ck_diagnosis_attempts_verdict",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guess: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_label: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    matched_option_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diagnosis_options.id", ondelete="SET NULL")
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
