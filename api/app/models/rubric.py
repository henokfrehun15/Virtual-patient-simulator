import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, utcnow


class RubricItem(UUIDMixin, Base):
    __tablename__ = "rubric_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('chief_complaint', 'hpi', 'pmh', 'medications', 'allergies', "
            "'family_history', 'social_history', 'ros', 'red_flag_screen', 'communication', "
            "'clinical_reasoning')",
            name="ck_rubric_items_category",
        ),
    )

    disease_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("disease_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DiagnosisOption(UUIDMixin, Base):
    __tablename__ = "diagnosis_options"
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('exact', 'synonym', 'partial', 'related', 'incorrect')",
            name="ck_diagnosis_options_match_type",
        ),
    )

    disease_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("disease_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
