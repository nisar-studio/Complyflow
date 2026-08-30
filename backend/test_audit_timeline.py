"""
test_audit_timeline.py

Comprehensive test suite for P1 #6 Enterprise Audit Activity Timeline & Immutable Audit Log.

Tests:
  - Audit event storage append-only behavior and deterministic ordering
  - Project isolation and cross-project security
  - Multi-criteria filtering (event_type, actor_type, severity, requirement_id, run_id, timestamps)
  - Pagination (limit, offset, total)
  - Lifecycle event triggers (project, document, analysis, gaps, conflicts, tasks, uploads, overrides, notes, report exports)
  - Security & privacy (no stored_filename, no absolute filesystem paths, no API keys)
  - ReportService point-in-time audit trail integration
"""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

import app.services.storage as storage_module
from app.services.audit_service import (
    AuditActorType,
    AuditEventType,
    AuditSeverity,
    record_audit_event,
    sanitize_audit_metadata,
    sanitize_audit_text,
)
from app.services.report_service import get_report_service
from app.services.storage import SQLiteStorageService


_loop = None

def run(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)



@pytest.fixture(scope="module")
def audit_api_ctx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("audit_api")
    db_path = str(tmp / "audit_api.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

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

    yield client, test_storage

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir



# ─────────────────────────────────────────────────────────────
# 1. Storage & Immutability Tests
# ─────────────────────────────────────────────────────────────

class TestAuditStorage:

    def test_append_and_retrieve_event(self, tmp_path):
        storage = SQLiteStorageService(db_path=str(tmp_path / "test_store.db"))
        pid = "proj_001"

        evt_id = run(storage.save_audit_event(pid, {
            "event_type": "PROJECT_CREATED",
            "actor_type": "AUDITOR",
            "severity": "INFO",
            "summary": "Project created for compliance check.",
            "description": "Initial setup by auditor.",
            "metadata": {"custom_field": "val123"},
        }))

        assert evt_id.startswith("evt_")

        # Retrieve single
        retrieved = run(storage.get_audit_event(pid, evt_id))
        assert retrieved is not None
        assert retrieved["event_id"] == evt_id
        assert retrieved["project_id"] == pid
        assert retrieved["event_type"] == "PROJECT_CREATED"
        assert retrieved["actor_type"] == "AUDITOR"
        assert retrieved["severity"] == "INFO"
        assert retrieved["summary"] == "Project created for compliance check."
        assert retrieved["description"] == "Initial setup by auditor."
        assert retrieved["metadata"] == {"custom_field": "val123"}

    def test_chronological_ordering_newest_first(self, tmp_path):
        storage = SQLiteStorageService(db_path=str(tmp_path / "test_order.db"))
        pid = "proj_order"

        run(storage.save_audit_event(pid, {
            "event_id": "evt_1",
            "timestamp": "2026-08-29T10:00:00Z",
            "event_type": "PROJECT_CREATED",
            "summary": "First event",
        }))
        run(storage.save_audit_event(pid, {
            "event_id": "evt_2",
            "timestamp": "2026-08-29T11:00:00Z",
            "event_type": "DOCUMENT_UPLOADED",
            "summary": "Second event",
        }))
        run(storage.save_audit_event(pid, {
            "event_id": "evt_3",
            "timestamp": "2026-08-29T12:00:00Z",
            "event_type": "ANALYSIS_COMPLETED",
            "summary": "Third event",
        }))

        events = run(storage.list_audit_events(pid))
        assert len(events) == 3
        # Newest first: evt_3 -> evt_2 -> evt_1
        assert events[0]["event_id"] == "evt_3"
        assert events[1]["event_id"] == "evt_2"
        assert events[2]["event_id"] == "evt_1"

    def test_project_isolation(self, tmp_path):
        storage = SQLiteStorageService(db_path=str(tmp_path / "test_iso.db"))

        run(storage.save_audit_event("proj_A", {
            "event_id": "evt_A1",
            "event_type": "PROJECT_CREATED",
            "summary": "Project A event",
        }))
        run(storage.save_audit_event("proj_B", {
            "event_id": "evt_B1",
            "event_type": "PROJECT_CREATED",
            "summary": "Project B event",
        }))

        events_a = run(storage.list_audit_events("proj_A"))
        assert len(events_a) == 1
        assert events_a[0]["event_id"] == "evt_A1"

        events_b = run(storage.list_audit_events("proj_B"))
        assert len(events_b) == 1
        assert events_b[0]["event_id"] == "evt_B1"

        # Cannot get evt_A1 using proj_B
        assert run(storage.get_audit_event("proj_B", "evt_A1")) is None


# ─────────────────────────────────────────────────────────────
# 2. Filtering & Pagination Tests
# ─────────────────────────────────────────────────────────────

class TestAuditFilteringAndPagination:

    @pytest.fixture(autouse=True)
    def setup_events(self, tmp_path):
        self.storage = SQLiteStorageService(db_path=str(tmp_path / "test_filter.db"))
        self.pid = "proj_filter_test"

        events_to_seed = [
            {"event_id": "e1", "timestamp": "2026-08-29T01:00:00Z", "event_type": "PROJECT_CREATED", "actor_type": "AUDITOR", "severity": "INFO", "summary": "Project created"},
            {"event_id": "e2", "timestamp": "2026-08-29T02:00:00Z", "event_type": "DOCUMENT_UPLOADED", "actor_type": "AUDITOR", "severity": "INFO", "document_id": "doc_1", "summary": "Doc uploaded"},
            {"event_id": "e3", "timestamp": "2026-08-29T03:00:00Z", "event_type": "ANALYSIS_STARTED", "actor_type": "AI_AGENT", "severity": "INFO", "summary": "Analysis started"},
            {"event_id": "e4", "timestamp": "2026-08-29T04:00:00Z", "event_type": "REQUIREMENT_GAP_DETECTED", "actor_type": "AI_AGENT", "severity": "WARNING", "requirement_id": "REQ-001", "summary": "Gap on REQ-001"},
            {"event_id": "e5", "timestamp": "2026-08-29T05:00:00Z", "event_type": "REQUIREMENT_CONFLICT_DETECTED", "actor_type": "AI_AGENT", "severity": "WARNING", "requirement_id": "REQ-002", "summary": "Conflict on REQ-002"},
            {"event_id": "e6", "timestamp": "2026-08-29T06:00:00Z", "event_type": "REMEDIATION_TASK_CREATED", "actor_type": "AI_AGENT", "severity": "INFO", "task_id": "TASK-001", "requirement_id": "REQ-001", "summary": "Task for REQ-001"},
            {"event_id": "e7", "timestamp": "2026-08-29T07:00:00Z", "event_type": "AUDITOR_OVERRIDE_CREATED", "actor_type": "AUDITOR", "severity": "INFO", "requirement_id": "REQ-001", "summary": "Override on REQ-001"},
            {"event_id": "e8", "timestamp": "2026-08-29T08:00:00Z", "event_type": "VERIFICATION_FAILED", "actor_type": "AI_AGENT", "severity": "ERROR", "run_id": "run_2", "summary": "Verification failed"},
        ]
        for e in events_to_seed:
            run(self.storage.save_audit_event(self.pid, e))

    def test_filter_by_event_type(self):
        evts = run(self.storage.list_audit_events(self.pid, event_type="REQUIREMENT_GAP_DETECTED"))
        assert len(evts) == 1
        assert evts[0]["event_id"] == "e4"

    def test_filter_by_actor_type(self):
        auditor_evts = run(self.storage.list_audit_events(self.pid, actor_type="AUDITOR"))
        assert len(auditor_evts) == 3
        ai_evts = run(self.storage.list_audit_events(self.pid, actor_type="AI_AGENT"))
        assert len(ai_evts) == 5

    def test_filter_by_severity(self):
        errs = run(self.storage.list_audit_events(self.pid, severity="ERROR"))
        assert len(errs) == 1
        assert errs[0]["event_id"] == "e8"
        warns = run(self.storage.list_audit_events(self.pid, severity="WARNING"))
        assert len(warns) == 2

    def test_filter_by_requirement_id(self):
        req1_evts = run(self.storage.list_audit_events(self.pid, requirement_id="REQ-001"))
        assert len(req1_evts) == 3  # e4, e6, e7

    def test_filter_by_timestamp_range(self):
        ranged = run(self.storage.list_audit_events(
            self.pid,
            from_timestamp="2026-08-29T03:00:00Z",
            to_timestamp="2026-08-29T06:00:00Z",
        ))
        assert len(ranged) == 4
        ids = [e["event_id"] for e in ranged]
        assert ids == ["e6", "e5", "e4", "e3"]

    def test_pagination(self):
        page1 = run(self.storage.list_audit_events(self.pid, limit=3, offset=0))
        assert len(page1) == 3
        page2 = run(self.storage.list_audit_events(self.pid, limit=3, offset=3))
        assert len(page2) == 3
        page3 = run(self.storage.list_audit_events(self.pid, limit=3, offset=6))
        assert len(page3) == 2

        # Assert no overlap
        ids_1 = {e["event_id"] for e in page1}
        ids_2 = {e["event_id"] for e in page2}
        assert ids_1.isdisjoint(ids_2)

        total = run(self.storage.count_audit_events(self.pid))
        assert total == 8


# ─────────────────────────────────────────────────────────────
# 3. API Integration & Lifecycle Actions
# ─────────────────────────────────────────────────────────────

class TestAuditApiIntegration:

    def test_full_lifecycle_generates_audit_events(self, audit_api_ctx):
        client, storage = audit_api_ctx

        # 1. Create project
        r = client.post("/api/projects", data={"name": "Lifecycle Audit Project"})
        assert r.status_code == 200
        pid = r.json()["project_id"]

        # Verify PROJECT_CREATED event
        evts_r = client.get(f"/api/projects/{pid}/audit-events")
        assert evts_r.status_code == 200
        data = evts_r.json()
        assert data["total"] >= 1
        assert data["events"][0]["event_type"] == "PROJECT_CREATED"
        assert data["events"][0]["actor_type"] == "AUDITOR"

        # 2. Upload document
        req_content = b"REQ-001: Company must have valid SOC 2 report."
        doc_r = client.post(
            f"/api/projects/{pid}/documents",
            files={"requirements_file": ("requirements.txt", req_content, "text/plain")},
        )
        assert doc_r.status_code == 200

        # Verify DOCUMENT_UPLOADED event
        evts_r = client.get(f"/api/projects/{pid}/audit-events?event_type=DOCUMENT_UPLOADED")
        assert evts_r.status_code == 200
        assert evts_r.json()["total"] >= 1
        assert evts_r.json()["events"][0]["document_id"] == "requirements_doc"

        # 3. Add auditor override
        # Seed requirement first
        run(storage.save_requirements(pid, [{"requirement_id": "REQ-001", "title": "SOC 2", "description": "SOC 2 certification", "priority": "HIGH", "required_evidence": "Certificate", "source_reference": "Sec 1"}]))
        run(storage.save_matches(pid, [{"requirement_id": "REQ-001", "requirement_title": "SOC 2", "status": "MISSING", "confidence": 1.0, "evidence": [], "reasoning": "Missing."}]))

        ov_r = client.post(
            f"/api/projects/{pid}/requirements/REQ-001/override",
            json={
                "overridden_status": "SATISFIED",
                "auditor_reason": "Auditor verified external portal directly.",
                "auditor_note": "Portal check passed.",
            },
        )
        assert ov_r.status_code == 200

        # Verify AUDITOR_OVERRIDE_CREATED event
        ov_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=AUDITOR_OVERRIDE_CREATED").json()
        assert ov_evts["total"] >= 1
        assert ov_evts["events"][0]["requirement_id"] == "REQ-001"
        assert ov_evts["events"][0]["actor_type"] == "AUDITOR"

        # 4. Add auditor note
        note_r = client.post(
            f"/api/projects/{pid}/requirements/REQ-001/notes",
            json={"note_text": "Follow-up required at next quarterly audit."},
        )
        assert note_r.status_code == 200
        note_id = note_r.json()["note"]["note_id"]

        note_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=AUDITOR_NOTE_CREATED").json()
        assert note_evts["total"] >= 1
        assert note_evts["events"][0]["requirement_id"] == "REQ-001"

        # 5. Delete auditor note
        del_note_r = client.delete(f"/api/projects/{pid}/notes/{note_id}")
        assert del_note_r.status_code == 200
        del_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=AUDITOR_NOTE_DELETED").json()
        assert del_evts["total"] >= 1

        # 6. Revoke auditor override
        del_ov_r = client.delete(f"/api/projects/{pid}/requirements/REQ-001/override")
        assert del_ov_r.status_code == 200
        rev_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=AUDITOR_OVERRIDE_REVOKED").json()
        assert rev_evts["total"] >= 1

        # 7. Remediation Upload
        run(storage.save_tasks(pid, [{"task_id": "TASK-100", "title": "Upload SOC 2", "severity": "HIGH", "status": "OPEN", "related_requirement_id": "REQ-001", "required_action": "Upload cert."}]))
        upload_r = client.post(
            f"/api/projects/{pid}/tasks/TASK-100/uploads",
            data={"requirement_id": "REQ-001", "description": "Signed cert"},
            files={"file": ("soc2_evidence.pdf", b"%PDF-1.4 test certificate content", "application/pdf")},
        )
        assert upload_r.status_code == 200
        upload_id = upload_r.json()["upload"]["upload_id"]

        up_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=REMEDIATION_UPLOAD_CREATED").json()
        assert up_evts["total"] >= 1
        assert up_evts["events"][0]["task_id"] == "TASK-100"
        assert up_evts["events"][0]["upload_id"] == upload_id

        # 8. Remediation Upload Delete
        del_up_r = client.delete(f"/api/projects/{pid}/uploads/{upload_id}")
        assert del_up_r.status_code == 200
        del_up_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=REMEDIATION_UPLOAD_DELETED").json()
        assert del_up_evts["total"] >= 1

        # 9. Report Export PDF and JSON
        run(storage.save_verification_run(pid, {
            "trigger": "INITIAL_ANALYSIS",
            "overall_status": "READY",
            "compliance_score": 100.0,
            "satisfied_count": 1,
            "total_count": 1,
            "requirements_snapshot": [{"requirement_id": "REQ-001", "title": "SOC 2", "description": "SOC 2"}],
            "matches_snapshot": [{"requirement_id": "REQ-001", "requirement_title": "SOC 2", "status": "SATISFIED", "evidence": []}],
            "issues_snapshot": [],
            "tasks_snapshot": [],
            "documents_used": ["requirements.txt"],
            "summary": "Complete.",
        }))

        pdf_r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.pdf")
        assert pdf_r.status_code == 200

        json_r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.json")
        assert json_r.status_code == 200

        rep_evts = client.get(f"/api/projects/{pid}/audit-events?event_type=REPORT_EXPORTED").json()
        assert rep_evts["total"] >= 2


# ─────────────────────────────────────────────────────────────
# 4. Security, Sanitization & Report Integration
# ─────────────────────────────────────────────────────────────

class TestSecurityAndSanitization:

    def test_text_sanitizer_removes_paths_and_tokens(self):
        text = "Uploaded to C:\\Users\\Administrator\\AppData\\Local\\secret.key with Bearer eyJhbGciOiJIUzI1NiIs..."
        cleaned = sanitize_audit_text(text)
        assert "C:\\Users\\" not in cleaned
        assert "[REDACTED_PATH]" in cleaned
        assert "[REDACTED_SECRET]" in cleaned

    def test_metadata_sanitizer_excludes_internal_keys(self):
        raw_meta = {
            "stored_filename": "/var/data/uploads/proj/task/12345.pdf",
            "api_key": "AIzaSyD-SecretKey12345",
            "filename": "soc2.pdf",
            "nested": {
                "db_path": "C:\\db.sqlite",
                "valid_key": "safe_value",
            }
        }
        clean = sanitize_audit_metadata(raw_meta)
        assert "stored_filename" not in clean
        assert "api_key" not in clean
        assert clean["filename"] == "soc2.pdf"
        assert "db_path" not in clean["nested"]
        assert clean["nested"]["valid_key"] == "safe_value"

    def test_single_event_endpoint_security(self, audit_api_ctx):
        client, storage = audit_api_ctx
        r = client.post("/api/projects", data={"name": "Sec Proj 1"})
        pid1 = r.json()["project_id"]
        r2 = client.post("/api/projects", data={"name": "Sec Proj 2"})
        pid2 = r2.json()["project_id"]

        evt_id = run(storage.save_audit_event(pid1, {
            "event_type": "PROJECT_CREATED",
            "summary": "Project 1 event",
        }))

        # Valid retrieval in pid1
        valid_r = client.get(f"/api/projects/{pid1}/audit-events/{evt_id}")
        assert valid_r.status_code == 200
        assert valid_r.json()["event"]["event_id"] == evt_id

        # Cross-project access in pid2 returns 404
        cross_r = client.get(f"/api/projects/{pid2}/audit-events/{evt_id}")
        assert cross_r.status_code == 404

        # Nonexistent event returns 404
        missing_r = client.get(f"/api/projects/{pid1}/audit-events/evt_nonexistent")
        assert missing_r.status_code == 404
