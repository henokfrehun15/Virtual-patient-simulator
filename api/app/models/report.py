import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class SessionReport(UUIDMixin, Base):
    __tablename__ = "session_reports"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric)
    history_score: Mapped[Decimal | None] = mapped_column(Numeric)
    communication_score: Mapped[Decimal | None] = mapped_column(Numeric)
    reasoning_score: Mapped[Decimal | None] = mapped_column(Numeric)
    diagnosis_score: Mapped[Decimal | None] = mapped_column(Numeric)
    critical_misses: Mapped[list | None] = mapped_column(JSONB)
    strengths: Mapped[list | None] = mapped_column(JSONB)
    gaps: Mapped[list | None] = mapped_column(JSONB)
    narrative: Mapped[str | None] = mapped_column(Text)
    recommended_focus: Mapped[str | None] = mapped_column(Text)
    generated_by_model: Mapped[str | None] = mapped_column(Text)
    generated_prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
