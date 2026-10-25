from typing import Literal

from pydantic import BaseModel, Field


class LLMSettingsUpdate(BaseModel):
    provider: Literal["anthropic", "groq"] | None = None
    api_key: str | None = Field(default=None, min_length=20, max_length=300)
    clear_api_key: bool = False
    extraction_model: str | None = Field(default=None, max_length=100)
    scenario_model: str | None = Field(default=None, max_length=100)
    patient_model: str | None = Field(default=None, max_length=100)
    scoring_model: str | None = Field(default=None, max_length=100)
    feedback_model: str | None = Field(default=None, max_length=100)


class LLMSettingsResponse(BaseModel):
    provider: str
    api_key_set: bool
    api_key_source: str | None
    extraction_model: str
    scenario_model: str
    patient_model: str
    scoring_model: str
    feedback_model: str


class ModelTestResult(BaseModel):
    model: str
    ok: bool
    error: str | None


class LLMSettingsTestResponse(BaseModel):
    results: list[ModelTestResult]
