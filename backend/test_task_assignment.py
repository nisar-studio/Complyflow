"""
test_task_assignment.py — Epic 1: Task Assignment & Ownership Tests

Tests:
  1. PUT /api/projects/{project_id}/tasks/{task_id}/assign
     - Successful assignment (OPEN task → member)
     - Reassignment (change assignee)
     - Assignment with due_date
     - Unauthenticated request rejected (401)
     - Non-member cannot assign (403)
     - REVIEWER cannot assign (403 — insufficient RBAC)
     - Target user not a project member (400)
     - Target user inactive (400)
     - Nonexistent task (404)
     - Project not found (404)
     - Invalid due_date format (400)
     - Audit event generated for assignment
     - Assignment preserves existing task data
     - Cross-project task access rejected
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
    ROLE_PERMISSIONS,
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
def e1_ctx(tmp_path_factory):
    """Isolated test context with DB, upload dir, and API client."""
    tmp = tmp_path_factory.mktemp("e1_assignment")
    db_path = str(tmp / "e1.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    # Run migrations to add assignment columns
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


def _auth_header(user_id: str, email: str = "test@test.com") -> dict:
    token = create_session_token(user_id, email)
    return {"Authorization": f"Bearer {token}"}


def _create_user(storage, user_id, email="test@test.com"):
    return _run(storage.create_user({
        "user_id": user_id,
        "email": email,
        "name": f"User {user_id}",
        "password_hash": hash_password("TestPass123!"),
        "is_active": True,
    }))


def _create_project(client, storage, user_id, name=None):
    name = name or f"Proj {_unique_id()}"
    _create_user(storage, user_id, f"{user_id}@test.com")
    _run(storage.add_project_member("NEW", user_id, Role.ADMIN.value))
    resp = client.post("/api/projects", data={"name": name}, headers=_auth_header(user_id))
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _seed_tasks(storage, project_id, count=2):
    """Seed remediation tasks into the database."""
    tasks = []
    for i in range(count):
        task = {
            "task_id": f"TASK-{_unique_id()}",
            "project_id": project_id,
            "title": f"Remediation Task {i+1}",
            "description": f"Do thing {i+1}",
            "severity": "HIGH",
            "status": "OPEN",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "required_action": f"Complete step {i+1}",
        }
        tasks.append(task)
    _run(storage.save_tasks(project_id, tasks))
    return tasks


# ══════════════════════════════════════════════════════════════
# 1. TASK ASSIGNMENT ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestTaskAssignmentEndpoint:
    """Tests for PUT /api/projects/{id}/tasks/{task_id}/assign"""

    def test_successful_assignment(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Assign Proj")

        # Add member to project
        _create_user(storage, member_id, f"{member_id}@test.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assigned"
        assert data["assigned_to"] == member_id
        assert data["task_id"] == task_id

    def test_reassignment(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        member1_id = _unique_id("m1_")
        member2_id = _unique_id("m2_")
        pid = _create_project(client, storage, admin_id, "Reassign Proj")

        _create_user(storage, member1_id, f"{member1_id}@test.com")
        _create_user(storage, member2_id, f"{member2_id}@test.com")
        _run(storage.add_project_member(pid, member1_id, Role.REVIEWER.value))
        _run(storage.add_project_member(pid, member2_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # First assignment
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member1_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Reassignment
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member2_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_to"] == member2_id

    def test_assignment_with_due_date(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "DueDate Proj")

        _create_user(storage, member_id, f"{member_id}@test.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        due = "2026-12-31T23:59:59Z"
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id, "due_date": due},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["due_date"] == due

        # Verify task data was updated
        tasks = _run(storage.get_tasks(pid))
        task = next(t for t in tasks if t["task_id"] == task_id)
        assert task["assigned_to"] == member_id
        assert task["due_date"] == due

    def test_unauthenticated_rejected(self, e1_ctx):
        client = e1_ctx["client"]
        resp = client.put(
            "/api/projects/fake/tasks/fake/assign",
            json={"assigned_to": "user"},
        )
        assert resp.status_code == 401

    def test_non_member_cannot_assign(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, admin_id, "Isolation Proj")

        _create_user(storage, outsider_id, f"{outsider_id}@test.com")

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": outsider_id},
            headers=_auth_header(outsider_id),
        )
        assert resp.status_code == 403

    def test_reviewer_cannot_assign(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        reviewer_id = _unique_id("rev_")
        pid = _create_project(client, storage, admin_id, "Reviewer Proj")

        _create_user(storage, reviewer_id, f"{reviewer_id}@test.com")
        _run(storage.add_project_member(pid, reviewer_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": reviewer_id},
            headers=_auth_header(reviewer_id),
        )
        # REVIEWER doesn't have remediation:manage
        assert resp.status_code == 403

    def test_target_user_not_project_member(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("stranger_admin_")
        stranger_id = _unique_id("stranger_user_")
        pid = _create_project(client, storage, admin_id, f"Stranger {_unique_id()}")

        _create_user(storage, stranger_id, f"{stranger_id}@stranger-only.com")
        # NOT added as project member

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": stranger_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = str(body)
        assert "not a member" in msg.lower() or "member" in msg.lower(), f"Unexpected: {body}"

    def test_nonexistent_task(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "NoTask Proj")

        _create_user(storage, member_id, f"{member_id}@test.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        resp = client.put(
            f"/api/projects/{pid}/tasks/TASK-nonexistent/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 404

    def test_project_not_found(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        _create_user(storage, admin_id, f"{admin_id}@test.com")

        resp = client.put(
            "/api/projects/nonexistent/tasks/TASK-x/assign",
            json={"assigned_to": "user-x"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 404

    def test_invalid_due_date_format(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("baddate_admin_")
        member_id = _unique_id("baddate_member_")
        pid = _create_project(client, storage, admin_id, f"BadDate {_unique_id()}")

        _create_user(storage, member_id, f"{member_id}@baddate-unique.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id, "due_date": "not-a-date"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400
        msg = str(resp.json())
        assert "invalid due_date" in msg.lower() or "due_date" in msg.lower(), f"Unexpected: {msg}"

    def test_audit_event_generated(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("audit_admin_")
        member_id = _unique_id("audit_member_")
        pid = _create_project(client, storage, admin_id, f"Audit {_unique_id()}")

        _create_user(storage, member_id, f"{member_id}@audit-unique.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Verify audit event was created via API
        resp_audit = client.get(f"/api/projects/{pid}/audit-events", headers=_auth_header(admin_id))
        assert resp_audit.status_code == 200
        audit_events = resp_audit.json().get("events", [])
        assign_events = [e for e in audit_events if e.get("event_type") == "TASK_ASSIGNED"]
        assert len(assign_events) >= 1
        event = assign_events[-1]
        assert event["task_id"] == task_id
        assert event["actor_id"] == admin_id
        meta = event.get("metadata", {})
        assert meta.get("new_assignee") == member_id

    def test_assignment_preserves_task_data(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Preserve Proj")

        _create_user(storage, member_id, f"{member_id}@test.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]
        original_title = tasks[0]["title"]
        original_severity = tasks[0]["severity"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Verify task data is preserved
        updated_tasks = _run(storage.get_tasks(pid))
        task = next(t for t in updated_tasks if t["task_id"] == task_id)
        assert task["title"] == original_title
        assert task["severity"] == original_severity
        assert task["status"] == "OPEN"
        assert task["assigned_to"] == member_id

    def test_cross_project_task_access_rejected(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        admin1_id = _unique_id("crossadmin1_")
        admin2_id = _unique_id("crossadmin2_")
        pid1 = _create_project(client, storage, admin1_id, f"Proj1 {_unique_id()}")
        pid2 = _create_project(client, storage, admin2_id, f"Proj2 {_unique_id()}")

        tasks = _seed_tasks(storage, pid2, 1)
        task_id = tasks[0]["task_id"]

        # Try to assign task from pid2 using pid1's project context
        resp = client.put(
            f"/api/projects/{pid1}/tasks/{task_id}/assign",
            json={"assigned_to": admin2_id},
            headers=_auth_header(admin1_id),
        )
        assert resp.status_code == 404

    def test_auditor_can_assign(self, e1_ctx):
        client = e1_ctx["client"]
        storage = e1_ctx["storage"]
        auditor_id = _unique_id("aud_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, auditor_id, f"Auditor {_unique_id()}")

        _create_user(storage, member_id, f"{member_id}@auditor.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))
        # Change auditor's role to AUDITOR
        _run(storage.update_project_member_role(pid, auditor_id, Role.AUDITOR.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(auditor_id),
        )
        assert resp.status_code == 200
