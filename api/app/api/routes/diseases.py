import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import PaginationParams, get_current_user
from app.core.database import get_db
from app.core.errors import AppError
from app.models.course import Course
from app.models.disease import Disease, DiseaseSourceEvidence, DiseaseVersion
from app.models.material import DocumentChunk, Material, MaterialVersion
from app.models.rubric import DiagnosisOption, RubricItem
from app.models.user import User
from app.schemas.common import Page
from app.schemas.disease import (
    DiseaseDetailResponse,
    DiseaseSummaryResponse,
    DiseaseVersionDetail,
    DiseaseVersionSummary,
    DiagnosisOptionResponse,
    EvidenceResponse,
    RubricItemResponse,
)

router = APIRouter(prefix="/api/v1/diseases", tags=["diseases"])
course_router = APIRouter(prefix="/api/v1/courses/{course_id}/diseases", tags=["diseases"])


def _latest_version(db: DbSession, disease_id: uuid.UUID) -> DiseaseVersion | None:
    return db.scalar(
        select(DiseaseVersion)
        .where(DiseaseVersion.disease_id == disease_id)
        .order_by(DiseaseVersion.version.desc())
        .limit(1)
    )


def _course_disease_ids_subquery(course_id: uuid.UUID):
    return (
        select(Disease.id)
        .join(DiseaseVersion, DiseaseVersion.disease_id == Disease.id)
        .join(DiseaseSourceEvidence, DiseaseSourceEvidence.disease_version_id == DiseaseVersion.id)
        .join(DocumentChunk, DocumentChunk.id == DiseaseSourceEvidence.chunk_id)
        .join(MaterialVersion, MaterialVersion.id == DocumentChunk.material_version_id)
        .join(Material, Material.id == MaterialVersion.material_id)
        .where(Material.course_id == course_id)
    )


@course_router.get("", response_model=Page[DiseaseSummaryResponse])
def list_course_diseases(
    course_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[DiseaseSummaryResponse]:
    course = db.get(Course, course_id)
    if course is None:
        raise AppError("COURSE_NOT_FOUND", "Course not found.", status_code=404)

    subquery = _course_disease_ids_subquery(course_id)
    total = (
        db.scalar(select(func.count()).select_from(Disease).where(Disease.id.in_(subquery))) or 0
    )
    rows = (
        db.scalars(
            select(Disease)
            .where(Disease.id.in_(subquery))
            .order_by(Disease.canonical_name)
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .unique()
        .all()
    )

    items: list[DiseaseSummaryResponse] = []
    for disease in rows:
        summary = DiseaseSummaryResponse(
            id=disease.id, canonical_name=disease.canonical_name
        )
        latest = _latest_version(db, disease.id)
        if latest is not None:
            summary.latest_version = DiseaseVersionSummary.model_validate(latest)
        items.append(summary)

    return Page(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{disease_id}", response_model=DiseaseDetailResponse)
def get_disease(
    disease_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiseaseDetailResponse:
    disease = db.get(Disease, disease_id)
    if disease is None:
        raise AppError("DISEASE_NOT_FOUND", "Disease not found.", status_code=404)

    versions = (
        db.scalars(
            select(DiseaseVersion)
            .where(DiseaseVersion.disease_id == disease.id)
            .order_by(DiseaseVersion.version)
        )
        .unique()
        .all()
    )

    detail = DiseaseDetailResponse(
        id=disease.id,
        canonical_name=disease.canonical_name,
        versions=[DiseaseVersionSummary.model_validate(version) for version in versions],
    )

    if versions:
        latest = versions[-1]
        rubric_items = (
            db.scalars(
                select(RubricItem)
                .where(RubricItem.disease_version_id == latest.id)
                .order_by(RubricItem.category, RubricItem.created_at)
            )
            .unique()
            .all()
        )
        evidence = (
            db.scalars(
                select(DiseaseSourceEvidence)
                .where(DiseaseSourceEvidence.disease_version_id == latest.id)
                .order_by(DiseaseSourceEvidence.created_at)
            )
            .unique()
            .all()
        )
        options = (
            db.scalars(
                select(DiagnosisOption).where(
                    DiagnosisOption.disease_version_id == latest.id
                )
            )
            .unique()
            .all()
        )

        detail.latest_version = DiseaseVersionDetail(
            id=latest.id,
            version=latest.version,
            name=latest.name,
            status=latest.status,
            aliases=latest.aliases,
            demographics=latest.demographics,
            symptoms=latest.symptoms,
            exam_findings=latest.exam_findings,
            investigations=latest.investigations,
            differentials=latest.differentials,
            red_flags=latest.red_flags,
            source_summary=latest.source_summary,
            created_at=latest.created_at,
            rubric_items=[RubricItemResponse.model_validate(item) for item in rubric_items],
            evidence=[
                EvidenceResponse(
                    page_number=item.page_number, evidence_text=item.evidence_text
                )
                for item in evidence
            ],
            diagnosis_options=[
                DiagnosisOptionResponse.model_validate(option) for option in options
            ],
        )

    return detail
