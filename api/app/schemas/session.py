import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StartSessionRequest(BaseModel):
    scenario_id: uuid.UUID
    mode: Literal["practice", "test"]
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class StreamMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    turn_number: int
    created_at: datetime


class SessionScenarioInfo(BaseModel):
    id: uuid.UUID
    title: str
    difficulty: str
    estimated_duration_minutes: int


class SessionPatientInfo(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: str | None = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    mode: str
    status: str
    current_turn: int
    turn_limit: int
    time_limit_seconds: int
    started_at: datetime
    last_activity_at: datetime | None
    ended_at: datetime | None
    completed_reason: str | None
    scenario: SessionScenarioInfo
    patient: SessionPatientInfo
    chief_complaint: str
    diagnosis: str | None = None
    messages: list[MessageResponse]
    examination_requests: list["ExaminationResponse"] = []
    investigation_requests: list["InvestigationResponse"] = []


class ExaminationRequest(BaseModel):
    exam_name: str = Field(min_length=2, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class ExaminationResponse(BaseModel):
    id: uuid.UUID
    exam_name: str
    result: dict
    created_at: datetime


class InvestigationRequest(BaseModel):
    test_name: str = Field(min_length=2, max_length=200)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class InvestigationResponse(BaseModel):
    id: uuid.UUID
    test_name: str
    result: dict
    created_at: datetime


class DiagnosisSubmitRequest(BaseModel):
    guess: str = Field(min_length=1, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class DiagnosisSubmitResponse(BaseModel):
    id: uuid.UUID
    guess: str
    verdict: str | None
    created_at: datetime


class CompleteSessionRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


SessionResponse.model_rebuild()
