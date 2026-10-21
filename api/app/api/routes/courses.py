import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import PaginationParams, get_current_user
from app.core.database import get_db
from app.core.errors import AppError
from app.models.course import Course
from app.models.user import User
from app.schemas.common import Page
from app.schemas.course import CourseCreate, CourseResponse
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


def get_course_or_404(db: DbSession, course_id: uuid.UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise AppError("COURSE_NOT_FOUND", "Course not found.", status_code=404)
    return course


@router.get("", response_model=Page[CourseResponse])
def list_courses(
    pagination: PaginationParams = Depends(),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[CourseResponse]:
    total = db.scalar(select(func.count()).select_from(Course)) or 0
    rows = db.scalars(
        select(Course)
        .order_by(Course.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return Page(
        items=[CourseResponse.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=CourseResponse, status_code=201)
def create_course(
    body: CourseCreate,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseResponse:
    course = Course(name=body.name, description=body.description)
    db.add(course)
    db.flush()
    record_audit_event(
        db,
        user_id=user.id,
        action="course.created",
        resource_type="course",
        resource_id=course.id,
        metadata={"name": body.name},
    )
    db.commit()
    db.refresh(course)
    return CourseResponse.model_validate(course)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: uuid.UUID,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CourseResponse:
    return CourseResponse.model_validate(get_course_or_404(db, course_id))
