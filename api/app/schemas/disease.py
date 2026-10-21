import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DiseaseVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    name: str
    status: str
    created_at: datetime


class DiseaseSummaryResponse(BaseModel):
    id: uuid.UUID
    canonical_name: str
    latest_version: DiseaseVersionSummary | None = None


class RubricItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    question_text: str
    rationale: str | None
    weight: int
    critical: bool


class EvidenceResponse(BaseModel):
    page_number: int | None
    evidence_text: str


class DiagnosisOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    match_type: str


class DiseaseVersionDetail(BaseModel):
    id: uuid.UUID
    version: int
    name: str
    status: str
    aliases: list[str] | None
    demographics: dict | None
    symptoms: list | None
    exam_findings: list | None
    investigations: list | None
    differentials: list[str] | None
    red_flags: list[str] | None
    source_summary: dict | None
    created_at: datetime
    rubric_items: list[RubricItemResponse]
    evidence: list[EvidenceResponse]
    diagnosis_options: list[DiagnosisOptionResponse]


class DiseaseDetailResponse(BaseModel):
    id: uuid.UUID
    canonical_name: str
    versions: list[DiseaseVersionSummary]
    latest_version: DiseaseVersionDetail | None = None
