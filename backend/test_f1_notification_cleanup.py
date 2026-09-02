"""
test_f1_notification_cleanup.py — Regression test for F-1 fix

Verifies that deleting a project also cleans up its associated notifications,
preventing orphaned notification records from persisting after project deletion.
"""
from __future__ import annotations

import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.migration_service import run_pending_migrations


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def f1_ctx(tmp_path_factory):
    """Isolated storage for F-1 notification cleanup tests."""
    tmp = tmp_path_factory.mktemp("f1_notification_cleanup")
    db_path = str(tmp / "f1.db")

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    # Run migrations to create notifications table and task assignment columns
    _run(run_pending_migrations(db_path))

    yield {"storage": test_storage}

    storage_module._storage_instance = original_instance


class TestDeleteProjectNotificationCleanup:
    """F-1 regression: project deletion must remove associated notifications."""

    def test_delete_project_removes_notifications(self, f1_ctx):
        """Deleting a project must remove all notifications scoped to that project."""
        storage = f1_ctx["storage"]
        proj_id = "f1_notification_cleanup_proj"
        user_id = "f1_user_1"

        # Create a project
        _run(storage.create_project({
            "project_id": proj_id,
            "name": "Notification Cleanup Test",
        }))

        # Create notifications scoped to this project
        _run(storage.save_notification(user_id, {
            "project_id": proj_id,
            "type": "TASK_ASSIGNED",
            "title": "Task Assigned",
            "message": "Task assigned to you.",
        }))
        _run(storage.save_notification(user_id, {
            "project_id": proj_id,
            "type": "VERIFICATION_COMPLETED",
            "title": "Verification Done",
            "message": "Verification completed.",
        }))

        # Also create a notification for a DIFFERENT project (should survive)
        other_proj_id = "f1_other_proj"
        _run(storage.create_project({
            "project_id": other_proj_id,
            "name": "Other Project",
        }))
        _run(storage.save_notification(user_id, {
            "project_id": other_proj_id,
            "type": "TASK_ASSIGNED",
            "title": "Other Task",
            "message": "Other task assigned.",
        }))

        # Verify notifications exist before deletion
        notifs_before = _run(storage.get_notifications(user_id, project_id=proj_id))
        assert len(notifs_before) == 2, f"Expected 2 notifications, got {len(notifs_before)}"

        other_notifs_before = _run(storage.get_notifications(user_id, project_id=other_proj_id))
        assert len(other_notifs_before) == 1, f"Expected 1 other notification, got {len(other_notifs_before)}"

        # Delete the project
        result = _run(storage.delete_project(proj_id))
        assert result is True

        # Verify project-specific notifications are gone
        notifs_after = _run(storage.get_notifications(user_id, project_id=proj_id))
        assert len(notifs_after) == 0, (
            f"Expected 0 notifications after project deletion, got {len(notifs_after)}. "
            "delete_project() is not cleaning up the notifications table."
        )

        # Verify other project's notifications are preserved
        other_notifs_after = _run(storage.get_notifications(user_id, project_id=other_proj_id))
        assert len(other_notifs_after) == 1, (
            f"Expected 1 notification for other project to survive, got {len(other_notifs_after)}"
        )

    def test_delete_project_removes_unscoped_notifications_for_project(self, f1_ctx):
        """Deleting a project removes notifications that reference it, even without user scoping."""
        storage = f1_ctx["storage"]
        proj_id = "f1_unscoped_notif_proj"
        user_a = "f1_user_a"
        user_b = "f1_user_b"

        _run(storage.create_project({
            "project_id": proj_id,
            "name": "Unscoped Notification Test",
        }))

        # Notifications for different users on the same project
        _run(storage.save_notification(user_a, {
            "project_id": proj_id,
            "type": "TASK_ASSIGNED",
            "title": "User A Task",
            "message": "Assigned to A.",
        }))
        _run(storage.save_notification(user_b, {
            "project_id": proj_id,
            "type": "TASK_ASSIGNED",
            "title": "User B Task",
            "message": "Assigned to B.",
        }))

        notifs_a = _run(storage.get_notifications(user_a, project_id=proj_id))
        notifs_b = _run(storage.get_notifications(user_b, project_id=proj_id))
        assert len(notifs_a) == 1
        assert len(notifs_b) == 1

        # Delete the project
        _run(storage.delete_project(proj_id))

        # Both users' project-scoped notifications should be gone
        notifs_a_after = _run(storage.get_notifications(user_a, project_id=proj_id))
        notifs_b_after = _run(storage.get_notifications(user_b, project_id=proj_id))
        assert len(notifs_a_after) == 0, (
            f"User A still has {len(notifs_a_after)} notification(s) after project deletion"
        )
        assert len(notifs_b_after) == 0, (
            f"User B still has {len(notifs_b_after)} notification(s) after project deletion"
        )

    def test_delete_project_idempotent_on_notifications(self, f1_ctx):
        """Deleting a project with no notifications should not fail."""
        storage = f1_ctx["storage"]
        proj_id = "f1_empty_notif_proj"

        _run(storage.create_project({
            "project_id": proj_id,
            "name": "Empty Notification Test",
        }))

        # Delete immediately — no notifications exist
        result = _run(storage.delete_project(proj_id))
        assert result is True

        # No error, no crash
        notifs = _run(storage.get_notifications("any_user", project_id=proj_id))
        assert len(notifs) == 0
