import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import materials as materials_routes
from app.core.database import SessionLocal
from app.llm.schemas import (
    Demographics,
    DiseaseDiscoveryResult,
    DiseaseProfileResult,
    DiscoveredDisease,
    InvestigationFinding,
    RubricCategory,
    RubricExtractionResult,
    RubricItemDraft,
    ScenarioDemographics,
    ScenarioExamination,
    ScenarioGenerationResult,
    ScenarioInvestigation,
    SymptomFinding,
)
from app.main import app
from app.models.scenario import Scenario, ScenarioExamination as ScenarioExaminationModel
from app.models.scenario import ScenarioInvestigation as ScenarioInvestigationModel
from app.models.scenario import ScenarioPatientState
from app.services import clinical_content as clinical_content_module
from app.services import ingestion as ingestion_service
from app.services import scenario as scenario_module


class FakeRouter:
    def __init__(
        self, *, scenario: ScenarioGenerationResult, disease_name: str = "Pneumonia"
    ) -> None:
        self.scenario = scenario
        self.disease_name = disease_name
        self.scenario_calls = 0

    def model_for_task(self, task: str) -> str:
        return f"fake-{task}"

    def generate(self, task: str, request) -> object:
        if request.schema_model is DiseaseDiscoveryResult:
            return DiseaseDiscoveryResult(
                diseases=[
                    DiscoveredDisease(
                        name=self.disease_name,
                        source_pages=[1],
                        mention_context=f"{self.disease_name} is discussed in the course text.",
                    )
                ]
            )
        if request.schema_model is DiseaseProfileResult:
            return DiseaseProfileResult(
                name=self.disease_name,
                aliases=["Community-acquired pneumonia"],
                demographics=Demographics(age_range="all ages"),
                symptoms=[SymptomFinding(name="cough", frequency="common")],
                exam_findings=[SymptomFinding(name="crackles", frequency="common")],
                investigations=[
                    InvestigationFinding(name="chest x-ray", typical_result="consolidation")
                ],
                differentials=["acute bronchitis"],
                red_flags=["severe respiratory distress"],
                history_checklist=[],
                source_pages=[1],
            )
        if request.schema_model is RubricExtractionResult:
            return RubricExtractionResult(
                items=[
                    RubricItemDraft(
                        category=RubricCategory.RED_FLAG_SCREEN,
                        question_text="Are you having any trouble breathing at rest?",
                        rationale="Screens for respiratory distress",
                        weight=5,
                        critical=True,
                    )
                ]
            )
        if request.schema_model is ScenarioGenerationResult:
            self.scenario_calls += 1
            return self.scenario
        raise AssertionError(f"Unexpected schema model: {request.schema_model}")


def make_scenario_generation(*, consistent: bool = True) -> ScenarioGenerationResult:
    return ScenarioGenerationResult(
        demographics=ScenarioDemographics(
            name="Sarah Johnson", age=34, sex="female", occupation="teacher"
        ),
        chief_complaint="cough and fever",
        hpi={"onset": "3 days ago", "severity": 6},
        pmh=["asthma"],
        medications=["salbutamol inhaler"],
        allergies=["penicillin"],
        family_history=[],
        social_history={"smoking": "never"},
        ros={"respiratory": "productive cough", "general": "fatigue"},
        red_flags={"severe respiratory distress": False} if consistent else {},
        communication_style="cooperative but worried",
        emotional_state="anxious",
        examinations=(
            [
                ScenarioExamination(
                    exam_name="respiratory examination",
                    findings={"auscultation": "crackles in the right lower zone"},
                )
            ]
            if consistent
            else []
        ),
        investigations=[
            ScenarioInvestigation(
                test_name="chest x-ray",
                result={"finding": "right lower lobe consolidation"},
            )
        ],
    )


def _setup_published_disease(client: TestClient, unique: str, pdf_bytes: bytes) -> tuple[str, dict]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"scenario-{unique}@example.com",
            "password": "password123",
            "full_name": "Scenario Student",
        },
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    course = client.post(
        "/api/v1/courses", json={"name": f"Scenario Course {unique}"}, headers=headers
    )
    course_id = course.json()["id"]

    upload = client.post(
        f"/api/v1/courses/{course_id}/materials",
        files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    material_id = upload.json()["id"]
    status = client.get(f"/api/v1/materials/{material_id}/status", headers=headers).json()
    version_id = uuid.UUID(status["versions"][0]["id"])

    ingestion_service.run_extraction(version_id)
    clinical_content_module.run_clinical_content(version_id)

    diseases = client.get(f"/api/v1/courses/{course_id}/diseases", headers=headers).json()
    disease = diseases["items"][0]
    return disease["id"], headers


def test_scenario_generation_publishes_scenario(pdf_bytes: bytes, monkeypatch) -> None:
    unique = uuid.uuid4().hex[:8]
    disease_name = f"Pneumonia {unique}"
    fake = FakeRouter(
        scenario=make_scenario_generation(consistent=True), disease_name=disease_name
    )
    monkeypatch.setattr(ingestion_service, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(materials_routes, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(clinical_content_module, "get_llm_router", lambda: fake)
    monkeypatch.setattr(scenario_module, "get_llm_router", lambda: fake)

    with TestClient(app) as client:
        disease_id, headers = _setup_published_disease(client, unique, pdf_bytes)

        detail = client.get(f"/api/v1/diseases/{disease_id}", headers=headers).json()
        disease_version_id = uuid.UUID(detail["latest_version"]["id"])

        scenario_module.run_scenario_generation(disease_version_id, "medium")

        scenarios = client.get(
            f"/api/v1/diseases/{disease_id}/scenarios", headers=headers
        ).json()
        assert scenarios["total"] == 1
        summary = scenarios["items"][0]
        assert summary["difficulty"] == "medium"
        assert summary["status"] == "published"
        assert summary["title"] == "34-year-old female with cough and fever"
        assert summary["estimated_duration_minutes"] > 0

        scenario_detail = client.get(
            f"/api/v1/scenarios/{summary['id']}", headers=headers
        ).json()
        assert scenario_detail["disease"]["name"] == disease_name
        assert scenario_detail["patient"]["name"] == "Sarah Johnson"
        assert scenario_detail["patient"]["age"] == 34
        assert scenario_detail["chief_complaint"] == "cough and fever"
        assert scenario_detail["modes"] == ["practice", "test"]

        response_keys = set(scenario_detail.keys())
        assert "hpi" not in response_keys
        assert "red_flags" not in response_keys
        assert "investigation_results" not in response_keys
        assert "physical_exam" not in response_keys
        assert "scenario_seed" not in response_keys

        with SessionLocal() as db:
            scenario_id = uuid.UUID(summary["id"])
            state = db.scalar(
                select(ScenarioPatientState).where(
                    ScenarioPatientState.scenario_id == scenario_id
                )
            )
            assert state is not None
            assert state.state["hpi"]["onset"] == "3 days ago"
            assert state.state["red_flags"] == {"severe respiratory distress": False}
            assert state.state["_meta"]["validation"]["passed"] is True

            exam_count = db.scalar(
                select(func.count())
                .select_from(ScenarioExaminationModel)
                .where(ScenarioExaminationModel.scenario_id == scenario_id)
            )
            investigation_count = db.scalar(
                select(func.count())
                .select_from(ScenarioInvestigationModel)
                .where(ScenarioInvestigationModel.scenario_id == scenario_id)
            )
        assert exam_count == 1
        assert investigation_count == 1

        calls_before = fake.scenario_calls
        scenario_module.run_scenario_generation(disease_version_id, "medium")
        assert fake.scenario_calls == calls_before


def test_scenario_validation_failure_keeps_draft(pdf_bytes: bytes, monkeypatch) -> None:
    unique = uuid.uuid4().hex[:8]
    fake = FakeRouter(
        scenario=make_scenario_generation(consistent=False),
        disease_name=f"Acute Bronchitis {unique}",
    )
    monkeypatch.setattr(ingestion_service, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(materials_routes, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(clinical_content_module, "get_llm_router", lambda: fake)
    monkeypatch.setattr(scenario_module, "get_llm_router", lambda: fake)

    with TestClient(app) as client:
        disease_id, headers = _setup_published_disease(client, unique, pdf_bytes)

        detail = client.get(f"/api/v1/diseases/{disease_id}", headers=headers).json()
        disease_version_id = uuid.UUID(detail["latest_version"]["id"])

        scenario_module.run_scenario_generation(disease_version_id, "medium")

        scenarios = client.get(
            f"/api/v1/diseases/{disease_id}/scenarios", headers=headers
        ).json()
        assert scenarios["total"] == 0

        with SessionLocal() as db:
            scenario = db.scalar(
                select(Scenario).where(
                    Scenario.disease_version_id == disease_version_id,
                    Scenario.difficulty == "medium",
                )
            )
            assert scenario is not None
            assert scenario.status == "draft"
            state = db.scalar(
                select(ScenarioPatientState).where(
                    ScenarioPatientState.scenario_id == scenario.id
                )
            )
            issue_codes = [
                issue["code"] for issue in state.state["_meta"]["validation"]["issues"]
            ]
        assert "EXAM_MISSING" in issue_codes
        assert "RED_FLAG_COVERAGE" in issue_codes

        missing = client.get(
            f"/api/v1/scenarios/{scenario.id}", headers=headers
        )
        assert missing.status_code == 404


def test_scenario_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/scenarios/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 401
