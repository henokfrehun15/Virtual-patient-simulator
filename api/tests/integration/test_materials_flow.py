import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import materials as materials_routes
from app.core.database import SessionLocal
from app.main import app
from app.models.material import DocumentChunk, DocumentPage
from app.services import ingestion as ingestion_service


def test_material_upload_and_extraction_flow(pdf_bytes: bytes, monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "enqueue_extraction", lambda version_id: None)
    monkeypatch.setattr(materials_routes, "enqueue_extraction", lambda version_id: None)

    unique = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"student-{unique}@example.com",
                "password": "password123",
                "full_name": "Flow Student",
            },
        )
        assert register.status_code == 201
        token = register.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        course = client.post(
            "/api/v1/courses",
            json={"name": f"Internal Medicine {unique}"},
            headers=headers,
        )
        assert course.status_code == 201
        course_id = course.json()["id"]

        upload = client.post(
            f"/api/v1/courses/{course_id}/materials",
            files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 201
        material = upload.json()
        assert material["latest_version"]["status"] == "uploaded"

        duplicate = client.post(
            f"/api/v1/courses/{course_id}/materials",
            files={"file": ("notes.pdf", pdf_bytes, "application/pdf")},
            headers=headers,
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "MATERIAL_DUPLICATE"

        invalid = client.post(
            f"/api/v1/courses/{course_id}/materials",
            files={"file": ("bad.pdf", b"definitely not a pdf", "application/pdf")},
            headers=headers,
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "MATERIAL_INVALID"

        status = client.get(f"/api/v1/materials/{material['id']}/status", headers=headers)
        assert status.status_code == 200
        status_body = status.json()
        assert status_body["material"]["id"] == material["id"]
        version_id = uuid.UUID(status_body["versions"][0]["id"])

        ingestion_service.run_extraction(version_id)

        status_body = client.get(
            f"/api/v1/materials/{material['id']}/status", headers=headers
        ).json()
        assert status_body["material"]["latest_version"]["status"] == "extracted"
        assert status_body["jobs"][0]["status"] == "succeeded"
        assert status_body["jobs"][0]["attempts"] == 1

        with SessionLocal() as db:
            page_count = db.scalar(
                select(func.count())
                .select_from(DocumentPage)
                .where(DocumentPage.material_version_id == version_id)
            )
            chunk_count = db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.material_version_id == version_id)
            )
        assert page_count == 2
        assert chunk_count >= 1

        rerun = ingestion_service.run_extraction(version_id)
        assert rerun is None

        anonymous = client.get(f"/api/v1/materials/{material['id']}")
        assert anonymous.status_code == 401


def test_course_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/courses")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_UNAUTHORIZED"
