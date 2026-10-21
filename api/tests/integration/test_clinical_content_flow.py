import uuid

from fastapi.testclient import TestClient

from app.api.routes import materials as materials_routes
from app.llm.schemas import (
    Demographics,
    DiseaseDiscoveryResult,
    DiseaseProfileResult,
    DiscoveredDisease,
    InvestigationFinding,
    RubricCategory,
    RubricExtractionResult,
    RubricItemDraft,
    SymptomFinding,
)
from app.main import app
from app.services import clinical_content as clinical_content_module
from app.services import ingestion as ingestion_service


class FakeRouter:
    def __init__(self, *, profile: DiseaseProfileResult, rubrics: RubricExtractionResult) -> None:
        self.profile = profile
        self.rubrics = rubrics
        self.calls: list[tuple[str, str]] = []

    def model_for_task(self, task: str) -> str:
        return f"fake-{task}"

    def generate(self, task: str, request) -> object:
        self.calls.append((task, request.prompt_version))
        if request.schema_model is DiseaseDiscoveryResult:
            return DiseaseDiscoveryResult(
                diseases=[
                    DiscoveredDisease(
                        name="Pneumonia",
                        source_pages=[1],
                        mention_context="Pneumonia is an infection of the lung parenchyma.",
                    )
                ]
            )
        if request.schema_model is DiseaseProfileResult:
            return self.profile
        if request.schema_model is RubricExtractionResult:
            return self.rubrics
        raise AssertionError(f"Unexpected schema model: {request.schema_model}")


def make_fake_router(*, empty: bool = False) -> FakeRouter:
    profile = DiseaseProfileResult(
        name="Pneumonia",
        aliases=["Community-acquired pneumonia"],
        demographics=Demographics(age_range="all ages", sex_bias=None, risk_factors=["smoking"]),
        symptoms=(
            []
            if empty
            else [
                SymptomFinding(name="cough", frequency="common"),
                SymptomFinding(name="fever", frequency="common"),
            ]
        ),
        exam_findings=[] if empty else [SymptomFinding(name="crackles", frequency="common")],
        investigations=(
            []
            if empty
            else [InvestigationFinding(name="chest x-ray", typical_result="lobar consolidation")]
        ),
        differentials=[] if empty else ["acute bronchitis"],
        red_flags=[] if empty else ["severe respiratory distress"],
        history_checklist=[],
        source_pages=[1],
    )
    rubrics = RubricExtractionResult(
        items=(
            []
            if empty
            else [
                RubricItemDraft(
                    category=RubricCategory.CHIEF_COMPLAINT,
                    question_text="What brings you in today?",
                    rationale="Opens the encounter",
                    weight=2,
                    critical=False,
                ),
                RubricItemDraft(
                    category=RubricCategory.HPI,
                    question_text="When did the cough start?",
                    rationale="Establishes onset",
                    weight=3,
                    critical=False,
                ),
                RubricItemDraft(
                    category=RubricCategory.RED_FLAG_SCREEN,
                    question_text="Are you having any trouble breathing at rest?",
                    rationale="Screens for respiratory distress",
                    weight=5,
                    critical=True,
                ),
            ]
        )
    )
    return FakeRouter(profile=profile, rubrics=rubrics)


def _setup_material(client: TestClient, unique: str, pdf_bytes: bytes) -> tuple[str, str, str, dict]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"clinical-{unique}@example.com",
            "password": "password123",
            "full_name": "Clinical Student",
        },
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    course = client.post(
        "/api/v1/courses", json={"name": f"Clinical Course {unique}"}, headers=headers
    )
    course_id = course.json()["id"]

    upload = client.post(
        f"/api/v1/courses/{course_id}/materials",
        files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    material_id = upload.json()["id"]

    status = client.get(f"/api/v1/materials/{material_id}/status", headers=headers).json()
    version_id = status["versions"][0]["id"]

    ingestion_service.run_extraction(uuid.UUID(version_id))

    return course_id, material_id, version_id, headers


def test_clinical_content_pipeline_publishes_disease(pdf_bytes: bytes, monkeypatch) -> None:
    fake = make_fake_router()
    monkeypatch.setattr(ingestion_service, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(materials_routes, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(clinical_content_module, "get_llm_router", lambda: fake)

    unique = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        course_id, material_id, version_id, headers = _setup_material(client, unique, pdf_bytes)

        clinical_content_module.run_clinical_content(uuid.UUID(version_id))

        status = client.get(f"/api/v1/materials/{material_id}/status", headers=headers).json()
        clinical_jobs = [job for job in status["jobs"] if job["job_type"] == "clinical_content"]
        assert clinical_jobs[0]["status"] == "succeeded"

        diseases = client.get(f"/api/v1/courses/{course_id}/diseases", headers=headers).json()
        assert diseases["total"] == 1
        disease = diseases["items"][0]
        assert disease["canonical_name"] == "pneumonia"
        assert disease["latest_version"]["status"] == "published"

        detail = client.get(f"/api/v1/diseases/{disease['id']}", headers=headers).json()
        latest = detail["latest_version"]
        assert latest["name"] == "Pneumonia"
        assert latest["status"] == "published"
        assert len(latest["rubric_items"]) == 3
        assert any(item["critical"] for item in latest["rubric_items"])
        assert len(latest["evidence"]) >= 1
        assert latest["source_summary"]["validation"]["passed"] is True

        labels = {option["label"]: option["match_type"] for option in latest["diagnosis_options"]}
        assert labels["Pneumonia"] == "exact"
        assert labels["Community-acquired pneumonia"] == "synonym"

        calls_before = len(fake.calls)
        clinical_content_module.run_clinical_content(uuid.UUID(version_id))
        assert len(fake.calls) == calls_before

        diseases_again = client.get(
            f"/api/v1/courses/{course_id}/diseases", headers=headers
        ).json()
        assert diseases_again["total"] == 1


def test_clinical_content_validation_failure_keeps_draft(pdf_bytes: bytes, monkeypatch) -> None:
    fake = make_fake_router(empty=True)
    monkeypatch.setattr(ingestion_service, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(materials_routes, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(clinical_content_module, "get_llm_router", lambda: fake)

    unique = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        course_id, _, version_id, headers = _setup_material(client, unique, pdf_bytes)

        clinical_content_module.run_clinical_content(uuid.UUID(version_id))

        diseases = client.get(f"/api/v1/courses/{course_id}/diseases", headers=headers).json()
        assert diseases["total"] == 1
        disease = diseases["items"][0]

        detail = client.get(f"/api/v1/diseases/{disease['id']}", headers=headers).json()
        latest = detail["latest_version"]
        assert latest["status"] == "draft"
        issue_codes = [issue["code"] for issue in latest["source_summary"]["validation"]["issues"]]
        assert "PROFILE_EMPTY" in issue_codes
        assert "RUBRIC_ITEMS_MISSING" in issue_codes


def test_disease_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/diseases/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 401
