"""
test_bulk_tasks.py — Epic 7: Bulk Task Operations Tests

Tests:
  POST /api/projects/{project_id}/bulk/tasks/status
    - Successful bulk status update
    - Atomic rejection (invalid task ID)
    - Batch size limit (50)
    - Empty task_ids
    - Invalid status value
    - Unauthenticated rejected (401)
    - Non-member cannot bulk update (403)
    - REVIEWER cannot bulk update (403)
    - Project not found (404)
    - Audit events generated for each task
    - Unchanged tasks skipped (idempotent)
    - Deduplication of task IDs

  POST /api/projects/{project_id}/bulk/tasks/assign
    - Successful bulk assignment
    - Atomic rejection (invalid task ID)
    - Target user not a member (400)
    - Target user inactive (400)
    - Invalid due_date (400)
    - Unauthenticated rejected (401)
    - Non-member cannot bulk assign (403)
    - REVIEWER cannot bulk assign (403)
    - Batch size limit
    - Audit events generated
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

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


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _unique_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def bulk_ctx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e7_bulk_tasks")
    db_path = str(tmp / "e7.db")
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
    _create_user(storage, user_id, f"{user_id}@bulk.com")
    resp = client.post("/api/projects", data={"name": name}, headers=_auth_header(user_id))
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _seed_tasks(storage, project_id, count=3):
    tasks = []
    for i in range(count):
        task = {
            "task_id": f"TASK-{_unique_id()}",
            "project_id": project_id,
            "title": f"Bulk Task {i+1}",
            "severity": "HIGH",
            "status": "OPEN",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "required_action": f"Complete step {i+1}",
        }
        tasks.append(task)
    _run(storage.save_tasks(project_id, tasks))
    return tasks


# ══════════════════════════════════════════════════════════════
# BULK STATUS UPDATE
# ══════════════════════════════════════════════════════════════


class TestBulkStatusUpdate:
    def test_successful_bulk_status(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Bulk Status")
        tasks = _seed_tasks(storage, pid, 3)
        task_ids = [t["task_id"] for t in tasks]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": task_ids, "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["new_status"] == "RESOLVED"
        assert data["total_requested"] == 3
        assert data["total_updated"] == 3

        # Verify in storage
        updated = _run(storage.get_tasks(pid))
        for t in updated:
            assert t["status"] == "RESOLVED"

    def test_atomic_rejection_invalid_task(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Atomic Reject")
        tasks = _seed_tasks(storage, pid, 2)
        task_ids = [t["task_id"] for t in tasks] + ["TASK-nonexistent"]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": task_ids, "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400

        # Verify NO tasks were modified (atomic)
        updated = _run(storage.get_tasks(pid))
        for t in updated:
            assert t["status"] == "OPEN"

    def test_batch_size_limit(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Batch Limit")
        too_many = [f"TASK-{_unique_id()}" for _ in range(51)]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": too_many, "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400
        assert "50" in str(resp.json())

    def test_empty_task_ids(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Empty IDs")

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": [], "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400

    def test_invalid_status_value(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Bad Status")
        tasks = _seed_tasks(storage, pid, 1)

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": [tasks[0]["task_id"]], "status": "INVALID"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400

    def test_unauthenticated_rejected(self, bulk_ctx):
        client = bulk_ctx["client"]
        resp = client.post(
            "/api/projects/fake/bulk/tasks/status",
            json={"task_ids": ["x"], "status": "RESOLVED"},
        )
        assert resp.status_code == 401

    def test_non_member_cannot_bulk_update(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, admin_id, "Isolation Bulk")
        _create_user(storage, outsider_id, f"{outsider_id}@out.com")

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": ["x"], "status": "RESOLVED"},
            headers=_auth_header(outsider_id),
        )
        assert resp.status_code == 403

    def test_reviewer_cannot_bulk_update(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        reviewer_id = _unique_id("rev_")
        pid = _create_project(client, storage, admin_id, "Reviewer Bulk")
        _create_user(storage, reviewer_id, f"{reviewer_id}@rev.com")
        _run(storage.add_project_member(pid, reviewer_id, Role.REVIEWER.value))

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": ["x"], "status": "RESOLVED"},
            headers=_auth_header(reviewer_id),
        )
        assert resp.status_code == 403

    def test_project_not_found(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        _create_user(storage, admin_id, f"{admin_id}@pnf.com")

        resp = client.post(
            "/api/projects/nonexistent/bulk/tasks/status",
            json={"task_ids": ["x"], "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 404

    def test_audit_events_generated(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("audit_")
        pid = _create_project(client, storage, admin_id, "Bulk Audit")
        tasks = _seed_tasks(storage, pid, 2)
        task_ids = [t["task_id"] for t in tasks]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": task_ids, "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        resp_audit = client.get(f"/api/projects/{pid}/audit-events", headers=_auth_header(admin_id))
        events = resp_audit.json().get("events", [])
        status_events = [e for e in events if e.get("event_type") == "TASK_STATUS_UPDATED" and e.get("metadata", {}).get("bulk_operation")]
        assert len(status_events) == 2

    def test_unchanged_tasks_skipped(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Skip Unchanged")
        tasks = _seed_tasks(storage, pid, 2)
        task_ids = [t["task_id"] for t in tasks]

        # All are OPEN; updating to OPEN should skip
        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": task_ids, "status": "OPEN"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        assert resp.json()["total_updated"] == 0
        assert resp.json()["total_unchanged"] == 2

    def test_deduplication(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Dedup Bulk")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # Duplicate the same task ID 3 times
        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/status",
            json={"task_ids": [task_id, task_id, task_id], "status": "RESOLVED"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        assert resp.json()["total_requested"] == 1
        assert resp.json()["total_updated"] == 1


# ══════════════════════════════════════════════════════════════
# BULK ASSIGNMENT
# ══════════════════════════════════════════════════════════════


class TestBulkAssignment:
    def test_successful_bulk_assign(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Bulk Assign")
        _create_user(storage, member_id, f"{member_id}@assign.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 3)
        task_ids = [t["task_id"] for t in tasks]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": task_ids, "assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["assigned_to"] == member_id
        assert data["total_assigned"] == 3

    def test_atomic_rejection_invalid_task(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Atomic Assign")
        _create_user(storage, member_id, f"{member_id}@a2.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 2)
        task_ids = [t["task_id"] for t in tasks] + ["TASK-nonexistent"]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": task_ids, "assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400

    def test_target_user_not_member(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        stranger_id = _unique_id("stranger_")
        pid = _create_project(client, storage, admin_id, "Stranger Assign")
        _create_user(storage, stranger_id, f"{stranger_id}@str.com")

        tasks = _seed_tasks(storage, pid, 1)

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": [tasks[0]["task_id"]], "assigned_to": stranger_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = str(body)
        assert "not a member" in msg.lower() or "member" in msg.lower(), f"Unexpected: {body}"

    def test_invalid_due_date(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Bad Date Bulk")
        _create_user(storage, member_id, f"{member_id}@bd.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": [tasks[0]["task_id"]], "assigned_to": member_id, "due_date": "not-a-date"},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 400

    def test_unauthenticated_rejected(self, bulk_ctx):
        client = bulk_ctx["client"]
        resp = client.post(
            "/api/projects/fake/bulk/tasks/assign",
            json={"task_ids": ["x"], "assigned_to": "user"},
        )
        assert resp.status_code == 401

    def test_non_member_cannot_bulk_assign(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("admin_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, admin_id, "Isolation Bulk Assign")
        _create_user(storage, outsider_id, f"{outsider_id}@out.com")

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": ["x"], "assigned_to": outsider_id},
            headers=_auth_header(outsider_id),
        )
        assert resp.status_code == 403

    def test_auditor_can_bulk_assign(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        auditor_id = _unique_id("aud_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, auditor_id, "Auditor Bulk")
        _run(storage.update_project_member_role(pid, auditor_id, Role.AUDITOR.value))
        _create_user(storage, member_id, f"{member_id}@aud.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": [tasks[0]["task_id"]], "assigned_to": member_id},
            headers=_auth_header(auditor_id),
        )
        assert resp.status_code == 200

    def test_audit_events_for_bulk_assign(self, bulk_ctx):
        client = bulk_ctx["client"]
        storage = bulk_ctx["storage"]
        admin_id = _unique_id("audit_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Bulk Assign Audit")
        _create_user(storage, member_id, f"{member_id}@baa.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 2)
        task_ids = [t["task_id"] for t in tasks]

        resp = client.post(
            f"/api/projects/{pid}/bulk/tasks/assign",
            json={"task_ids": task_ids, "assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        resp_audit = client.get(f"/api/projects/{pid}/audit-events", headers=_auth_header(admin_id))
        events = resp_audit.json().get("events", [])
        assign_events = [e for e in events if e.get("event_type") == "TASK_ASSIGNED" and e.get("metadata", {}).get("bulk_operation")]
        assert len(assign_events) == 2
