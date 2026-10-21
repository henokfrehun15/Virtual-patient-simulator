import uuid
from datetime import datetime

from pydantic import BaseModel


class RubricResultResponse(BaseModel):
    category: str
    question: str
    status: str
    weight: float
    critical: bool
    quality_score: float | None


class DiagnosisSummary(BaseModel):
    guess: str
    normalized_label: str | None
    verdict: str


class ReportResponse(BaseModel):
    session_id: uuid.UUID
    mode: str
    scenario_title: str
    completed_at: datetime | None
    overall_score: float | None
    history_score: float | None
    communication_score: float | None
    reasoning_score: float | None
    diagnosis_score: float | None
    critical_misses: list
    strengths: list
    gaps: list
    narrative: str | None
    recommended_focus: str | None
    diagnosis: DiagnosisSummary | None
    rubric_results: list[RubricResultResponse]


class ProgressCategoryResponse(BaseModel):
    category: str
    rolling_score: float | None
    rolling_attempts: int
    trend: str | None


class ProgressResponse(BaseModel):
    categories: list[ProgressCategoryResponse]
    diagnosis_accuracy: float | None
    sessions_completed: int


class SessionHistoryItem(BaseModel):
    id: uuid.UUID
    scenario_title: str
    mode: str
    overall_score: float | None
    diagnosis_verdict: str | None
    ended_at: datetime | None
