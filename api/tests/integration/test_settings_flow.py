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
                "provider": "groq",
                "api_key": "gsk_test_key_00000000000000000000",
                "patient_model": "llama-3.3-70b-versatile",
            },
            headers=headers,
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["provider"] == "groq"
        assert body["api_key_set"] is True
        assert body["api_key_source"] == "user"
        assert body["patient_model"] == "llama-3.3-70b-versatile"
        assert "gsk_" not in str(body)

        fetched = client.get("/api/v1/users/me/llm-settings", headers=headers)
        assert fetched.json()["provider"] == "groq"
        assert fetched.json()["api_key_set"] is True
        assert "api_key" not in fetched.json()

        switched = client.put(
            "/api/v1/users/me/llm-settings",
            json={"provider": "anthropic"},
            headers=headers,
        )
        assert switched.json()["provider"] == "anthropic"
        assert switched.json()["api_key_set"] is False

        cleared = client.put(
            "/api/v1/users/me/llm-settings",
            json={"clear_api_key": True},
            headers=headers,
        )
        assert cleared.json()["api_key_set"] is False
        assert cleared.json()["patient_model"] == "llama-3.3-70b-versatile"


def test_settings_reject_unknown_provider() -> None:
    unique = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"settings-prov-{unique}@example.com",
                "password": "password123",
                "full_name": "Settings Student",
            },
        )
        headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
        rejected = client.put(
            "/api/v1/users/me/llm-settings",
            json={"provider": "openai"},
            headers=headers,
        )
        assert rejected.status_code == 422


def test_settings_require_authentication() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/users/me/llm-settings").status_code == 401
