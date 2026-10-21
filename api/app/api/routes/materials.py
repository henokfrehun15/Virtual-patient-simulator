import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import PaginationParams, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.ratelimit import enforce_rate_limit
from app.models.course import Course
from app.models.material import ExtractionJob, Material, MaterialVersion
from app.models.user import User
from app.schemas.common import Page
from app.schemas.material import (
    ExtractionJobResponse,
    MaterialResponse,
    MaterialStatusResponse,
    MaterialVersionResponse,
)
from app.services.ingestion import enqueue_extraction, upload_material, validate_pdf_upload

logger = get_logger("app.materials")

upload_router = APIRouter(prefix="/api/v1/courses/{course_id}/materials", tags=["materials"])
router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


def get_material_or_404(db: DbSession, material_id: uuid.UUID) -> Material:
    material = db.get(Material, material_id)
    if material is None:
        raise AppError("MATERIAL_NOT_FOUND", "Material not found.", status_code=404)
    return material


def latest_version(db: DbSession, material_id: uuid.UUID) -> MaterialVersion | None:
    return db.scalar(
        select(MaterialVersion)
        .where(MaterialVersion.material_id == material_id)
        .order_by(MaterialVersion.version.desc())
        .limit(1)
    )


def material_response(db: DbSession, material: Material) -> MaterialResponse:
    response = MaterialResponse.model_validate(material)
    latest = latest_version(db, material.id)
    if latest is not None:
        response.latest_version = MaterialVersionResponse.model_validate(latest)
    return response


@upload_router.post("", response_model=MaterialResponse, status_code=201)
def upload_course_material(
    course_id: uuid.UUID,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MaterialResponse:
    settings = get_settings()
    enforce_rate_limit(
        "material_upload",
        str(user.id),
        settings.upload_rate_limit_count,
        settings.upload_rate_limit_window_seconds,
    )

    course = db.get(Course, course_id)
    if course is None:
        raise AppError("COURSE_NOT_FOUND", "Course not found.", status_code=404)

    max_bytes = settings.max_pdf_size_mb * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise AppError(
            "MATERIAL_TOO_LARGE",
            f"Maximum file size is {settings.max_pdf_size_mb} MB.",
            status_code=413,
        )

    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(
            "MATERIAL_TOO_LARGE",
            f"Maximum file size is {settings.max_pdf_size_mb} MB.",
            status_code=413,
        )

    filename = file.filename or ""
    validate_pdf_upload(filename=filename, content_type=file.content_type, data=data)

    material, version = upload_material(
        db,
        course=course,
        user=user,
        filename=filename,
        content_type=file.content_type,
        data=data,
    )

    try:
        enqueue_extraction(version.id)
    except Exception:
        logger.error("extraction_enqueue_failed", material_version_id=str(version.id))

    return material_response(db, material)


@upload_router.get("", response_model=Page[MaterialResponse])
def list_course_materials(
    course_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[MaterialResponse]:
    course = db.get(Course, course_id)
    if course is None:
        raise AppError("COURSE_NOT_FOUND", "Course not found.", status_code=404)

    total = (
        db.scalar(select(func.count()).select_from(Material).where(Material.course_id == course.id))
        or 0
    )
    rows = db.scalars(
        select(Material)
        .where(Material.course_id == course.id)
        .order_by(Material.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return Page(
        items=[material_response(db, row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{material_id}", response_model=MaterialResponse)
def get_material(
    material_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MaterialResponse:
    return material_response(db, get_material_or_404(db, material_id))


@router.get("/{material_id}/status", response_model=MaterialStatusResponse)
def get_material_status(
    material_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MaterialStatusResponse:
    material = get_material_or_404(db, material_id)
    versions = db.scalars(
        select(MaterialVersion)
        .where(MaterialVersion.material_id == material.id)
        .order_by(MaterialVersion.version)
    ).all()
    jobs = (
        db.scalars(
            select(ExtractionJob)
            .where(
                ExtractionJob.material_version_id.in_([version.id for version in versions])
            )
            .order_by(ExtractionJob.created_at)
        ).all()
        if versions
        else []
    )
    return MaterialStatusResponse(
        material=material_response(db, material),
        versions=[MaterialVersionResponse.model_validate(version) for version in versions],
        jobs=[ExtractionJobResponse.model_validate(job) for job in jobs],
    )
