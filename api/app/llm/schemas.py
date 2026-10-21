from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SymptomFrequency(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"


class DiscoveredDisease(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_pages: list[int] = Field(default_factory=list)
    mention_context: str = Field(default="", max_length=2000)


class DiseaseDiscoveryResult(BaseModel):
    diseases: list[DiscoveredDisease] = Field(default_factory=list)


class Demographics(BaseModel):
    age_range: str | None = None
    sex_bias: str | None = None
    risk_factors: list[str] = Field(default_factory=list)


class SymptomFinding(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    frequency: SymptomFrequency = SymptomFrequency.COMMON


class InvestigationFinding(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    typical_result: str = Field(default="", max_length=1000)


class HistoryChecklistItem(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(default="", max_length=2000)
    weight: int = Field(default=1, ge=1, le=5)
    critical: bool = False


class DiseaseProfileResult(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    demographics: Demographics = Field(default_factory=Demographics)
    symptoms: list[SymptomFinding] = Field(default_factory=list)
    exam_findings: list[SymptomFinding] = Field(default_factory=list)
    investigations: list[InvestigationFinding] = Field(default_factory=list)
    differentials: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    history_checklist: list[HistoryChecklistItem] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


class RubricCategory(str, Enum):
    CHIEF_COMPLAINT = "chief_complaint"
    HPI = "hpi"
    PMH = "pmh"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    FAMILY_HISTORY = "family_history"
    SOCIAL_HISTORY = "social_history"
    ROS = "ros"
    RED_FLAG_SCREEN = "red_flag_screen"
    COMMUNICATION = "communication"
    CLINICAL_REASONING = "clinical_reasoning"


class RubricItemDraft(BaseModel):
    category: RubricCategory
    question_text: str = Field(min_length=5, max_length=1000)
    rationale: str = Field(default="", max_length=2000)
    weight: int = Field(default=1, ge=1, le=5)
    critical: bool = False


class RubricExtractionResult(BaseModel):
    items: list[RubricItemDraft] = Field(default_factory=list)


class ScenarioDemographics(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0, le=120)
    sex: str = Field(min_length=1, max_length=30)
    occupation: str | None = None


class ScenarioExamination(BaseModel):
    exam_name: str = Field(min_length=1, max_length=200)
    findings: dict[str, Any] = Field(default_factory=dict)


class ScenarioInvestigation(BaseModel):
    test_name: str = Field(min_length=1, max_length=200)
    result: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    cost_weight: int = Field(default=1, ge=1, le=10)


class ScenarioGenerationResult(BaseModel):
    demographics: ScenarioDemographics
    chief_complaint: str = Field(min_length=1, max_length=300)
    hpi: dict[str, Any] = Field(default_factory=dict)
    pmh: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    social_history: dict[str, Any] = Field(default_factory=dict)
    ros: dict[str, Any] = Field(default_factory=dict)
    red_flags: dict[str, bool] = Field(default_factory=dict)
    communication_style: str = Field(min_length=1, max_length=500)
    emotional_state: str = Field(min_length=1, max_length=300)
    examinations: list[ScenarioExamination] = Field(default_factory=list)
    investigations: list[ScenarioInvestigation] = Field(default_factory=list)
