import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_llm_settings_roundtrip_never_returns_key() -> None:
    unique = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"settings-{unique}@example.com",
                "password": "password123",
                "full_name": "Settings Student",
            },
        )
        headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

        initial = client.get("/api/v1/users/me/llm-settings", headers=headers)
        assert initial.status_code == 200
        assert initial.json()["api_key_set"] is False

        updated = client.put(
            "/api/v1/users/me/llm-settings",
            json={
                "api_key": "sk-ant-test-key-0000000000000000",
                "patient_model": "claude-test-model",
            },
            headers=headers,
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["api_key_set"] is True
        assert body["api_key_source"] == "user"
        assert body["patient_model"] == "claude-test-model"
        assert "sk-ant" not in str(body)

        fetched = client.get("/api/v1/users/me/llm-settings", headers=headers)
        assert fetched.json()["api_key_set"] is True
        assert "api_key" not in fetched.json()

        cleared = client.put(
            "/api/v1/users/me/llm-settings",
            json={"clear_api_key": True},
            headers=headers,
        )
        assert cleared.json()["api_key_set"] is False
        assert cleared.json()["patient_model"] == "claude-test-model"


def test_settings_require_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/users/me/llm-settings").status_code == 401
