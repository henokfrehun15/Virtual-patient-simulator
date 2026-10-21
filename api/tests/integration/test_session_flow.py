import uuid

import redis
from fastapi.testclient import TestClient

from app.api.routes import sessions as sessions_routes
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.models.disease import Disease, DiseaseVersion
from app.models.scenario import Scenario, ScenarioPatientState
from app.main import app


class FakeStreamRouter:
    def __init__(self, reply_chunks: list[str] | None = None) -> None:
        self.reply_chunks = reply_chunks or ["It started ", "about two days ago."]
        self.stream_calls = 0
        self.last_request = None

    def model_for_task(self, task: str) -> str:
        return "fake-patient"

    def stream(self, task, request):
        self.stream_calls += 1
        self.last_request = request
        return iter(list(self.reply_chunks))


class FailingStreamRouter:
    def model_for_task(self, task: str) -> str:
        return "fake-patient"

    def stream(self, task, request):
        def generator():
            yield "partial "
            raise AppError("LLM_TIMEOUT", "The provider timed out.", status_code=502)

        return generator()


def create_published_scenario() -> uuid.UUID:
    unique = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        disease = Disease(canonical_name=f"influenza {unique}")
        db.add(disease)
        db.flush()
        disease_version = DiseaseVersion(
            disease_id=disease.id,
            version=1,
            name=f"Influenza {unique}",
            status="published",
        )
        db.add(disease_version)
        db.flush()
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
            "hpi": {"onset": "2 days ago", "severity": 6},
            "pmh": [],
            "medications": [],
            "allergies": [],
            "family_history": [],
            "social_history": {},
            "ros": {},
            "red_flags": {"difficulty breathing": False},
            "physical_exam": {"general": "appears unwell"},
            "investigation_results": {"rapid influenza test": {"result": "positive"}},
            "communication_style": "tired but cooperative",
            "emotional_state": "fatigued",
            "_meta": {"difficulty": "medium"},
        }
        db.add(ScenarioPatientState(scenario_id=scenario.id, state=state))
        db.commit()
        return scenario.id


def _register_user(client: TestClient, unique: str) -> dict:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"session-{unique}@example.com",
            "password": "password123",
            "full_name": "Session Student",
        },
    )
    return {"Authorization": f"Bearer {register.json()['access_token']}"}


def test_start_session_practice_shows_diagnosis_and_idempotency() -> None:
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        headers = _register_user(client, unique)
        body = {
            "scenario_id": str(scenario_id),
            "mode": "practice",
            "idempotency_key": "start-key-12345678",
        }

        first = client.post("/api/v1/sessions", json=body, headers=headers)
        assert first.status_code == 201
        session = first.json()
        assert session["status"] == "active"
        assert session["current_turn"] == 0
        assert session["turn_limit"] > 0
        assert session["messages"] == []
        assert session["patient"]["name"] == "Maria Garcia"
        assert session["chief_complaint"] == "fever and body aches"
        assert "Influenza" in session["diagnosis"]

        second = client.post("/api/v1/sessions", json=body, headers=headers)
        assert second.status_code == 201
        assert second.json()["id"] == session["id"]


def test_test_mode_hides_diagnosis_and_enforces_ownership() -> None:
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        owner_headers = _register_user(client, f"{unique}a")
        other_headers = _register_user(client, f"{unique}b")

        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "test"},
            headers=owner_headers,
        )
        assert started.status_code == 201
        session = started.json()
        assert session["diagnosis"] is None

        forbidden = client.get(f"/api/v1/sessions/{session['id']}", headers=other_headers)
        assert forbidden.status_code == 404
        assert forbidden.json()["error"]["code"] == "SESSION_NOT_FOUND"

        allowed = client.get(f"/api/v1/sessions/{session['id']}", headers=owner_headers)
        assert allowed.status_code == 200

        invalid_scenario = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(uuid.uuid4()), "mode": "test"},
            headers=owner_headers,
        )
        assert invalid_scenario.status_code == 404
        assert invalid_scenario.json()["error"]["code"] == "SCENARIO_INVALID"


def test_message_stream_flow_and_replay(monkeypatch) -> None:
    fake = FakeStreamRouter()
    monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: fake)
    monkeypatch.setattr(
        sessions_routes, "enqueue_message_scoring", lambda *args, **kwargs: None
    )
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        headers = _register_user(client, unique)
        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "test"},
            headers=headers,
        )
        session_id = started.json()["id"]

        body = {
            "content": "When did you start feeling unwell?",
            "idempotency_key": "msg-key-12345678",
        }
        response = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream", json=body, headers=headers
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "event: token" in response.text
        assert "event: done" in response.text

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        assert detail["current_turn"] == 1
        roles = [message["role"] for message in detail["messages"]]
        assert roles == ["doctor", "patient"]
        assert detail["messages"][1]["content"] == "It started about two days ago."

        user_content = fake.last_request.user
        assert "physical_exam" not in user_content
        assert "investigation_results" not in user_content
        assert "_meta" not in user_content
        assert "Maria Garcia" in user_content

        replay = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream", json=body, headers=headers
        )
        assert replay.status_code == 200
        assert "event: done" in replay.text

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        assert detail["current_turn"] == 1
        assert len(detail["messages"]) == 2
        assert fake.stream_calls == 1


def test_stream_failure_aborts_turn_and_allows_retry(monkeypatch) -> None:
    failing = FailingStreamRouter()
    monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: failing)
    monkeypatch.setattr(
        sessions_routes, "enqueue_message_scoring", lambda *args, **kwargs: None
    )
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        headers = _register_user(client, unique)
        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "test"},
            headers=headers,
        )
        session_id = started.json()["id"]

        response = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "When did it start?"},
            headers=headers,
        )
        assert response.status_code == 200
        assert "event: error" in response.text
        assert "unable to respond" in response.text

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        assert detail["messages"] == []
        assert detail["current_turn"] == 0

        working = FakeStreamRouter()
        monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: working)
        retry = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "When did it start?"},
            headers=headers,
        )
        assert "event: done" in retry.text

        detail = client.get(f"/api/v1/sessions/{session_id}", headers=headers).json()
        assert detail["current_turn"] == 1
        assert len(detail["messages"]) == 2


def test_turn_limit_enforced(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "max_session_turns", 1)
    fake = FakeStreamRouter()
    monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: fake)
    monkeypatch.setattr(
        sessions_routes, "enqueue_message_scoring", lambda *args, **kwargs: None
    )
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        headers = _register_user(client, unique)
        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "test"},
            headers=headers,
        )
        session_id = started.json()["id"]
        assert started.json()["turn_limit"] == 1

        first = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "Hello, what brings you in?"},
            headers=headers,
        )
        assert "event: done" in first.text

        second = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "Tell me more."},
            headers=headers,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "SESSION_TURN_LIMIT"


def test_concurrent_turn_rejected(monkeypatch) -> None:
    fake = FakeStreamRouter()
    monkeypatch.setattr(sessions_routes, "get_llm_router", lambda user_id=None: fake)
    monkeypatch.setattr(
        sessions_routes, "enqueue_message_scoring", lambda *args, **kwargs: None
    )
    scenario_id = create_published_scenario()
    unique = uuid.uuid4().hex[:8]

    with TestClient(app) as client:
        headers = _register_user(client, unique)
        started = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(scenario_id), "mode": "test"},
            headers=headers,
        )
        session_id = started.json()["id"]

        lock_client = redis.Redis.from_url(get_settings().redis_url)
        lock_key = f"lock:turn:{session_id}"
        lock_client.set(lock_key, "1", nx=True, ex=60)

        response = client.post(
            f"/api/v1/sessions/{session_id}/messages/stream",
            json={"content": "Hello?"},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SESSION_CONCURRENT_TURN"

        lock_client.delete(lock_key)


def test_session_endpoints_require_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/sessions").status_code in (401, 405)
        response = client.post(
            "/api/v1/sessions",
            json={"scenario_id": str(uuid.uuid4()), "mode": "test"},
        )
        assert response.status_code == 401
