import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MaterialVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    status: str
    created_at: datetime


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    latest_version: MaterialVersionResponse | None = None


class ExtractionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    attempts: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class MaterialStatusResponse(BaseModel):
    material: MaterialResponse
    versions: list[MaterialVersionResponse]
    jobs: list[ExtractionJobResponse]
