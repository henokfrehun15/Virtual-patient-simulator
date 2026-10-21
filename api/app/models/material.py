import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
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


class Material(UUIDMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (UniqueConstraint("course_id", "sha256", name="uq_materials_course_sha256"),)

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="materials")
    versions: Mapped[list["MaterialVersion"]] = relationship(
        back_populates="material", cascade="all, delete-orphan", passive_deletes=True
    )


class MaterialVersion(UUIDMixin, Base):
    __tablename__ = "material_versions"
    __table_args__ = (
        UniqueConstraint("material_id", "version", name="uq_material_versions_material_version"),
        CheckConstraint(
            "status IN ('uploaded', 'extracting', 'extracted', 'failed')",
            name="ck_material_versions_status",
        ),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    material: Mapped["Material"] = relationship(back_populates="versions")
    pages: Mapped[list["DocumentPage"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    chunks: Mapped[list["DocumentChunk"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    jobs: Mapped[list["ExtractionJob"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class DocumentPage(UUIDMixin, Base):
    __tablename__ = "document_pages"

    material_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("material_version_id", "chunk_index", name="uq_document_chunks_version_index"),
    )

    material_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExtractionJob(UUIDMixin, Base):
    __tablename__ = "extraction_jobs"

    material_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
