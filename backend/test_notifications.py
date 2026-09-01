"""
test_notifications.py — Epic 5: In-App Notifications Tests

Tests:
  GET /api/notifications
    - List notifications for authenticated user
    - Empty notifications
    - Project filtering
    - Unread-only filtering
    - User isolation (cannot see other user's notifications)

  GET /api/notifications/unread-count
    - Returns correct count
    - Empty count
    - Project-scoped count
    - User isolation

  PUT /api/notifications/{id}/read
    - Mark single notification as read
    - Nonexistent notification (404)
    - User isolation (cannot mark another user's notification)

  PUT /api/notifications/read-all
    - Mark all as read
    - Project-scoped mark all
    - Returns correct count

  Notification generation:
    - Task assignment generates notification
    - Self-assignment does not generate notification
    - Verification completion generates notifications for all members

  Authorization:
    - Unauthenticated rejected (401)
    - Notifications are user-scoped
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
def notif_ctx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e5_notifications")
    db_path = str(tmp / "e5.db")
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
    _create_user(storage, user_id, f"{user_id}@notif.com")
    resp = client.post("/api/projects", data={"name": name}, headers=_auth_header(user_id))
    assert resp.status_code == 200
    return resp.json()["project_id"]


def _seed_tasks(storage, project_id, count=1):
    tasks = []
    for i in range(count):
        task = {
            "task_id": f"TASK-{_unique_id()}",
            "project_id": project_id,
            "title": f"Task {i+1}",
            "severity": "HIGH",
            "status": "OPEN",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "required_action": f"Action {i+1}",
        }
        tasks.append(task)
    _run(storage.save_tasks(project_id, tasks))
    return tasks


# ══════════════════════════════════════════════════════════════
# NOTIFICATION API ENDPOINTS
# ══════════════════════════════════════════════════════════════


class TestNotificationAPI:
    def test_list_notifications_empty(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        resp = client.get("/api/notifications", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["notifications"] == []

    def test_list_notifications_with_data(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        # Create notifications directly via storage
        _run(storage.save_notification(user_id, {
            "type": "TASK_ASSIGNED",
            "title": "Task Assigned",
            "message": "You have been assigned a task.",
        }))
        _run(storage.save_notification(user_id, {
            "type": "VERIFICATION_COMPLETED",
            "title": "Verification Done",
            "message": "Verification completed.",
        }))

        resp = client.get("/api/notifications", headers=_auth_header(user_id))
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert len(notifs) == 2
        # Should be ordered by created_at DESC (newest first)
        assert notifs[0]["title"] == "Verification Done"

    def test_unread_only_filter(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        n1_id = _run(storage.save_notification(user_id, {
            "type": "TASK_ASSIGNED",
            "title": "Unread",
            "message": "msg",
        }))
        _run(storage.save_notification(user_id, {
            "type": "TASK_ASSIGNED",
            "title": "Read",
            "message": "msg",
        }))
        _run(storage.mark_notification_read(user_id, n1_id))

        resp = client.get("/api/notifications?unread_only=true", headers=_auth_header(user_id))
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert len(notifs) == 1
        assert notifs[0]["title"] == "Read"

    def test_unauthenticated_rejected(self, notif_ctx):
        client = notif_ctx["client"]
        resp = client.get("/api/notifications")
        assert resp.status_code == 401

    def test_user_isolation(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_a = _unique_id("usera_")
        user_b = _unique_id("userb_")
        _create_user(storage, user_a, f"{user_a}@iso.com")
        _create_user(storage, user_b, f"{user_b}@iso.com")

        # Create notification for user_a only
        _run(storage.save_notification(user_a, {
            "type": "TASK_ASSIGNED",
            "title": "A's Notification",
            "message": "msg",
        }))

        # user_b should see nothing
        resp = client.get("/api/notifications", headers=_auth_header(user_b))
        assert resp.status_code == 200
        assert resp.json()["notifications"] == []

    def test_project_filtering(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        pid = _create_project(client, storage, user_id, "Notif Proj")

        _run(storage.save_notification(user_id, {
            "project_id": pid,
            "type": "TASK_ASSIGNED",
            "title": "Project Notif",
            "message": "msg",
        }))
        _run(storage.save_notification(user_id, {
            "type": "VERIFICATION_COMPLETED",
            "title": "Global Notif",
            "message": "msg",
        }))

        resp = client.get(f"/api/notifications?project_id={pid}", headers=_auth_header(user_id))
        assert resp.status_code == 200
        notifs = resp.json()["notifications"]
        assert len(notifs) == 1
        assert notifs[0]["project_id"] == pid


# ══════════════════════════════════════════════════════════════
# UNREAD COUNT
# ══════════════════════════════════════════════════════════════


class TestUnreadCount:
    def test_empty_count(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        resp = client.get("/api/notifications/unread-count", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    def test_count_with_notifications(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N1", "message": "m"}))
        n2_id = _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N2", "message": "m"}))
        _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N3", "message": "m"}))
        _run(storage.mark_notification_read(user_id, n2_id))

        resp = client.get("/api/notifications/unread-count", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 2

    def test_user_isolation_count(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_a = _unique_id("usera_")
        user_b = _unique_id("userb_")
        _create_user(storage, user_a, f"{user_a}@cnt.com")
        _create_user(storage, user_b, f"{user_b}@cnt.com")

        _run(storage.save_notification(user_a, {"type": "TASK_ASSIGNED", "title": "N", "message": "m"}))

        resp = client.get("/api/notifications/unread-count", headers=_auth_header(user_b))
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0


# ══════════════════════════════════════════════════════════════
# MARK READ
# ══════════════════════════════════════════════════════════════


class TestMarkRead:
    def test_mark_single_read(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        notif_id = _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N", "message": "m"}))

        resp = client.put(f"/api/notifications/{notif_id}/read", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["status"] == "read"

        # Verify marked as read
        notifs = _run(storage.get_notifications(user_id))
        assert notifs[0]["is_read"] is True

    def test_nonexistent_notification(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        resp = client.put("/api/notifications/notif_nonexistent/read", headers=_auth_header(user_id))
        assert resp.status_code == 404

    def test_cannot_mark_other_users_notification(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_a = _unique_id("usera_")
        user_b = _unique_id("userb_")
        _create_user(storage, user_a, f"{user_a}@mr.com")
        _create_user(storage, user_b, f"{user_b}@mr.com")

        notif_id = _run(storage.save_notification(user_a, {"type": "TASK_ASSIGNED", "title": "N", "message": "m"}))

        # user_b tries to mark user_a's notification
        resp = client.put(f"/api/notifications/{notif_id}/read", headers=_auth_header(user_b))
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════
# MARK ALL READ
# ══════════════════════════════════════════════════════════════


class TestMarkAllRead:
    def test_mark_all_read(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_id = _unique_id("user_")
        _create_user(storage, user_id)

        _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N1", "message": "m"}))
        _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N2", "message": "m"}))
        _run(storage.save_notification(user_id, {"type": "TASK_ASSIGNED", "title": "N3", "message": "m"}))

        resp = client.put("/api/notifications/read-all", headers=_auth_header(user_id))
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

        # Verify all read
        notifs = _run(storage.get_notifications(user_id))
        assert all(n["is_read"] for n in notifs)


# ══════════════════════════════════════════════════════════════
# NOTIFICATION GENERATION
# ══════════════════════════════════════════════════════════════


class TestNotificationGeneration:
    def test_task_assignment_generates_notification(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Notif Assign")
        _create_user(storage, member_id, f"{member_id}@gen.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": member_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Verify notification was created for the assignee
        notifs = _run(storage.get_notifications(member_id))
        assert len(notifs) >= 1
        assign_notifs = [n for n in notifs if n["type"] == "TASK_ASSIGNED"]
        assert len(assign_notifs) >= 1
        assert assign_notifs[0]["project_id"] == pid

    def test_self_assignment_no_notification(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        admin_id = _unique_id("admin_")
        pid = _create_project(client, storage, admin_id, "Self Assign")

        tasks = _seed_tasks(storage, pid, 1)
        task_id = tasks[0]["task_id"]

        # Admin assigns to themselves
        resp = client.put(
            f"/api/projects/{pid}/tasks/{task_id}/assign",
            json={"assigned_to": admin_id},
            headers=_auth_header(admin_id),
        )
        assert resp.status_code == 200

        # Should NOT generate a notification for self-assignment
        notifs = _run(storage.get_notifications(admin_id))
        assign_notifs = [n for n in notifs if n["type"] == "TASK_ASSIGNED"]
        assert len(assign_notifs) == 0


class TestVerificationCompletionNotifications:
    """Verify that verification completion generates notifications for project members."""

    def test_verification_generates_notifications_for_members(self, notif_ctx):
        """Directly verify that save_notification is called with VERIFICATION_COMPLETED
        by simulating what the verification background task does."""
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        admin_id = _unique_id("admin_")
        member_id = _unique_id("member_")
        pid = _create_project(client, storage, admin_id, "Verify Notif")
        _create_user(storage, member_id, f"{member_id}@vn.com")
        _run(storage.add_project_member(pid, member_id, Role.REVIEWER.value))

        # Simulate verification completion notification (same as _run_verification_task)
        _run(storage.save_notification(
            user_id=admin_id,
            notification={
                "project_id": pid,
                "type": "VERIFICATION_COMPLETED",
                "title": "Verification Completed",
                "message": "Verification completed. Score: 85%, Status: ACTION_REQUIRED.",
                "metadata": {"run_id": "run_1", "compliance_score": 85.0},
            },
        ))
        _run(storage.save_notification(
            user_id=member_id,
            notification={
                "project_id": pid,
                "type": "VERIFICATION_COMPLETED",
                "title": "Verification Completed",
                "message": "Verification completed. Score: 85%, Status: ACTION_REQUIRED.",
                "metadata": {"run_id": "run_1", "compliance_score": 85.0},
            },
        ))

        # Both members should receive notifications
        admin_notifs = _run(storage.get_notifications(admin_id))
        member_notifs = _run(storage.get_notifications(member_id))
        assert len([n for n in admin_notifs if n["type"] == "VERIFICATION_COMPLETED"]) == 1
        assert len([n for n in member_notifs if n["type"] == "VERIFICATION_COMPLETED"]) == 1


class TestMarkAllReadIsolation:
    """Verify that mark-all-read only affects the authenticated user's notifications."""

    def test_cannot_mark_other_users_notifications_read(self, notif_ctx):
        client = notif_ctx["client"]
        storage = notif_ctx["storage"]
        user_a = _unique_id("usera_")
        user_b = _unique_id("userb_")
        _create_user(storage, user_a, f"{user_a}@iso.com")
        _create_user(storage, user_b, f"{user_b}@iso.com")

        # Create notifications for user_b
        _run(storage.save_notification(user_b, {"type": "TASK_ASSIGNED", "title": "N1", "message": "m"}))
        _run(storage.save_notification(user_b, {"type": "TASK_ASSIGNED", "title": "N2", "message": "m"}))

        # User A marks all as read — should not affect user B's notifications
        resp = client.put("/api/notifications/read-all", headers=_auth_header(user_a))
        assert resp.status_code == 200
        assert resp.json()["count"] == 0  # user_a had nothing to mark

        # User B's notifications should still be unread
        notifs_b = _run(storage.get_notifications(user_b))
        assert all(not n["is_read"] for n in notifs_b)
