import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class SessionRubricResult(UUIDMixin, Base):
    __tablename__ = "session_rubric_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_attempted', 'attempted', 'satisfied', 'partially_satisfied', "
            "'poorly_asked', 'unsafe', 'not_applicable')",
            name="ck_session_rubric_results_status",
        ),
        UniqueConstraint("session_id", "rubric_item_id", name="uq_session_rubric_results_session_item"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rubric_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rubric_items.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="not_attempted")
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric)
    weight: Mapped[Decimal | None] = mapped_column(Numeric)
    evidence_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    grader_reason: Mapped[str | None] = mapped_column(Text)
    grader_model: Mapped[str | None] = mapped_column(Text)
    grader_prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
