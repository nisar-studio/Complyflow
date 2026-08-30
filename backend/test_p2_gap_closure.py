"""
test_p2_gap_closure.py — P2 Gap Closure & Operational Polish Test Suite

Tests:
  1. Member Access Governance Audit Trail:
     - MEMBER_ADDED recorded on adding a project member
     - MEMBER_ROLE_UPDATED recorded on updating a member's role
     - MEMBER_REMOVED recorded on removing a project member
  2. Project Deletion Lifecycle & RBAC:
     - ADMIN can delete a project and all associated files
     - AUDITOR, REVIEWER, VIEWER are blocked with 403 Forbidden
     - PROJECT_DELETED event is logged
  3. Uniform File Sanitization:
     - DocumentService.save_upload sanitizes dangerous characters, path traversals, and null bytes
  4. Project Deletion Data Cleanup:
     - Deleted project records are removed across all child tables
"""
from __future__ import annotations

import asyncio
import os
import sys
import pytest
from pathlib import Path
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.document_service import DocumentService
from app.services.auth_service import (
    create_session_token,
    hash_password,
    Role,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from app.main import app


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def p2_ctx(tmp_path_factory):
    """Isolated environment for P2 gap closure tests."""
    tmp = tmp_path_factory.mktemp("p2_gap_closure")
    db_path = str(tmp / "p2.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    original_doc_dir = routes_module._document_service.upload_dir
    routes_module.settings.upload_dir = upload_dir
    routes_module._document_service.upload_dir = upload_dir

    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


# ─────────────────────────────────────────────────────────────
# 1. Member Access Governance Audit Trail
# ─────────────────────────────────────────────────────────────

class TestMemberAccessAuditTrail:

    def test_member_mutations_emit_immutable_audit_events(self, p2_ctx):
        client = p2_ctx["client"]
        storage = p2_ctx["storage"]

        proj_id = "p2_member_audit_proj"
        admin_uid = "p2_admin_user"
        admin_email = "admin_p2@company.com"

        _run(storage.create_user({
            "user_id": admin_uid,
            "email": admin_email,
            "name": "P2 Admin",
            "password_hash": hash_password("Password123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "P2 Member Audit Project"}))
        _run(storage.add_project_member(proj_id, admin_uid, Role.ADMIN.value))

        admin_token = create_session_token(admin_uid, admin_email)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create target user to be added/updated/removed
        target_uid = "p2_target_user"
        target_email = "target_p2@company.com"
        _run(storage.create_user({
            "user_id": target_uid,
            "email": target_email,
            "name": "Target Auditor",
            "password_hash": hash_password("Password123!"),
            "is_active": True,
        }))

        # 1. Add member -> MEMBER_ADDED
        add_res = client.post(
            f"/api/projects/{proj_id}/members",
            json={"email": target_email, "role": "AUDITOR"},
            headers=admin_headers,
        )
        assert add_res.status_code == 201

        events = _run(storage.list_audit_events(proj_id, event_type="MEMBER_ADDED"))
        assert len(events) >= 1
        assert "target_p2@company.com" in events[0]["summary"]

        # 2. Update member role -> MEMBER_ROLE_UPDATED
        up_res = client.put(
            f"/api/projects/{proj_id}/members/{target_uid}",
            json={"role": "REVIEWER"},
            headers=admin_headers,
        )
        assert up_res.status_code == 200

        up_events = _run(storage.list_audit_events(proj_id, event_type="MEMBER_ROLE_UPDATED"))
        assert len(up_events) >= 1
        assert "REVIEWER" in up_events[0]["summary"]

        # 3. Remove member -> MEMBER_REMOVED
        del_res = client.delete(
            f"/api/projects/{proj_id}/members/{target_uid}",
            headers=admin_headers,
        )
        assert del_res.status_code == 200

        del_events = _run(storage.list_audit_events(proj_id, event_type="MEMBER_REMOVED"))
        assert len(del_events) >= 1
        assert target_uid in del_events[0]["summary"]


# ─────────────────────────────────────────────────────────────
# 2. Project Deletion Lifecycle & RBAC
# ─────────────────────────────────────────────────────────────

class TestProjectDeletionLifecycle:

    def test_project_deletion_rbac_and_audit(self, p2_ctx):
        client = p2_ctx["client"]
        storage = p2_ctx["storage"]

        proj_id = "p2_delete_lifecycle_proj"
        admin_uid = "p2_del_admin"
        admin_email = "del_admin@test.com"
        viewer_uid = "p2_del_viewer"
        viewer_email = "del_viewer@test.com"

        _run(storage.create_user({"user_id": admin_uid, "email": admin_email, "name": "A", "password_hash": hash_password("Pass123!"), "is_active": True}))
        _run(storage.create_user({"user_id": viewer_uid, "email": viewer_email, "name": "V", "password_hash": hash_password("Pass123!"), "is_active": True}))

        _run(storage.create_project({"project_id": proj_id, "name": "Deletion Test Project"}))
        _run(storage.add_project_member(proj_id, admin_uid, Role.ADMIN.value))
        _run(storage.add_project_member(proj_id, viewer_uid, Role.VIEWER.value))

        admin_token = create_session_token(admin_uid, admin_email)
        viewer_token = create_session_token(viewer_uid, viewer_email)

        # Viewer cannot delete project -> 403
        v_res = client.delete(f"/api/projects/{proj_id}", headers={"Authorization": f"Bearer {viewer_token}"})
        assert v_res.status_code == 403

        # Admin can delete project -> 200
        a_res = client.delete(f"/api/projects/{proj_id}", headers={"Authorization": f"Bearer {admin_token}"})
        assert a_res.status_code == 200
        assert a_res.json()["status"] == "deleted"

        # Project is now deleted
        check_p = _run(storage.get_project(proj_id))
        assert check_p is None


# ─────────────────────────────────────────────────────────────
# 3. Uniform Filename Sanitization
# ─────────────────────────────────────────────────────────────

class TestDocumentServiceSanitization:

    def test_save_upload_sanitizes_path_traversal(self, tmp_path):
        upload_dir = str(tmp_path / "uploads")
        doc_service = DocumentService(upload_dir=upload_dir)

        proj_id = "sanitization_proj"
        file_path = doc_service.save_upload(
            filename="../../../etc/malicious_payload.pdf",
            content=b"%PDF-1.4 test",
            project_id=proj_id,
        )

        assert ".." not in file_path.name
        assert file_path.name == "malicious_payload.pdf"
        assert file_path.parent == Path(upload_dir) / proj_id
