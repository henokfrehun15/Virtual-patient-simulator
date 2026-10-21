import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, utcnow


class Scenario(UUIDMixin, Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("disease_version_id", "version", name="uq_scenarios_disease_version_version"),
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_scenarios_difficulty"),
        CheckConstraint(
            "status IN ('draft', 'validated', 'published', 'retired')",
            name="ck_scenarios_status",
        ),
    )

    disease_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("disease_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    scenario_seed: Mapped[str] = mapped_column(Text, nullable=False)
    generator_model: Mapped[str | None] = mapped_column(Text)
    generator_prompt_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    disease_version: Mapped["DiseaseVersion"] = relationship(back_populates="scenarios")
    patient_state: Mapped[Optional["ScenarioPatientState"]] = relationship(
        back_populates="scenario", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    investigations: Mapped[list["ScenarioInvestigation"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    examinations: Mapped[list["ScenarioExamination"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class ScenarioPatientState(UUIDMixin, Base):
    __tablename__ = "scenario_patient_state"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    scenario: Mapped["Scenario"] = relationship(back_populates="patient_state")


class ScenarioInvestigation(UUIDMixin, Base):
    __tablename__ = "scenario_investigations"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_name: Mapped[str] = mapped_column(Text, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    cost_weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ScenarioExamination(UUIDMixin, Base):
    __tablename__ = "scenario_examinations"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_name: Mapped[str] = mapped_column(Text, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    findings: Mapped[dict | None] = mapped_column(JSONB)
