import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, utcnow


class Disease(UUIDMixin, Base):
    __tablename__ = "diseases"

    canonical_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    versions: Mapped[list["DiseaseVersion"]] = relationship(
        back_populates="disease", cascade="all, delete-orphan", passive_deletes=True
    )


class DiseaseVersion(UUIDMixin, Base):
    __tablename__ = "disease_versions"
    __table_args__ = (
        UniqueConstraint("disease_id", "version", name="uq_disease_versions_disease_version"),
        CheckConstraint(
            "status IN ('draft', 'validated', 'published', 'retired')",
            name="ck_disease_versions_status",
        ),
    )

    disease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    demographics: Mapped[dict | None] = mapped_column(JSONB)
    symptoms: Mapped[list | None] = mapped_column(JSONB)
    exam_findings: Mapped[list | None] = mapped_column(JSONB)
    investigations: Mapped[list | None] = mapped_column(JSONB)
    differentials: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    red_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    history_checklist: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    source_summary: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    disease: Mapped["Disease"] = relationship(back_populates="versions")
    evidence: Mapped[list["DiseaseSourceEvidence"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    rubric_items: Mapped[list["RubricItem"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    diagnosis_options: Mapped[list["DiagnosisOption"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    scenarios: Mapped[list["Scenario"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class DiseaseSourceEvidence(UUIDMixin, Base):
    __tablename__ = "disease_source_evidence"

    disease_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("disease_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
