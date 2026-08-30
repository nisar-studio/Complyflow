"""
test_remediation_uploads.py

Comprehensive pytest suite for the Remediation Uploads feature (P1 #4).

Covers:
  - Storage CRUD (unit tests against a temporary SQLite DB)
  - File validation utilities (sanitize_filename, validate_upload)
  - API endpoints: POST / GET-list / GET-single / DELETE
  - Security: disallowed extension, oversized file, path traversal
  - Integration: files written to disk on create, removed on delete
  - No cross-contamination with existing test data
"""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService


# ---------------------------------------------------------------------------
# Helper: run coroutine in a brand-new event loop
# ---------------------------------------------------------------------------

def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    return SQLiteStorageService(db_path=str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# 1. Storage Unit Tests
# ---------------------------------------------------------------------------


class TestRemediationUploadStorage:

    def _proj(self): return f"proj-{uuid.uuid4().hex[:8]}"
    def _task(self): return f"task-{uuid.uuid4().hex[:8]}"

    def test_save_and_get_upload(self, tmp_db):
        proj, task = self._proj(), self._task()
        uid = run(tmp_db.save_remediation_upload(proj, task, {
            "requirement_id": "REQ-01",
            "filename": "insurance.pdf",
            "stored_filename": "/tmp/fake.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "description": "Q3 cert",
        }))
        assert uid
        rec = run(tmp_db.get_remediation_upload(proj, uid))
        assert rec is not None
        assert rec["upload_id"] == uid
        assert rec["filename"] == "insurance.pdf"
        assert rec["upload_status"] == "PENDING_VERIFICATION"
        assert rec["description"] == "Q3 cert"

    def test_list_uploads_by_task(self, tmp_db):
        proj = self._proj()
        ta, tb = self._task(), self._task()
        for i in range(3):
            run(tmp_db.save_remediation_upload(proj, ta, {
                "requirement_id": f"REQ-0{i}", "filename": f"f{i}.pdf",
                "stored_filename": f"/tmp/f{i}.pdf", "file_type": "pdf", "file_size": i,
            }))
        run(tmp_db.save_remediation_upload(proj, tb, {
            "requirement_id": "REQ-99", "filename": "other.pdf",
            "stored_filename": "/tmp/o.pdf", "file_type": "pdf", "file_size": 1,
        }))
        assert len(run(tmp_db.list_remediation_uploads(proj, task_id=ta))) == 3
        assert len(run(tmp_db.list_remediation_uploads(proj, task_id=tb))) == 1
        assert len(run(tmp_db.list_remediation_uploads(proj))) == 4

    def test_delete_upload_removes_file(self, tmp_db, tmp_path):
        proj, task = self._proj(), self._task()
        f = tmp_path / "ev.pdf"
        f.write_bytes(b"evidence")
        uid = run(tmp_db.save_remediation_upload(proj, task, {
            "requirement_id": "REQ-05", "filename": "ev.pdf",
            "stored_filename": str(f), "file_type": "pdf", "file_size": 8,
        }))
        assert f.exists()
        assert run(tmp_db.delete_remediation_upload(proj, uid)) is True
        assert not f.exists()
        assert run(tmp_db.delete_remediation_upload(proj, uid)) is False

    def test_get_nonexistent_returns_none(self, tmp_db):
        assert run(tmp_db.get_remediation_upload(self._proj(), "no-such-id")) is None

    def test_upload_ids_are_unique(self, tmp_db):
        proj, task = self._proj(), self._task()
        ids = {run(tmp_db.save_remediation_upload(proj, task, {
            "requirement_id": "REQ-01", "filename": "f.pdf",
            "stored_filename": "/tmp/x.pdf", "file_type": "pdf", "file_size": 1,
        })) for _ in range(5)}
        assert len(ids) == 5

    def test_project_scoping(self, tmp_db):
        pa, pb, task = self._proj(), self._proj(), self._task()
        run(tmp_db.save_remediation_upload(pa, task, {
            "requirement_id": "REQ-01", "filename": "a.pdf",
            "stored_filename": "/tmp/a.pdf", "file_type": "pdf", "file_size": 1,
        }))
        assert run(tmp_db.list_remediation_uploads(pb)) == []


# ---------------------------------------------------------------------------
# 2. File Validation Unit Tests
# ---------------------------------------------------------------------------


class TestFileUtils:

    def test_sanitize_normal(self):
        from app.services.file_utils import sanitize_filename
        assert sanitize_filename("insurance_cert.pdf") == "insurance_cert.pdf"

    def test_sanitize_strips_path(self):
        from app.services.file_utils import sanitize_filename
        r = sanitize_filename("../../etc/passwd")
        assert "/" not in r and "\\" not in r

    def test_sanitize_empty(self):
        from app.services.file_utils import sanitize_filename
        assert sanitize_filename("") == "upload"

    def test_sanitize_unsafe_chars(self):
        from app.services.file_utils import sanitize_filename
        r = sanitize_filename("hello world & more!.pdf")
        assert " " not in r and "&" not in r
        assert r.endswith(".pdf")

    def test_get_extension(self):
        from app.services.file_utils import get_extension
        assert get_extension("report.PDF") == ".pdf"
        assert get_extension("noext") == ""

    def test_validate_allowed(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.file_utils import validate_upload
        f = MagicMock()
        f.filename = "cert.pdf"
        data = b"pdf content"
        f.read = AsyncMock(side_effect=[data, b""])
        assert run(validate_upload(f)) == data

    def test_validate_disallowed_ext(self):
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException
        from app.services.file_utils import validate_upload
        f = MagicMock()
        f.filename = "evil.exe"
        f.read = AsyncMock(return_value=b"")
        with pytest.raises(HTTPException) as ei:
            run(validate_upload(f))
        assert ei.value.status_code == 400

    def test_validate_empty(self):
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException
        from app.services.file_utils import validate_upload
        f = MagicMock()
        f.filename = "empty.pdf"
        f.read = AsyncMock(return_value=b"")
        with pytest.raises(HTTPException) as ei:
            run(validate_upload(f))
        assert ei.value.status_code == 400

    def test_validate_oversized(self):
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException
        from app.services.file_utils import validate_upload
        f = MagicMock()
        f.filename = "huge.pdf"
        big = b"x" * (64 * 1024)
        f.read = AsyncMock(side_effect=[big, big, b""])
        with pytest.raises(HTTPException) as ei:
            run(validate_upload(f, max_size=1))
        assert ei.value.status_code == 413


# ---------------------------------------------------------------------------
# 3. API Integration Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_ctx(tmp_path_factory):
    """
    Provide (client, project_id, storage_instance, upload_dir).
    Injects our test SQLiteStorageService into the global singleton so
    all routes use the temp DB without needing function-level patches.
    """
    tmp = tmp_path_factory.mktemp("api_uploads")
    db_path = str(tmp / "api.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Reset the module-level singleton so our instance is used
    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir

    from app.main import app
    from app.services.auth_service import create_session_token
    client = TestClient(app, raise_server_exceptions=True)
    token = create_session_token("demo-user", "demo@complyflow.local")
    client.headers["Authorization"] = f"Bearer {token}"

    # Create project via API (uses our test_storage through the singleton)
    r = client.post("/api/projects", data={"name": "Upload Test Project"})

    assert r.status_code == 200, r.text
    project_id = r.json()["project_id"]

    # Seed requirements + tasks directly via the same instance
    run(test_storage.save_requirements(project_id, [
        {"requirement_id": "REQ-01", "title": "Insurance Certificate", "description": "Proof of insurance"},
        {"requirement_id": "REQ-02", "title": "DPA", "description": "Data Processing Agreement"},
    ]))
    run(test_storage.save_tasks(project_id, [
        {
            "task_id": "TASK-01",
            "title": "Upload insurance cert",
            "severity": "HIGH",
            "required_action": "Upload proof",
            "status": "OPEN",
            "related_requirement_id": "REQ-01",
        },
    ]))

    yield client, project_id, test_storage, upload_dir

    # Teardown: restore original singleton and upload dir
    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir


class TestRemediationUploadAPI:

    def _upload_pdf(self, client, project_id, task_id="TASK-01", req_id="REQ-01",
                    filename="cert.pdf", content=b"pdf content", description=""):
        data = {"requirement_id": req_id}
        if description:
            data["description"] = description
        return client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/uploads",
            data=data,
            files={"file": (filename, io.BytesIO(content), "application/pdf")},
        )

    def test_upload_valid_file(self, api_ctx):
        client, pid, storage, _ = api_ctx
        content = b"%PDF-1.4 fake insurance cert"
        r = self._upload_pdf(client, pid, content=content, description="Test upload")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "created"
        u = body["upload"]
        assert u["filename"] == "cert.pdf"
        assert u["requirement_id"] == "REQ-01"
        assert u["upload_status"] == "PENDING_VERIFICATION"
        assert u["file_size"] == len(content)
        assert "stored_filename" not in u, "stored_filename must NOT be exposed"

    def test_list_uploads(self, api_ctx):
        client, pid, _, _ = api_ctx
        self._upload_pdf(client, pid, filename="list_test.pdf", content=b"list test")
        r = client.get(f"/api/projects/{pid}/tasks/TASK-01/uploads")
        assert r.status_code == 200
        uploads = r.json()["uploads"]
        assert isinstance(uploads, list) and len(uploads) >= 1
        for u in uploads:
            assert "stored_filename" not in u

    def test_get_single_upload(self, api_ctx):
        client, pid, _, _ = api_ctx
        cr = self._upload_pdf(client, pid, filename="single.pdf", content=b"single content")
        assert cr.status_code == 200, cr.text
        upload_id = cr.json()["upload"]["upload_id"]
        r = client.get(f"/api/projects/{pid}/uploads/{upload_id}")
        assert r.status_code == 200
        assert r.json()["upload"]["upload_id"] == upload_id
        assert "stored_filename" not in r.json()["upload"]

    def test_delete_upload(self, api_ctx):
        client, pid, _, _ = api_ctx
        cr = self._upload_pdf(client, pid, filename="del.pdf", content=b"delete me")
        assert cr.status_code == 200, cr.text
        uid = cr.json()["upload"]["upload_id"]
        del_r = client.delete(f"/api/projects/{pid}/uploads/{uid}")
        assert del_r.status_code == 200
        assert del_r.json()["status"] == "deleted"
        assert client.get(f"/api/projects/{pid}/uploads/{uid}").status_code == 404

    def test_disallowed_extension(self, api_ctx):
        client, pid, _, _ = api_ctx
        r = client.post(
            f"/api/projects/{pid}/tasks/TASK-01/uploads",
            data={"requirement_id": "REQ-01"},
            files={"file": ("evil.exe", io.BytesIO(b"bad"), "application/octet-stream")},
        )
        assert r.status_code == 400
        body = r.json()
        # App may wrap errors as {"detail": "..."} or {"error": {"message": "..."}}
        error_text = str(body)
        assert ".exe" in error_text, f"Expected .exe in error body: {body}"

    def test_invalid_requirement_id(self, api_ctx):
        client, pid, _, _ = api_ctx
        r = client.post(
            f"/api/projects/{pid}/tasks/TASK-01/uploads",
            data={"requirement_id": "REQ-NONEXISTENT"},
            files={"file": ("f.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        assert r.status_code == 400

    def test_invalid_task_id(self, api_ctx):
        client, pid, _, _ = api_ctx
        r = client.post(
            f"/api/projects/{pid}/tasks/TASK-FAKE/uploads",
            data={"requirement_id": "REQ-01"},
            files={"file": ("f.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        assert r.status_code == 404

    def test_nonexistent_project(self, api_ctx):
        client, _, _, _ = api_ctx
        r = client.post(
            "/api/projects/ghost/tasks/TASK-01/uploads",
            data={"requirement_id": "REQ-01"},
            files={"file": ("f.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
        assert r.status_code == 404

    def test_get_nonexistent_upload(self, api_ctx):
        client, pid, _, _ = api_ctx
        assert client.get(f"/api/projects/{pid}/uploads/nonexistent").status_code == 404

    def test_delete_nonexistent_upload(self, api_ctx):
        client, pid, _, _ = api_ctx
        assert client.delete(f"/api/projects/{pid}/uploads/nonexistent").status_code == 404

    def test_file_stored_on_disk(self, api_ctx):
        client, pid, storage, upload_dir = api_ctx
        content = b"physical file content check"
        cr = self._upload_pdf(client, pid, filename="physical.pdf", content=content)
        assert cr.status_code == 200, cr.text
        uid = cr.json()["upload"]["upload_id"]
        record = run(storage.get_remediation_upload(pid, uid))
        path = record["stored_filename"]
        assert os.path.isfile(path), f"Expected file at {path}"
        assert Path(path).read_bytes() == content

    def test_delete_removes_file_from_disk(self, api_ctx):
        client, pid, storage, _ = api_ctx
        cr = self._upload_pdf(client, pid, filename="cleanup.txt",
                              content=b"cleanup", description="")
        # txt file needs correct content-type
        cr = client.post(
            f"/api/projects/{pid}/tasks/TASK-01/uploads",
            data={"requirement_id": "REQ-01"},
            files={"file": ("cleanup.txt", io.BytesIO(b"cleanup content"), "text/plain")},
        )
        assert cr.status_code == 200, cr.text
        uid = cr.json()["upload"]["upload_id"]
        record = run(storage.get_remediation_upload(pid, uid))
        path = record["stored_filename"]
        assert os.path.isfile(path)
        client.delete(f"/api/projects/{pid}/uploads/{uid}")
        assert not os.path.isfile(path), "File must be gone after delete"
