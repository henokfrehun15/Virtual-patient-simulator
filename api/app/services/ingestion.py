import hashlib
import uuid
from datetime import datetime, timezone

import fitz
import redis
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.course import Course
from app.models.material import DocumentChunk, DocumentPage, ExtractionJob, Material, MaterialVersion
from app.models.user import User
from app.services import extraction
from app.services.audit import record_audit_event
from app.services.storage import generate_storage_key, get_storage

logger = get_logger("app.ingestion")

PDF_SIGNATURE = b"%PDF-"
EXTRACTION_LOCK_TTL_SECONDS = 1800
MAX_FILENAME_LENGTH = 255


def validate_pdf_upload(*, filename: str | None, content_type: str | None, data: bytes) -> int:
    settings = get_settings()
    max_bytes = settings.max_pdf_size_mb * 1024 * 1024

    if not filename or not filename.lower().endswith(".pdf"):
        raise AppError("MATERIAL_INVALID", "Only PDF files are accepted.", status_code=400)
    if len(filename) > MAX_FILENAME_LENGTH:
        raise AppError("MATERIAL_INVALID", "Filename is too long.", status_code=400)
    if content_type is not None and content_type != "application/pdf":
        raise AppError("MATERIAL_INVALID", "Only PDF files are accepted.", status_code=400)
    if not data.startswith(PDF_SIGNATURE):
        raise AppError("MATERIAL_INVALID", "The file is not a valid PDF.", status_code=400)
    if len(data) > max_bytes:
        raise AppError(
            "MATERIAL_TOO_LARGE",
            f"Maximum file size is {settings.max_pdf_size_mb} MB.",
            status_code=413,
        )

    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            page_count = document.page_count
    except Exception as exc:
        raise AppError("MATERIAL_INVALID", "The file is not a valid PDF.", status_code=400) from exc

    if page_count == 0:
        raise AppError("MATERIAL_INVALID", "The PDF contains no pages.", status_code=400)
    if page_count > settings.max_pdf_pages:
        raise AppError(
            "MATERIAL_INVALID",
            f"Maximum page count is {settings.max_pdf_pages}.",
            status_code=400,
        )

    return page_count


def upload_material(
    db: DbSession,
    *,
    course: Course,
    user: User,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> tuple[Material, MaterialVersion]:
    sha256 = hashlib.sha256(data).hexdigest()

    existing = db.scalar(
        select(Material).where(Material.course_id == course.id, Material.sha256 == sha256)
    )
    if existing is not None:
        raise AppError(
            "MATERIAL_DUPLICATE",
            "This file has already been uploaded to this course.",
            status_code=409,
        )

    storage_key = generate_storage_key("materials")
    get_storage().save(storage_key, data)

    material = Material(
        course_id=course.id,
        filename=filename,
        mime_type=content_type or "application/pdf",
        size_bytes=len(data),
        sha256=sha256,
        storage_key=storage_key,
        created_by=user.id,
    )
    db.add(material)
    db.flush()

    version_count = (
        db.scalar(
            select(func.count())
            .select_from(MaterialVersion)
            .where(MaterialVersion.material_id == material.id)
        )
        or 0
    )
    version = MaterialVersion(material_id=material.id, version=version_count + 1, status="uploaded")
    db.add(version)
    db.flush()

    db.add(ExtractionJob(material_version_id=version.id, job_type="extract", status="pending"))
    record_audit_event(
        db,
        user_id=user.id,
        action="material.uploaded",
        resource_type="material",
        resource_id=material.id,
        metadata={"filename": filename, "sha256": sha256, "size_bytes": len(data)},
    )
    db.commit()
    db.refresh(material)
    db.refresh(version)
    return material, version


def enqueue_extraction(material_version_id: uuid.UUID) -> None:
    from app.tasks.ingestion import extract_material

    extract_material.delay(str(material_version_id))


def run_extraction(material_version_id: uuid.UUID) -> None:
    settings = get_settings()
    lock_client = redis.Redis.from_url(settings.redis_url)
    lock_key = f"lock:extract:{material_version_id}"
    acquired = lock_client.set(lock_key, "1", nx=True, ex=EXTRACTION_LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("extraction_skipped_locked", material_version_id=str(material_version_id))
        return

    try:
        with SessionLocal() as db:
            version = db.get(MaterialVersion, material_version_id)
            if version is None:
                logger.error(
                    "extraction_version_missing", material_version_id=str(material_version_id)
                )
                return
            if version.status == "extracted":
                logger.info(
                    "extraction_skipped_completed", material_version_id=str(material_version_id)
                )
                return

            job = db.scalar(
                select(ExtractionJob).where(
                    ExtractionJob.material_version_id == version.id,
                    ExtractionJob.job_type == "extract",
                )
            )
            material = db.get(Material, version.material_id)
            if material is None:
                logger.error(
                    "extraction_material_missing", material_version_id=str(material_version_id)
                )
                return

            now = datetime.now(timezone.utc)
            version.status = "extracting"
            if job is not None:
                job.status = "running"
                job.started_at = now
                job.attempts += 1
            db.commit()

            db.execute(
                delete(DocumentChunk).where(DocumentChunk.material_version_id == version.id)
            )
            db.execute(
                delete(DocumentPage).where(DocumentPage.material_version_id == version.id)
            )
            db.commit()

            pdf_bytes = get_storage().read(material.storage_key)
            pages = extraction.extract_pages(pdf_bytes)
            chunks = extraction.chunk_pages(
                pages, settings.chunk_target_chars, settings.chunk_overlap_chars
            )

            for page in pages:
                db.add(
                    DocumentPage(
                        material_version_id=version.id,
                        page_number=page.page_number,
                        text=page.text,
                        ocr_used=page.ocr_used,
                        meta=page.meta,
                    )
                )
            for chunk in chunks:
                db.add(
                    DocumentChunk(
                        material_version_id=version.id,
                        page_start=chunk.page_number,
                        page_end=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                    )
                )

            version.status = "extracted"
            if job is not None:
                job.status = "succeeded"
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(
                "extraction_completed",
                material_version_id=str(material_version_id),
                pages=len(pages),
                chunks=len(chunks),
            )
    finally:
        lock_client.delete(lock_key)


def mark_extraction_failed(material_version_id: uuid.UUID, error_message: str) -> None:
    try:
        with SessionLocal() as db:
            version = db.get(MaterialVersion, material_version_id)
            if version is None:
                return
            version.status = "failed"
            job = db.scalar(
                select(ExtractionJob).where(
                    ExtractionJob.material_version_id == version.id,
                    ExtractionJob.job_type == "extract",
                )
            )
            if job is not None:
                job.status = "failed"
                job.error_message = error_message[:2000]
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.error(
                "extraction_failed",
                material_version_id=str(material_version_id),
                error=error_message,
            )
    except Exception:
        logger.exception(
            "mark_extraction_failed_error", material_version_id=str(material_version_id)
        )
