import uuid
from datetime import datetime

from pydantic import BaseModel


class ScenarioDiseaseInfo(BaseModel):
    id: uuid.UUID
    canonical_name: str
    name: str


class ScenarioPatientInfo(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: str | None = None


class ScenarioSummaryResponse(BaseModel):
    id: uuid.UUID
    difficulty: str
    title: str
    estimated_duration_minutes: int
    status: str
    created_at: datetime


class ScenarioDetailResponse(ScenarioSummaryResponse):
    disease: ScenarioDiseaseInfo
    disease_version: int
    chief_complaint: str
    patient: ScenarioPatientInfo
    modes: list[str]
