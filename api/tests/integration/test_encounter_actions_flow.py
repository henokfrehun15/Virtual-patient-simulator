import uuid

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.disease import Disease, DiseaseVersion
from app.models.scenario import (
    Scenario,
    ScenarioExamination,
    ScenarioInvestigation,
    ScenarioPatientState,
)


def create_scenario_with_catalog() -> uuid.UUID:
    unique = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        disease = Disease(canonical_name=f"pericarditis {unique}")
        db.add(disease)
        db.flush()
        disease_version = DiseaseVersion(
            disease_id=disease.id,
            version=1,
            name=f"Pericarditis {unique}",
            status="published",
        )
        db.add(disease_version)
        db.flush()
        scenario = Scenario(
            disease_version_id=disease_version.id,
            version=1,
            difficulty="easy",
            scenario_seed=f"seed-{unique}",
            status="published",
        )
        db.add(scenario)
        db.flush()
        state = {
            "demographics": {"name": "James Okafor", "age": 45, "sex": "male"},
            "chief_complaint": "chest pain",
            "hpi": {"onset": "2 days ago"},
        }
        db.add(ScenarioPatientState(scenario_id=scenario.id, state=state))
        db.add(
            ScenarioExamination(
                scenario_id=scenario.id,
                exam_name="cardiovascular examination",
                available=True,
                findings={"auscultation": "pericardial friction rub", "BP": "110/70"},
            )
        )
        db.add(
            ScenarioExamination(
                scenario_id=scenario.id,
                exam_name="abdominal examination",
                available=False,
                findings={},
            )
        )
        db.add(
            ScenarioInvestigation(
                scenario_id=scenario.id,
                test_name="ECG",
                available=True,
                result={"finding": "widespread ST elevation"},
                cost_weight=1,
            )
        )
        db.add(
            ScenarioInvestigation(
                scenario_id=scenario.id,
                test_name="CBC",
                available=False,
                result={},
                cost_weight=1,
            )
        )
        db.commit()
        return scenario.id


def _start_session(client: TestClient, unique: str, scenario_id: uuid.UUID) -> tuple[str, dict]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"actions-{unique}@example.com",
            "password": "password123",
            "full_name": "Actions Student",
        },
    )
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
    started = client.post(
        "/api/v1/sessions",
        json={"scenario_id": str(scenario_id), "mode": "test"},
        headers=headers,
    )
    return started.json()["id"], headers


def test_examination_flow(monkeypatch) -> None:
    scenario_id = create_scenario_with_catalog()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        session_id, headers = _start_session(client, unique, scenario_id)

        found = client.post(
            f"/api/v1/sessions/{session_id}/examinations",
            json={"exam_name": "cardiovascular exam"},
            headers=headers,
        )
        assert found.status_code == 201
        body = found.json()
        assert body["exam_name"] == "cardiovascular examination"
        assert body["result"]["auscultation"] == "pericardial friction rub"

        replay = client.post(
            f"/api/v1/sessions/{session_id}/examinations",
            json={
                "exam_name": "cardiovascular exam",
                "idempotency_key": "exam-key-12345678",
            },
            headers=headers,
        )
        assert replay.status_code == 201

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        assert len(detail["examination_requests"]) == 2

        unavailable = client.post(
            f"/api/v1/sessions/{session_id}/examinations",
            json={"exam_name": "fundoscopy"},
            headers=headers,
        )
        assert unavailable.status_code == 404
        assert unavailable.json()["error"]["code"] == "EXAMINATION_UNAVAILABLE"

        disabled = client.post(
            f"/api/v1/sessions/{session_id}/examinations",
            json={"exam_name": "abdominal examination"},
            headers=headers,
        )
        assert disabled.status_code == 404


def test_investigation_flow(monkeypatch) -> None:
    scenario_id = create_scenario_with_catalog()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        session_id, headers = _start_session(client, unique, scenario_id)

        found = client.post(
            f"/api/v1/sessions/{session_id}/investigations",
            json={"test_name": "ECG"},
            headers=headers,
        )
        assert found.status_code == 201
        assert found.json()["test_name"] == "ECG"
        assert found.json()["result"]["finding"] == "widespread ST elevation"

        unavailable = client.post(
            f"/api/v1/sessions/{session_id}/investigations",
            json={"test_name": "urinalysis"},
            headers=headers,
        )
        assert unavailable.status_code == 404
        assert unavailable.json()["error"]["code"] == "INVESTIGATION_UNAVAILABLE"

        disabled = client.post(
            f"/api/v1/sessions/{session_id}/investigations",
            json={"test_name": "CBC"},
            headers=headers,
        )
        assert disabled.status_code == 404
