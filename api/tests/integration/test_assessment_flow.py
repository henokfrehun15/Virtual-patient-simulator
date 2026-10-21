import uuid

from fastapi.testclient import TestClient

from app.api.routes import sessions as sessions_routes
from app.core.database import SessionLocal
from app.llm.schemas import (
    FeedbackResult,
    RubricMatch,
    RubricMatchResult,
    RubricMatchStatus,
)
from app.main import app
from app.models.disease import Disease, DiseaseVersion
from app.models.rubric import DiagnosisOption, RubricItem
from app.models.scenario import Scenario, ScenarioPatientState
from app.services import completion as completion_module
from app.services import scoring as scoring_module
from app.services.scoring import run_message_scoring


class FakeStreamRouter:
    def model_for_task(self, task: str) -> str:
        return "fake-patient"

    def stream(self, task, request):
        return iter(["It started ", "two days ago."])


class FakeMatcherRouter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def model_for_task(self, task: str) -> str:
        return "fake-scorer"

    def generate(self, task, request):
        self.calls.append(task)
        return RubricMatchResult(
            matches=[
                RubricMatch(
                    rubric_index=1,
                    status=RubricMatchStatus.SATISFIED,
                    confidence=0.95,
                    quality_score=0.9,
                    reason="Directly asks about onset.",
                )
            ]
        )


class FakeFeedbackRouter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def model_for_task(self, task: str) -> str:
        return "fake-feedback"

    def generate(self, task, request):
        self.calls.append(task)
        return FeedbackResult(
            narrative="You established the presenting complaint and onset effectively.",
            strengths=["Clear opening question"],
            gaps=["Did not screen the critical red flag"],
            critical_misses=["Are you having any trouble breathing at rest?"],
            one_recommended_focus="Always screen for respiratory distress in chest pain cases.",
        )


def create_assessment_scenario() -> uuid.UUID:
    unique = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        disease = Disease(canonical_name=f"pneumonia {unique}")
        db.add(disease)
        db.flush()
        disease_version = DiseaseVersion(
            disease_id=disease.id,
            version=1,
            name=f"Pneumonia {unique}",
            status="published",
            red_flags=["severe respiratory distress"],
        )
        db.add(disease_version)
        db.flush()

        db.add(
            RubricItem(
                disease_version_id=disease_version.id,
                category="hpi",
                question_text="When did your symptoms start?",
                rationale="Establishes onset",
                weight=3,
                critical=False,
            )
        )
        db.add(
            RubricItem(
                disease_version_id=disease_version.id,
                category="red_flag_screen",
                question_text="Are you having any trouble breathing at rest?",
                rationale="Screens respiratory distress",
                weight=5,
                critical=True,
            )
        )
        db.add(
            DiagnosisOption(
                disease_version_id=disease_version.id,
                label=f"Pneumonia {unique}",
                match_type="exact",
            )
        )
        db.add(
            DiagnosisOption(
                disease_version_id=disease_version.id,
                label="flu",
                match_type="synonym",
            )
        )

        scenario = Scenario(
            disease_version_id=disease_version.id,
            version=1,
            difficulty="medium",
            scenario_seed=f"seed-{unique}",
            status="published",
        )
        db.add(scenario)
        db.flush()
        state = {
            "demographics": {"name": "Maria Garcia", "age": 28, "sex": "female"},
            "chief_complaint": "fever and body aches",
            "hpi": {"onset": "2 days ago"},
        }
        db.add(ScenarioPatientState(scenario_id=scenario.id, state=state))
        db.commit()
        return scenario.id


def _start_session(
    client: TestClient, unique: str, scenario_id: uuid.UUID
) -> tuple[str, dict, str]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"assess-{unique}@example.com",
            "password": "password123",
            "full_name": "Assessment Student",
        },
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    user_id = register.json()["user"]["id"]
    started = client.post(
        "/api/v1/sessions",
        json={"scenario_id": str(scenario_id), "mode": "test"},
        headers=headers,
    )
    return started.json()["id"], headers, user_id


def test_full_assessment_flow(monkeypatch) -> None:
    scenario_id = create_assessment_scenario()
    unique = uuid.uuid4().hex[:8]

    matcher = FakeMatcherRouter()
    feedback = FakeFeedbackRouter()
    monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: FakeStreamRouter())
    monkeypatch.setattr(
        sessions_routes, "enqueue_message_scoring", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(scoring_module, "get_llm_router", lambda user_id=None: matcher)
    monkeypatch.setattr(completion_module, "get_llm_router", lambda user_id=None: feedback)

    with TestClient(app) as client:
        session_id, headers, user_id = _start_session(client, unique, scenario_id)

        stream = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "When did your symptoms start?"},
            headers=headers,
        )
        assert "event: done" in stream.text

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        doctor_message_id = detail["messages"][0]["id"]
        run_message_scoring(
            uuid.UUID(session_id), uuid.UUID(doctor_message_id), uuid.UUID(user_id)
        )
        assert len(matcher.calls) == 1

        diagnosis = client.post(
            f"/api/v1/sessions/{session_id}/diagnosis",
            json={"guess": "pneumonia"},
            headers=headers,
        )
        assert diagnosis.status_code == 201
        assert diagnosis.json()["verdict"] is None

        report_before = client.get(
            f"/api/v1/sessions/{session_id}/report", headers=headers
        )
        assert report_before.status_code == 404

        complete = client.post(
            f"/api/v1/sessions/{session_id}/complete", json={}, headers=headers
        )
        assert complete.status_code == 202
        assert complete.json()["status"] == "completing"

        completion_module.run_completion(uuid.UUID(session_id), uuid.UUID(user_id))
        assert len(feedback.calls) == 1

        report = client.get(f"/api/v1/sessions/{session_id}/report", headers=headers)
        assert report.status_code == 200
        body = report.json()
        assert body["diagnosis"]["verdict"] == "correct"
        assert body["diagnosis_score"] == 100.0
        assert body["history_score"] is not None
        assert len(body["critical_misses"]) == 1
        assert "breathing at rest" in body["critical_misses"][0]
        assert body["narrative"] is not None
        assert body["strengths"] == ["Clear opening question"]

        statuses = {item["question"]: item["status"] for item in body["rubric_results"]}
        assert statuses["When did your symptoms start?"] == "satisfied"
        assert statuses["Are you having any trouble breathing at rest?"] == "not_attempted"

        progress = client.get("/api/v1/users/me/progress", headers=headers)
        assert progress.status_code == 200
        progress_body = progress.json()
        assert progress_body["sessions_completed"] == 1
        categories = {c["category"] for c in progress_body["categories"]}
        assert "history_hpi" in categories
        assert "red_flag_screening" in categories
        assert "diagnosis" in categories

        history = client.get("/api/v1/users/me/history", headers=headers)
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["diagnosis_verdict"] == "correct"

        complete_again = client.post(
            f"/api/v1/sessions/{session_id}/complete", json={}, headers=headers
        )
        assert complete_again.status_code == 200
        assert complete_again.json()["status"] == "completed"


def test_diagnosis_verdict_visible_in_practice_mode(monkeypatch) -> None:
    scenario_id = create_assessment_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"practice-{unique}@example.com",
                "password": "password123",
                "full_name": "Practice Student",
            },
        )
        headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "practice"},
            headers=headers,
        )
        session_id = started.json()["id"]

        diagnosis = client.post(
            f"/api/v1/sessions/{session_id}/diagnosis",
            json={"guess": "I think this is the flu"},
            headers=headers,
        )
        assert diagnosis.status_code == 201
        assert diagnosis.json()["verdict"] == "correct"
