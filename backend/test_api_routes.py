"""
ComplyFlow — API Route Integration Tests

Tests FastAPI endpoints (project creation, listing, file upload, results retrieval)
using SQLiteStorageService persistence.
"""
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import get_storage, SQLiteStorageService

from app.services.auth_service import create_session_token

client = TestClient(app)
token = create_session_token("demo-user", "demo@complyflow.local")
client.headers["Authorization"] = f"Bearer {token}"



def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "complyflow-api"


def test_create_and_list_projects():
    # Create project
    response = client.post("/api/projects", data={"name": "API Test Project"})
    assert response.status_code == 200
    proj = response.json()
    project_id = proj["project_id"]
    assert proj["name"] == "API Test Project"
    assert proj["status"] == "PENDING"

    # Get project by ID
    get_res = client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["project_id"] == project_id

    # List projects
    list_res = client.get("/api/projects")
    assert list_res.status_code == 200
    projects = list_res.json()["projects"]
    assert any(p["project_id"] == project_id for p in projects)


def test_upload_documents_endpoint():
    # 1. Create project
    create_res = client.post("/api/projects", data={"name": "Upload Test Project"})
    project_id = create_res.json()["project_id"]

    # 2. Upload requirements and evidence files
    req_content = b"REQ-001: Sample Requirement\nMust provide insurance certificate."
    doc_content = b"CERTIFICATE OF INSURANCE\nInsured: Acme Corp\nLimit: $2M"

    files = [
        ("requirements_file", ("reqs.txt", io.BytesIO(req_content), "text/plain")),
        ("evidence_files", ("insurance.txt", io.BytesIO(doc_content), "text/plain")),
    ]

    upload_res = client.post(
        f"/api/projects/{project_id}/documents",
        files=files,
        data={"is_remediation": "false"},
    )
    assert upload_res.status_code == 200
    saved = upload_res.json()["saved"]
    assert len(saved) == 2
    assert any(d["name"] == "reqs.txt" and d["role"] == "requirements" for d in saved)
    assert any(d["name"] == "insurance.txt" and d["role"] == "evidence" for d in saved)
