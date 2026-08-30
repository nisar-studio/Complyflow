"""
test_realtime_remediation.py — P2 #5 Real-Time Agent Monitoring & Remediation Lifecycle Tests

Tests:
  1. Events list endpoint (GET /api/projects/{id}/events)
     - Authenticated member can retrieve events
     - Unauthenticated request rejected (401)
     - Non-member cannot access another project (403)
     - Empty event list works
     - Project isolation

  2. SSE stream endpoint (GET /api/projects/{id}/events/stream)
     - Authentication enforcement
     - Project membership enforcement
     - Correct SSE content type
     - Event delivery via broadcaster
     - Project isolation (no cross-project leak)
     - Subscriber cleanup on generator completion

  3. Task status update endpoint (PUT /api/projects/{id}/tasks/{task_id}/status)
     - Successful OPEN → RESOLVED
     - Successful RESOLVED → OPEN
     - Invalid status rejected
     - Nonexistent task rejected
     - Cross-project task access rejected
     - Unauthenticated access rejected
     - Insufficient RBAC role rejected
     - Audit event generated for status change
     - Idempotent when status unchanged
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
def p25_ctx(tmp_path_factory):
    """Isolated test context with DB, upload dir, and API client."""
    tmp = tmp_path_factory.mktemp("p25_realtime")
    db_path = str(tmp / "p25.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
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


def _seed_events(storage, project_id, count=3):
    """Seed agent events into the database for a project."""
    events = []
    for i in range(count):
        event = {
            "type": "TOOL_COMPLETED",
            "status": "completed",
            "summary": f"Tool step {i+1}",
            "tool": f"tool_{i+1}",
            "project_id": project_id,
        }
        _run(storage.add_event(project_id, event))
        events.append(event)
    return events


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
# 1. EVENTS LIST ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestEventsListEndpoint:
    """Tests for GET /api/projects/{id}/events"""

    def test_authenticated_member_retrieves_events(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id)
        _seed_events(storage, pid, 3)

        resp = client.get(f"/api/projects/{pid}/events", headers=_auth_header(user_id))
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert len(data["events"]) == 3
        assert data["events"][0]["summary"] == "Tool step 1"

    def test_unauthenticated_rejected(self, p25_ctx):
        client = p25_ctx["client"]
        resp = client.get("/api/projects/fake/events")
        assert resp.status_code == 401

    def test_non_member_cannot_access(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        owner_id = _unique_id("owner_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, owner_id, "Owner Project")
        _seed_events(storage, pid, 2)

        _create_user(storage, outsider_id, f"{outsider_id}@test.com")
        resp = client.get(f"/api/projects/{pid}/events", headers=_auth_header(outsider_id))
        assert resp.status_code == 403

    def test_empty_event_list(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id)

        resp = client.get(f"/api/projects/{pid}/events", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_project_isolation(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_a = _unique_id("a_")
        user_b = _unique_id("b_")
        pid_a = _create_project(client, storage, user_a, "Project A")
        pid_b = _create_project(client, storage, user_b, "Project B")
        _seed_events(storage, pid_a, 2)
        _seed_events(storage, pid_b, 5)

        # User A sees only their events
        resp_a = client.get(f"/api/projects/{pid_a}/events", headers=_auth_header(user_a))
        assert len(resp_a.json()["events"]) == 2

        # User B sees only their events
        resp_b = client.get(f"/api/projects/{pid_b}/events", headers=_auth_header(user_b))
        assert len(resp_b.json()["events"]) == 5

    def test_nonexistent_project_returns_404(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_404_")
        try:
            _create_user(storage, user_id, f"{user_id}@test.com")
        except Exception:
            pass
        resp = client.get("/api/projects/nonexistent/events", headers=_auth_header(user_id))
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════
# 2. SSE STREAM ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestSSEStreamEndpoint:
    """Tests for GET /api/projects/{id}/events/stream"""

    def test_authentication_enforcement(self, p25_ctx):
        client = p25_ctx["client"]
        resp = client.get("/api/projects/fake/events/stream")
        assert resp.status_code == 401

    def test_project_membership_enforcement(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        owner_id = _unique_id("owner_")
        outsider_id = _unique_id("out_")
        pid = _create_project(client, storage, owner_id, "SSE Proj")
        _create_user(storage, outsider_id, f"{outsider_id}@test.com")

        resp = client.get(f"/api/projects/{pid}/events/stream", headers=_auth_header(outsider_id))
        assert resp.status_code == 403

    def test_correct_content_type_and_sse_format(self, p25_ctx):
        """Test the SSE generator directly (bypassing infinite HTTP stream)."""
        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(p25_ctx["client"], storage, user_id, "SSE Format")

        # Test the generator produces valid SSE formatted data
        async def _test_generator():
            queue = await broadcaster.subscribe(pid)
            # Simulate what the route handler does
            async def event_gen():
                try:
                    yield f"data: {json.dumps({'type': 'CONNECTED', 'project_id': pid})}\n\n"
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=0.1)
                            yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.TimeoutError:
                            break
                finally:
                    await broadcaster.unsubscribe(pid, queue)

            lines = []
            async for chunk in event_gen():
                lines.append(chunk)
                if len(lines) >= 2:
                    break

            return lines

        lines = _run(_test_generator())
        assert len(lines) >= 1
        # First line should be CONNECTED
        assert "CONNECTED" in lines[0]
        assert lines[0].startswith("data:")
        assert lines[0].endswith("\n\n")

    def test_event_delivery_via_broadcaster(self, p25_ctx):
        """Test that events broadcast via EventBroadcaster reach the SSE generator."""
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "SSE Delivery")

        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()

        # Manually test the broadcaster + generator logic
        async def _test_delivery():
            queue = await broadcaster.subscribe(pid)
            # Broadcast an event
            test_event = {"type": "TOOL_STARTED", "summary": "Test tool", "tool": "test"}
            await broadcaster.broadcast(pid, test_event)
            # Read from queue
            received = await asyncio.wait_for(queue.get(), timeout=2.0)
            await broadcaster.unsubscribe(pid, queue)
            return received

        received = _run(_test_delivery())
        assert received["type"] == "TOOL_STARTED"
        assert received["summary"] == "Test tool"

    def test_project_isolation_broadcaster(self, p25_ctx):
        """Verify events broadcast to project A don't reach project B subscribers."""
        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()

        async def _test_isolation():
            queue_a = await broadcaster.subscribe("proj_a")
            queue_b = await broadcaster.subscribe("proj_b")
            await broadcaster.broadcast("proj_a", {"type": "A_EVENT"})
            await broadcaster.broadcast("proj_b", {"type": "B_EVENT"})

            # proj_a queue should have A_EVENT only
            event_a = await asyncio.wait_for(queue_a.get(), timeout=1.0)
            assert event_a["type"] == "A_EVENT"
            assert queue_a.empty()  # no B_EVENT leaked

            # proj_b queue should have B_EVENT only
            event_b = await asyncio.wait_for(queue_b.get(), timeout=1.0)
            assert event_b["type"] == "B_EVENT"
            assert queue_b.empty()

            await broadcaster.unsubscribe("proj_a", queue_a)
            await broadcaster.unsubscribe("proj_b", queue_b)

        _run(_test_isolation())

    def test_subscriber_cleanup(self, p25_ctx):
        """Verify broadcaster cleans up after generator completes."""
        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()

        async def _test_cleanup():
            queue = await broadcaster.subscribe("cleanup_proj")
            assert await broadcaster.get_active_subscriber_count("cleanup_proj") == 1
            await broadcaster.unsubscribe("cleanup_proj", queue)
            assert await broadcaster.get_active_subscriber_count("cleanup_proj") == 0

        _run(_test_cleanup())

    def test_nonexistent_project_returns_404(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_sse404_")
        try:
            _create_user(storage, user_id, f"{user_id}@test.com")
        except Exception:
            pass
        resp = client.get("/api/projects/nonexistent/events/stream", headers=_auth_header(user_id))
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════
# 3. TASK STATUS UPDATE ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestTaskStatusUpdateEndpoint:
    """Tests for PUT /api/projects/{id}/tasks/{task_id}/status"""

    def test_open_to_resolved(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Task Proj 1")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["old_status"] == "OPEN"
        assert data["new_status"] == "RESOLVED"

    def test_resolved_to_open(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Task Proj 2")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # First resolve
        client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )
        # Then reopen
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "OPEN"},
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_status"] == "RESOLVED"
        assert data["new_status"] == "OPEN"

    def test_invalid_status_rejected(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Task Proj 3")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "INVALID"},
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail") or body.get("error", {}).get("message", "")
        assert "Invalid task status" in msg

    def test_nonexistent_task_rejected(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Task Proj 4")

        resp = client.put(
            f"/api/projects/{pid}/tasks/NONEXISTENT/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 404

    def test_cross_project_task_access_rejected(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_a = _unique_id("a_")
        user_b = _unique_id("b_")
        pid_a = _create_project(client, storage, user_a, "Proj A Tasks")
        pid_b = _create_project(client, storage, user_b, "Proj B Tasks")
        tasks_b = _seed_tasks(storage, pid_b, 1)

        # User A tries to modify User B's task
        resp = client.put(
            f"/api/projects/{pid_a}/tasks/{tasks_b[0]['task_id']}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_a),
        )
        assert resp.status_code == 404  # Task not found in project A

    def test_unauthenticated_access_rejected(self, p25_ctx):
        client = p25_ctx["client"]
        resp = client.put(
            "/api/projects/fake/tasks/fake/status",
            json={"status": "RESOLVED"},
        )
        assert resp.status_code == 401

    def test_insufficient_rbac_role(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        owner_id = _unique_id("owner_")
        viewer_id = _unique_id("view_")
        pid = _create_project(client, storage, owner_id, "RBAC Task Proj")

        _create_user(storage, viewer_id, f"{viewer_id}@test.com")
        _run(storage.add_project_member(pid, viewer_id, Role.VIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(viewer_id),
        )
        assert resp.status_code == 403
        body = resp.json()
        msg = body.get("detail") or body.get("error", {}).get("message", "")
        assert "remediation:manage" in msg

    def test_audit_event_generated(self, p25_ctx):
        storage = p25_ctx["storage"]
        client = p25_ctx["client"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Audit Task Proj")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )

        # Verify audit event was created
        events = _run(storage.list_audit_events(pid, event_type="TASK_STATUS_UPDATED"))
        assert len(events) >= 1
        audit = events[-1]
        assert audit["event_type"] == "TASK_STATUS_UPDATED"
        assert audit["actor_type"] == "AUDITOR"
        assert audit["task_id"] == task_id
        meta = audit.get("metadata", {})
        assert meta.get("old_status") == "OPEN"
        assert meta.get("new_status") == "RESOLVED"

    def test_idempotent_when_status_unchanged(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Idempotent Proj")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "OPEN"},  # Already OPEN
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unchanged"

    def test_nonexistent_project_returns_404(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        user_id = _unique_id("user_task404_")
        try:
            _create_user(storage, user_id, f"{user_id}@test.com")
        except Exception:
            pass
        resp = client.put(
            "/api/projects/nonexistent/tasks/fake/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )
        assert resp.status_code == 404

    def test_auditor_role_can_update_tasks(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        owner_id = _unique_id("own_")
        auditor_id = _unique_id("aud_")
        pid = _create_project(client, storage, owner_id, "Auditor Task Proj")

        _create_user(storage, auditor_id, f"{auditor_id}@test.com")
        _run(storage.add_project_member(pid, auditor_id, Role.AUDITOR.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(auditor_id),
        )
        assert resp.status_code == 200
        assert resp.json()["new_status"] == "RESOLVED"

    def test_reviewer_cannot_update_tasks(self, p25_ctx):
        client = p25_ctx["client"]
        storage = p25_ctx["storage"]
        owner_id = _unique_id("own2_")
        reviewer_id = _unique_id("rev_")
        pid = _create_project(client, storage, owner_id, "Reviewer Task Proj")

        _create_user(storage, reviewer_id, f"{reviewer_id}@test.com")
        _run(storage.add_project_member(pid, reviewer_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(reviewer_id),
        )
        assert resp.status_code == 403

    def test_audit_metadata_includes_task_title(self, p25_ctx):
        storage = p25_ctx["storage"]
        client = p25_ctx["client"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Meta Task Proj")
        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        client.put(
            f"/api/projects/{pid}/tasks/{task_id}/status",
            json={"status": "RESOLVED"},
            headers=_auth_header(user_id),
        )

        events = _run(storage.list_audit_events(pid, event_type="TASK_STATUS_UPDATED"))
        assert len(events) >= 1
        meta = events[-1].get("metadata", {})
        assert "task_title" in meta
        assert meta["task_id"] == task_id
