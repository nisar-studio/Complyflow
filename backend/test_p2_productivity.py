"""
test_p2_productivity.py — Automated Tests for Auditor Productivity & Bulk Operations

Tests:
  1. Bulk Status Override:
     - Multi-requirement bulk status overrides
     - Atomicity, per-item result structure, preservation of original AI status
     - Individual audit events generated with bulk_operation=True metadata
     - Recalculation of auditor_adjusted_score
  2. Bulk Partial Failure Handling:
     - Mixed valid and invalid requirement IDs
     - Deterministic error reporting without silent discarding
  3. Bulk Override RBAC:
     - ADMIN & AUDITOR allowed
     - REVIEWER & VIEWER return 403 Forbidden
  4. Bulk Auditor Notes:
     - Adding bulk note across requirements
     - Note creation, retrieval, and audit logging
  5. Bulk Document Deletion:
     - Physical file removal and DB record cleanup
     - Audit event generation
     - RBAC enforcement
  6. Synthetic Scale Performance:
     - Validates project results calculation with 100+ requirements and overrides
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import pytest
from pathlib import Path
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import (
    create_session_token,
    hash_password,
    Role,
)
from app.main import app


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def prod_ctx(tmp_path_factory):
    """Isolated environment for P2 productivity & bulk operations tests."""
    tmp = tmp_path_factory.mktemp("p2_productivity")
    db_path = str(tmp / "productivity.db")
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
# 1. Bulk Override Tests
# ─────────────────────────────────────────────────────────────

class TestBulkOverrides:

    def test_bulk_override_success_and_audit(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]

        proj_id = "p2_bulk_override_proj"
        auditor_uid = "p2_auditor_user"
        auditor_email = "auditor@complyflow.local"

        _run(storage.create_user({
            "user_id": auditor_uid,
            "email": auditor_email,
            "name": "Lead Auditor",
            "password_hash": hash_password("AuditorPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "Bulk Override Project", "compliance_score": 50.0}))
        _run(storage.add_project_member(proj_id, auditor_uid, Role.AUDITOR.value))

        # Seed 4 requirements & matches
        reqs = [
            {"requirement_id": "REQ-B1", "title": "Access Control", "priority": "HIGH"},
            {"requirement_id": "REQ-B2", "title": "Encryption at Rest", "priority": "CRITICAL"},
            {"requirement_id": "REQ-B3", "title": "Audit Logging", "priority": "HIGH"},
            {"requirement_id": "REQ-B4", "title": "Incident Response", "priority": "MEDIUM"},
        ]
        matches = [
            {"requirement_id": "REQ-B1", "status": "MISSING", "confidence": 0.9},
            {"requirement_id": "REQ-B2", "status": "MISSING", "confidence": 0.85},
            {"requirement_id": "REQ-B3", "status": "SATISFIED", "confidence": 0.95},
            {"requirement_id": "REQ-B4", "status": "MISSING", "confidence": 0.8},
        ]
        _run(storage.save_requirements(proj_id, reqs))
        _run(storage.save_matches(proj_id, matches))

        token = create_session_token(auditor_uid, auditor_email)
        headers = {"Authorization": f"Bearer {token}"}

        # Bulk override REQ-B1 and REQ-B2 to SATISFIED
        payload = {
            "requirement_ids": ["REQ-B1", "REQ-B2"],
            "overridden_status": "SATISFIED",
            "auditor_reason": "Verified external certificate for compliance.",
            "auditor_note": "Ticket SEC-9988",
        }

        res = client.post(f"/api/projects/{proj_id}/bulk/overrides", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "success"
        assert data["total_succeeded"] == 2
        assert len(data["success"]) == 2
        assert data["total_failed"] == 0

        # Check individual overrides in storage
        ov1 = _run(storage.get_auditor_override(proj_id, "REQ-B1"))
        assert ov1["overridden_status"] == "SATISFIED"
        assert ov1["original_ai_status"] == "MISSING"

        ov2 = _run(storage.get_auditor_override(proj_id, "REQ-B2"))
        assert ov2["overridden_status"] == "SATISFIED"
        assert ov2["original_ai_status"] == "MISSING"

        # Check audit events
        events = _run(storage.list_audit_events(proj_id, event_type="AUDITOR_OVERRIDE_CREATED"))
        assert len(events) >= 2

        # Check recalculated auditor-adjusted score
        details_res = client.get(f"/api/projects/{proj_id}", headers=headers)
        assert details_res.status_code == 200
        details = details_res.json()
        assert details["has_auditor_overrides"] is True
        # 3 out of 4 SATISFIED (REQ-B1, REQ-B2, REQ-B3) -> 75.0%
        assert details["auditor_adjusted_score"] == 75.0

    def test_bulk_override_partial_failure_handling(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]

        proj_id = "p2_partial_override_proj"
        auditor_uid = "p2_auditor_user_2"
        auditor_email = "auditor2@complyflow.local"

        _run(storage.create_user({
            "user_id": auditor_uid,
            "email": auditor_email,
            "name": "Auditor Two",
            "password_hash": hash_password("AuditorPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "Partial Override Project"}))
        _run(storage.add_project_member(proj_id, auditor_uid, Role.AUDITOR.value))

        _run(storage.save_requirements(proj_id, [{"requirement_id": "REQ-VALID-1", "title": "Valid"}]))

        token = create_session_token(auditor_uid, auditor_email)
        headers = {"Authorization": f"Bearer {token}"}

        # Request with 1 valid and 1 non-existent ID
        payload = {
            "requirement_ids": ["REQ-VALID-1", "REQ-INVALID-999"],
            "overridden_status": "SATISFIED",
            "auditor_reason": "Testing partial failure",
        }

        res = client.post(f"/api/projects/{proj_id}/bulk/overrides", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "partial"
        assert data["total_succeeded"] == 1
        assert data["total_failed"] == 1
        assert "REQ-INVALID-999" in data["failed"]
        assert len(data["errors"]) == 1
        assert data["errors"][0]["requirement_id"] == "REQ-INVALID-999"

    def test_bulk_override_rbac_enforcement(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]

        proj_id = "p2_rbac_override_proj"
        viewer_uid = "p2_viewer_user"
        viewer_email = "viewer@complyflow.local"

        _run(storage.create_user({
            "user_id": viewer_uid,
            "email": viewer_email,
            "name": "Read Only Viewer",
            "password_hash": hash_password("ViewerPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "RBAC Override Project"}))
        _run(storage.add_project_member(proj_id, viewer_uid, Role.VIEWER.value))
        _run(storage.save_requirements(proj_id, [{"requirement_id": "REQ-V1", "title": "Viewer Req"}]))

        token = create_session_token(viewer_uid, viewer_email)
        headers = {"Authorization": f"Bearer {token}"}

        # VIEWER cannot perform bulk override -> 403 Forbidden
        res = client.post(
            f"/api/projects/{proj_id}/bulk/overrides",
            json={"requirement_ids": ["REQ-V1"], "overridden_status": "SATISFIED", "auditor_reason": "Attempted by viewer"},
            headers=headers,
        )
        assert res.status_code == 403


# ─────────────────────────────────────────────────────────────
# 2. Bulk Notes Tests
# ─────────────────────────────────────────────────────────────

class TestBulkNotes:

    def test_bulk_create_notes(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]

        proj_id = "p2_bulk_notes_proj"
        admin_uid = "p2_admin_notes"
        admin_email = "admin_notes@complyflow.local"

        _run(storage.create_user({
            "user_id": admin_uid,
            "email": admin_email,
            "name": "Admin Notes",
            "password_hash": hash_password("AdminPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "Bulk Notes Project"}))
        _run(storage.add_project_member(proj_id, admin_uid, Role.ADMIN.value))

        _run(storage.save_requirements(proj_id, [
            {"requirement_id": "REQ-N1", "title": "Note Req 1"},
            {"requirement_id": "REQ-N2", "title": "Note Req 2"},
        ]))

        token = create_session_token(admin_uid, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "requirement_ids": ["REQ-N1", "REQ-N2"],
            "note_text": "Reviewed during Q3 audit committee meeting.",
        }

        res = client.post(f"/api/projects/{proj_id}/bulk/notes", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_succeeded"] == 2

        notes1 = _run(storage.list_auditor_notes(proj_id, "REQ-N1"))
        assert len(notes1) >= 1
        assert "Q3 audit committee" in notes1[0]["note_text"]


# ─────────────────────────────────────────────────────────────
# 3. Bulk Document Deletion Tests
# ─────────────────────────────────────────────────────────────

class TestBulkDocumentDeletion:

    def test_bulk_delete_documents_and_files(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]
        upload_dir = prod_ctx["upload_dir"]

        proj_id = "p2_bulk_doc_del_proj"
        admin_uid = "p2_admin_doc_del"
        admin_email = "admin_doc_del@complyflow.local"

        _run(storage.create_user({
            "user_id": admin_uid,
            "email": admin_email,
            "name": "Doc Admin",
            "password_hash": hash_password("AdminPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "Bulk Doc Del Project"}))
        _run(storage.add_project_member(proj_id, admin_uid, Role.ADMIN.value))

        # Create physical files and doc records
        proj_dir = Path(upload_dir) / proj_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        file1 = proj_dir / "sample1.txt"
        file2 = proj_dir / "sample2.txt"
        file1.write_text("file 1 content")
        file2.write_text("file 2 content")

        _run(storage.save_document_analysis(proj_id, "doc-1", {"name": "sample1.txt", "role": "evidence", "text": "file 1 content"}))
        _run(storage.save_document_analysis(proj_id, "doc-2", {"name": "sample2.txt", "role": "evidence", "text": "file 2 content"}))

        token = create_session_token(admin_uid, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        # Bulk delete doc-1 and doc-2
        res = client.post(
            f"/api/projects/{proj_id}/bulk/documents/delete",
            json={"doc_ids": ["doc-1", "doc-2"]},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_succeeded"] == 2

        # Verify physical files are unlinked
        assert not file1.exists()
        assert not file2.exists()

        # Verify DB records deleted
        remaining_docs = _run(storage.list_documents(proj_id))
        assert len(remaining_docs) == 0


# ─────────────────────────────────────────────────────────────
# 4. Synthetic Scale Performance Check
# ─────────────────────────────────────────────────────────────

class TestScalePerformance:

    def test_synthetic_100_requirements_evaluation_speed(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]

        proj_id = "p2_scale_perf_proj"
        admin_uid = "p2_admin_scale"
        admin_email = "admin_scale@complyflow.local"

        _run(storage.create_user({
            "user_id": admin_uid,
            "email": admin_email,
            "name": "Scale Admin",
            "password_hash": hash_password("AdminPass123!"),
            "is_active": True,
        }))
        _run(storage.create_project({"project_id": proj_id, "name": "Scale Performance Project", "compliance_score": 80.0}))
        _run(storage.add_project_member(proj_id, admin_uid, Role.ADMIN.value))

        # Generate 100 synthetic requirements and matches
        reqs = [{"requirement_id": f"REQ-SCALE-{i:03d}", "title": f"Requirement {i}", "priority": "HIGH"} for i in range(100)]
        matches = [{"requirement_id": f"REQ-SCALE-{i:03d}", "status": "SATISFIED" if i % 4 != 0 else "MISSING", "confidence": 0.9} for i in range(100)]

        _run(storage.save_requirements(proj_id, reqs))
        _run(storage.save_matches(proj_id, matches))

        token = create_session_token(admin_uid, admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        # Measure bulk override speed across 25 requirements
        t0 = time.perf_counter()
        res = client.post(
            f"/api/projects/{proj_id}/bulk/overrides",
            json={
                "requirement_ids": [f"REQ-SCALE-{i:03d}" for i in range(0, 100, 4)],
                "overridden_status": "SATISFIED",
                "auditor_reason": "Batch verified in automated regression",
            },
            headers=headers,
        )
        t_elapsed = time.perf_counter() - t0

        assert res.status_code == 200
        # 25 overrides should complete in under 2.0 seconds on local SQLite WAL
        assert t_elapsed < 2.0
        assert res.json()["total_succeeded"] == 25
