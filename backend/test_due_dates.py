"""
test_due_dates.py — Epic 2: Due Dates & SLA Tracking Tests

Tests:
  PUT /api/projects/{project_id}/tasks/{task_id}/due-date
    - Set due date on task
    - Change existing due date
    - Clear due date
    - Unauthenticated request rejected (401)
    - Non-member cannot set due date (403)
    - REVIEWER cannot set due date (403)
    - Nonexistent task (404)
    - Project not found (404)
    - Invalid due_date format (400)
    - Audit event generated for due date set
    - Audit event generated for due date clear
    - Due date does not block verification (informational only)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.migration_service import run_pending_migrations
from app.services.auth_service import (
    create_session_token,
    hash_password,
    Role,
)


# ── Helpers ─────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _unique_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def e2_ctx(tmp_path_factory):
    """Isolated test context with DB, upload dir, and API client."""
    tmp = tmp_path_factory.mktemp("e2_due_dates")
    db_path = str(tmp / "e2.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    _run(run_pending_migrations(db_path))
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir
    document_service = routes_module._document_service
    document_service.upload_dir = upload_dir

    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
    }

    routes_module.settings.upload_dir = original_upload_dir
    document_service.upload_dir = original_upload_dir
    storage_module._storage_instance = original_instance


def _auth_header(user_id: str) -> dict:
    token = create_session_token(user_id, f"{user_id}@test.com")
    return {"Authorization": f"Bearer {token}"}


def _create_user(storage, user_id, email=None):
    email = email or f"{user_id}@test.com"
    return _run(storage.create_user({
        "user_id": user_id,
        "email": email,
        "name": f"User {user_id}",
        "password_hash": hash_password("TestPass123!"),
        "is_active": True,
    }))


def _create_project(client, storage, user_id, name=None):
    name = name or f"Proj {_unique_id()}"
    _create_user(storage, user_id, f"{user_id}@proj.com")
    resp = client.post("/api/projects", data={"name": name}, headers=_auth_header(user_id))
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _seed_tasks(storage, project_id, count=1):
    tasks = []
    for i in range(count):
        task = {
            "task_id": f"TASK-{_unique_id()}",
            "project_id": project_id,
            "title": f"Remediation Task {i+1}",
            "severity": "HIGH",
            "status": "OPEN",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "required_action": f"Complete step {i+1}",
        }
        tasks.append(task)
    _run(storage.save_tasks(project_id, tasks))
    return tasks


# ══════════════════════════════════════════════════════════════
# 1. DUE DATE ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestDueDateEndpoint:
    """Tests for PUT /api/projects/{id}/tasks/{task_id}/due-date"""

    def test_set_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "DueDate Set")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        due = "2026-12-31T23:59:59Z"
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": due},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["due_date"] == due

        # Verify in storage
        updated = _run(storage.get_tasks(pid))
        task = next(t for t in updated if t["task_id"] == task_id)
        assert task["due_date"] == due

    def test_change_existing_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "DueDate Change")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # Set initial due date
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-06-15T12:00:00Z"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Change it
        new_due = "2026-12-31T23:59:59Z"
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": new_due},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        assert resp.json()["due_date"] == new_due

    def test_clear_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "DueDate Clear")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # Set then clear
        client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-06-15T12:00:00Z"},
            headers=_auth_header(admin_id),
        )
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": None},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        assert resp.json()["due_date"] is None

        # Verify cleared
        updated = _run(storage.get_tasks(pid))
        task = next(t for t in updated if t["task_id"] == task_id)
        assert task.get("due_date") is None

    def test_unauthenticated_rejected(self, e2_ctx):
        client = e2_ctx["client"]
        resp = client.put(
            "/api/projects/fake/tasks/fake/due-date",
            json={"due_date": "2026-12-31T00:00:00Z"},
        )
        assert resp.status_code == 401

    def test_non_member_cannot_set_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, admin_id, "DueDate Isolation")
        _create_user(storage, outsider_id, f"{outsider_id}@out.com")

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-12-31T00:00:00Z"},
            headers=_auth_header(outsider_id),
        )
        assert resp.status_code == 403

    def test_reviewer_cannot_set_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        reviewer_id = _unique_id("rev_")
        pid = _create_project(client, storage, admin_id, "DueDate Reviewer")
        _create_user(storage, reviewer_id, f"{reviewer_id}@rev.com")
        _run(storage.add_project_member(pid, reviewer_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-12-31T00:00:00Z"},
            headers=_auth_header(reviewer_id),
        )
        assert resp.status_code == 403

    def test_nonexistent_task(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "DueDate NoTask")

        resp = client.put(
            f"/api/projects/{pid}/tasks/TASK-nonexistent/due-date",
            json={"due_date": "2026-12-31T00:00:00Z"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 404

    def test_project_not_found(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        _create_user(storage, admin_id, f"{admin_id}@pnf.com")

        resp = client.put(
            "/api/projects/nonexistent/tasks/TASK-x/due-date",
            json={"due_date": "2026-12-31T00:00:00Z"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 404

    def test_invalid_due_date_format(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "DueDate BadFormat")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "not-a-date"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400
        msg = str(resp.json())
        assert "due_date" in msg.lower() or "invalid" in msg.lower()

    def test_audit_event_on_set(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("audit_")
        pid = _create_project(client, storage, admin_id, "DueDate Audit Set")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-12-31T23:59:59Z"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        resp_audit = client.get(f"/api/projects/{pid}/audit-events", headers=_auth_header(admin_id))
        assert resp_audit.status_code == 200
        events = resp_audit.json().get("events", [])
        due_events = [e for e in events if e.get("event_type") == "TASK_DUE_DATE_UPDATED"]
        assert len(due_events) >= 1
        event = due_events[0]  # newest first (DESC order)
        assert event["task_id"] == task_id
        assert event["actor_id"] == admin_id
        meta = event.get("metadata", {})
        assert meta.get("action") == "set"
        assert meta.get("new_due_date") == "2026-12-31T23:59:59Z"

    def test_audit_event_on_clear(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        admin_id = _unique_id("audit_")
        pid = _create_project(client, storage, admin_id, "DueDate Audit Clear")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # Set first
        client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-06-15T12:00:00Z"},
            headers=_auth_header(admin_id),
        )
        # Then clear
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": None},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        resp_audit = client.get(f"/api/projects/{pid}/audit-events", headers=_auth_header(admin_id))
        events = resp_audit.json().get("events", [])
        due_events = [e for e in events if e.get("event_type") == "TASK_DUE_DATE_UPDATED"]
        assert len(due_events) >= 1
        clear_event = due_events[0]  # newest first (DESC order)
        meta = clear_event.get("metadata", {})
        assert meta.get("action") == "cleared"
        assert meta.get("new_due_date") is None

    def test_auditor_can_set_due_date(self, e2_ctx):
        client = e2_ctx["client"]
        storage = e2_ctx["storage"]
        auditor_id = _unique_id("aud_")
        pid = _create_project(client, storage, auditor_id, "DueDate Auditor")
        _run(storage.update_project_member_role(pid, auditor_id, Role.AUDITOR.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/due-date",
            json={"due_date": "2026-12-31T23:59:59Z"},
            headers=_auth_header(auditor_id),
        )
        assert resp.status_code == 200
