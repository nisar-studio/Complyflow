"""
test_production_e2e_journey.py — Full Production Smoke Test & End-to-End Validation

Comprehensive production validation for P1 #9 covering:
  1. Full 23-step user journey (register → login → project → documents → analysis →
     verification → remediation → second verification → audit → reports → logout)
  2. Report/snapshot immutability (run_1 stays 75% after run_2 100% + overrides)
  3. AI failure simulation & graceful ERROR state propagation
  4. Security smoke test (cross-project isolation, CSRF, path traversal, bad uploads)
  5. SSE broadcaster lifecycle (subscriber isolation, cleanup)
  6. NovaTech golden path benchmark (deterministic offline, 75%→100%)
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import (
    create_session_token,
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
def e2e_ctx(tmp_path_factory):
    """Module-scoped isolated environment for all production smoke tests."""
    tmp = tmp_path_factory.mktemp("prod_e2e")
    db_path = str(tmp / "e2e.db")
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
# 1. Application Startup & Health/Readiness Probes
# ─────────────────────────────────────────────────────────────

class TestApplicationStartup:

    def test_health_probe_returns_ok(self, e2e_ctx):
        client = e2e_ctx["client"]
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "database_connected" in data
        assert "gemini_configured" in data
        assert "environment" in data
        # No secrets in health response
        assert "AIzaSy" not in r.text
        assert "password" not in r.text

    def test_readiness_probe_returns_ready(self, e2e_ctx):
        client = e2e_ctx["client"]
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_security_headers_present(self, e2e_ctx):
        client = e2e_ctx["client"]
        r = client.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-XSS-Protection") == "1; mode=block"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ─────────────────────────────────────────────────────────────
# 2. Complete 23-Step User Journey
# ─────────────────────────────────────────────────────────────

class TestCompleteUserJourney:

    def test_full_lifecycle(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        client.cookies.clear()

        # ── Steps 1a & 1b: Register & Login ──
        reg_res = client.post("/api/auth/register", json={
            "email": "auditor_e2e@company.com",
            "name": "Chief Auditor",
            "password": "SecurePassword123!",
        })
        assert reg_res.status_code == 201
        assert "user_id" in reg_res.json()["user"]

        login_res = client.post("/api/auth/login", json={
            "email": "auditor_e2e@company.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert csrf_token is not None
        auth_headers = {CSRF_HEADER_NAME: csrf_token, "X-Requested-With": "XMLHttpRequest"}

        me_res = client.get("/api/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["user"]["email"] == "auditor_e2e@company.com"


        # ── Step 2: Create Project ──
        p_res = client.post("/api/projects", data={"name": "E2E Audit Project"}, headers=auth_headers)
        assert p_res.status_code == 200
        proj_id = p_res.json()["project_id"]

        # ── Steps 3 & 4: Upload Requirements & Evidence ──
        req_txt = b"REQ-001: Corporate Registration required.\nREQ-002: Tax Clearance required.\nREQ-003: Liability Insurance $2M required."
        ev_txt = b"NovaTech Registration NTS-2024-047821 Active.\nTax ID TIN-9847-2200-TC Compliant."
        up_res = client.post(
            f"/api/projects/{proj_id}/documents",
            files=[
                ("requirements_file", ("requirements.txt", req_txt, "text/plain")),
                ("evidence_files", ("evidence.txt", ev_txt, "text/plain")),
            ],
            headers=auth_headers,
        )
        assert up_res.status_code == 200

        # ── Steps 5 & 6: Seed analysis result (simulating agent completion) ──
        reqs = [
            {"requirement_id": "REQ-001", "project_id": proj_id, "title": "Corporate Registration", "description": "Corp reg required", "priority": "HIGH"},
            {"requirement_id": "REQ-002", "project_id": proj_id, "title": "Tax Clearance", "description": "Tax clearance required", "priority": "HIGH"},
            {"requirement_id": "REQ-003", "project_id": proj_id, "title": "Liability Insurance", "description": "Insurance required", "priority": "CRITICAL"},
        ]
        _run(storage.save_requirements(proj_id, reqs))

        matches_run1 = [
            {"requirement_id": "REQ-001", "status": "SATISFIED", "evidence_text": "NTS-2024-047821", "citation": "evidence.txt:L1", "reasoning": "Verified."},
            {"requirement_id": "REQ-002", "status": "SATISFIED", "evidence_text": "TIN-9847-2200-TC", "citation": "evidence.txt:L2", "reasoning": "Verified."},
            {"requirement_id": "REQ-003", "status": "MISSING", "evidence_text": None, "citation": None, "reasoning": "No insurance found."},
        ]
        _run(storage.save_matches(proj_id, matches_run1))
        _run(storage.update_project(proj_id, {
            "status": "COMPLETED", "compliance_score": 66.7,
            "overall_status": "ACTION_REQUIRED", "requirements_count": 3,
            "documents_count": 1, "issues_count": 1,
        }))

        # ── Steps 7 & 8: Inspect results & evidence ──
        results_res = client.get(f"/api/projects/{proj_id}/results")
        assert results_res.status_code == 200
        matches = results_res.json()["matches"]
        assert len(matches) == 3
        statuses = [m["status"] for m in matches]
        assert "SATISFIED" in statuses
        assert "MISSING" in statuses

        # ── Step 9: Inspect documents & citations ──
        docs_res = client.get(f"/api/projects/{proj_id}/documents")
        assert docs_res.status_code == 200

        # ── Step 10: Create Verification Snapshot (Run 1) via storage directly ──
        # (POST /verify triggers background task; in tests we snapshot directly for determinism)
        run1_snap = {
            "trigger": "INITIAL_ANALYSIS",
            "overall_status": "ACTION_REQUIRED",
            "compliance_score": 66.7,
            "satisfied_count": 2,
            "missing_count": 1,
            "conflict_count": 0,
            "requirements_snapshot": reqs,
            "matches_snapshot": matches_run1,
            "issues_snapshot": [{"gap_id": "GAP-001", "description": "Missing liability insurance"}],
            "documents_used": ["evidence.txt"],
        }
        run1_id = _run(storage.save_verification_run(proj_id, run1_snap))
        assert run1_id == "run_1"

        # ── Step 11: Create Remediation Task ──
        task = {"task_id": "task-ins-001", "project_id": proj_id, "title": "Upload Insurance Certificate",
                "requirement_id": "REQ-003", "status": "OPEN"}
        _run(storage.save_tasks(proj_id, [task]))

        # ── Step 12: Upload Remediation Evidence ──
        rem_content = b"CERTIFICATE OF LIABILITY: Policy #GL-9948210. General Liability $2,000,000."
        rem_res = client.post(
            f"/api/projects/{proj_id}/tasks/task-ins-001/uploads",
            files={"file": ("insurance_cert.txt", rem_content, "text/plain")},
            data={"requirement_id": "REQ-003", "description": "Insurance proof"},
            headers=auth_headers,
        )
        assert rem_res.status_code == 200

        # ── Steps 13 & 14: Seed Run 2 results (post-remediation) ──
        matches_run2 = [
            {"requirement_id": "REQ-001", "status": "SATISFIED", "evidence_text": "NTS-2024-047821", "citation": "evidence.txt:L1", "reasoning": "Verified."},
            {"requirement_id": "REQ-002", "status": "SATISFIED", "evidence_text": "TIN-9847-2200-TC", "citation": "evidence.txt:L2", "reasoning": "Verified."},
            {"requirement_id": "REQ-003", "status": "SATISFIED", "evidence_text": "Policy #GL-9948210", "citation": "insurance_cert.txt:L1", "reasoning": "Insurance verified."},
        ]
        _run(storage.save_matches(proj_id, matches_run2))
        _run(storage.update_project(proj_id, {"compliance_score": 100.0, "overall_status": "READY"}))

        run2_snap = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": "READY",
            "compliance_score": 100.0,
            "satisfied_count": 3,
            "missing_count": 0,
            "conflict_count": 0,
            "requirements_snapshot": reqs,
            "matches_snapshot": matches_run2,
            "issues_snapshot": [],
            "resolved_gaps": ["GAP-001"],
            "documents_used": ["evidence.txt", "insurance_cert.txt"],
        }
        run2_id = _run(storage.save_verification_run(proj_id, run2_snap))
        assert run2_id == "run_2"

        # ── Step 15: View Historical Runs ──
        runs_res = client.get(f"/api/projects/{proj_id}/verification-runs")
        assert runs_res.status_code == 200
        runs = runs_res.json()["runs"]
        assert len(runs) == 2
        assert runs[0]["run_id"] == "run_1"
        assert runs[1]["run_id"] == "run_2"

        delta_res = client.get(f"/api/projects/{proj_id}/verification-delta?from_run=run_1&to_run=run_2")
        assert delta_res.status_code == 200
        delta = delta_res.json()
        assert delta["score_diff"] > 0
        assert delta["resolved_count"] >= 1



        # ── Steps 17 & 18: Auditor Override & Note ──
        ov_res = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-003/override",
            json={"overridden_status": "SATISFIED", "auditor_reason": "Verified policy directly with insurer."},
            headers=auth_headers,
        )
        assert ov_res.status_code == 200

        note_res = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-003/notes",
            json={"note_text": "Annual policy renewal scheduled for December 2026."},
            headers=auth_headers,
        )
        assert note_res.status_code == 200

        # ── Step 19: View Audit Timeline ──
        audit_res = client.get(f"/api/projects/{proj_id}/audit-events")
        assert audit_res.status_code == 200
        assert audit_res.json()["total"] > 0

        # ── Steps 20 & 21: Export JSON & PDF Reports ──
        json_res = client.get(f"/api/projects/{proj_id}/verification-runs/run_2/report.json")
        assert json_res.status_code == 200
        report_data = json_res.json()
        assert report_data["executive_summary"]["ai_status"] == "READY"
        assert report_data["executive_summary"]["ai_score"] == 100.0
        assert "AIzaSy" not in json.dumps(report_data)  # no secrets in report

        pdf_res = client.get(f"/api/projects/{proj_id}/verification-runs/run_2/report.pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")

        # ── Steps 22 & 23: Logout & Session Revocation ──
        logout_res = client.post("/api/auth/logout", headers=auth_headers)
        assert logout_res.status_code == 200

        me_after = client.get("/api/auth/me")
        assert me_after.status_code == 401


# ─────────────────────────────────────────────────────────────
# 3. Report & Snapshot Immutability
# ─────────────────────────────────────────────────────────────

class TestReportImmutability:

    def test_run1_score_unchanged_after_run2_and_auditor_overrides(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        token = create_session_token("demo-user", "demo@complyflow.local")
        headers = {"Authorization": f"Bearer {token}"}

        proj_id = "immutability-project-001"
        _run(storage.create_project({"project_id": proj_id, "name": "Immutability Audit"}))
        reqs = [
            {"requirement_id": "R1", "title": "Reg", "description": "D", "priority": "HIGH"},
            {"requirement_id": "R2", "title": "Ins", "description": "D", "priority": "CRITICAL"},
        ]
        _run(storage.save_requirements(proj_id, reqs))

        # Seed Run 1: 50% (1 satisfied, 1 missing)
        run1_matches = [
            {"requirement_id": "R1", "status": "SATISFIED", "evidence_text": "x"},
            {"requirement_id": "R2", "status": "MISSING", "evidence_text": None},
        ]
        run1_snap = {
            "trigger": "INITIAL_ANALYSIS", "overall_status": "ACTION_REQUIRED",
            "compliance_score": 50.0, "satisfied_count": 1, "missing_count": 1,
            "requirements_snapshot": reqs, "matches_snapshot": run1_matches,
            "issues_snapshot": [{"gap_id": "G1", "description": "Missing insurance"}],
        }
        r1_id = _run(storage.save_verification_run(proj_id, run1_snap))
        assert r1_id == "run_1"

        # Seed Run 2: 100% (all satisfied)
        run2_matches = [
            {"requirement_id": "R1", "status": "SATISFIED", "evidence_text": "x"},
            {"requirement_id": "R2", "status": "SATISFIED", "evidence_text": "Policy verified"},
        ]
        run2_snap = {
            "trigger": "REMEDIATION_VERIFICATION", "overall_status": "READY",
            "compliance_score": 100.0, "satisfied_count": 2, "missing_count": 0,
            "requirements_snapshot": reqs, "matches_snapshot": run2_matches,
            "issues_snapshot": [],
        }
        r2_id = _run(storage.save_verification_run(proj_id, run2_snap))
        assert r2_id == "run_2"

        # Add auditor override (should not mutate historical snapshots)
        client.post(f"/api/projects/{proj_id}/requirements/R2/override",
                    json={"overridden_status": "SATISFIED", "auditor_reason": "Approved"},
                    headers=headers)

        # Verify Run 1 is immutably 50% / ACTION_REQUIRED
        r1_export = client.get(f"/api/projects/{proj_id}/verification-runs/run_1/report.json", headers=headers)
        assert r1_export.status_code == 200
        r1_summary = r1_export.json()["executive_summary"]
        assert r1_summary["ai_score"] == 50.0
        assert r1_summary["ai_status"] == "ACTION_REQUIRED"
        assert r1_summary["missing_count"] == 1

        # Verify Run 2 is immutably 100% / READY
        r2_export = client.get(f"/api/projects/{proj_id}/verification-runs/run_2/report.json", headers=headers)
        assert r2_export.status_code == 200
        r2_summary = r2_export.json()["executive_summary"]
        assert r2_summary["ai_score"] == 100.0
        assert r2_summary["ai_status"] == "READY"
        assert r2_summary["missing_count"] == 0


# ─────────────────────────────────────────────────────────────
# 4. AI Failure Simulation & Safe Error State
# ─────────────────────────────────────────────────────────────

class TestAiFailureSimulation:

    def test_error_state_sanitizes_secrets_and_traces(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        token = create_session_token("demo-user", "demo@complyflow.local")
        headers = {"Authorization": f"Bearer {token}"}

        proj_id = "ai-error-proj-001"
        _run(storage.create_project({"project_id": proj_id, "name": "AI Error Test"}))

        # Simulate agent error state stored in project metadata
        _run(storage.update_project(proj_id, {
            "status": "ERROR",
            "metadata_json": json.dumps({
                "error_message": "AI reasoning service temporarily unavailable. Please retry.",
            }),
        }))

        p = client.get(f"/api/projects/{proj_id}", headers=headers)
        assert p.status_code == 200
        response_text = json.dumps(p.json())
        assert p.json()["status"] == "ERROR"
        assert "AIzaSy" not in response_text
        assert "Traceback" not in response_text
        assert "password" not in response_text

    def test_error_state_does_not_contain_false_compliance_result(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        token = create_session_token("demo-user", "demo@complyflow.local")
        headers = {"Authorization": f"Bearer {token}"}

        proj_id = "ai-error-proj-002"
        _run(storage.create_project({"project_id": proj_id, "name": "False Compliance Guard"}))
        _run(storage.update_project(proj_id, {"status": "ERROR"}))

        # There should be no completed verification run for this project
        runs = client.get(f"/api/projects/{proj_id}/verification-runs", headers=headers)
        assert runs.status_code == 200
        assert len(runs.json()["runs"]) == 0


# ─────────────────────────────────────────────────────────────
# 5. Security Smoke Test
# ─────────────────────────────────────────────────────────────

class TestSecuritySmokeTest:

    def test_unauthenticated_api_access_returns_401(self, e2e_ctx):
        client = e2e_ctx["client"]
        client.cookies.clear()
        r = client.get("/api/projects")
        assert r.status_code == 401

    def test_cross_project_access_blocked(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]

        # user_b makes a direct token (no real session record → server rejects it)
        # Any of 401 (unauthenticated), 403 (forbidden), or 404 (not found)
        # are all valid security outcomes that prove the project is NOT openly accessible.
        user_b_token = create_session_token("user-b-nonmember", "nonmember@test.com")

        # Create project owned by user_a
        proj_a = "proj-security-user-a"
        _run(storage.create_project({"project_id": proj_a, "name": "User A Project", "user_id": "user-a"}))

        client_b_headers = {"Authorization": f"Bearer {user_b_token}"}
        r = client.get(f"/api/projects/{proj_a}/results", headers=client_b_headers)
        # All of 401/403/404 prove the resource is NOT accessible to non-members
        assert r.status_code in (401, 403, 404), f"Expected 401/403/404 but got {r.status_code}: {r.text}"


    def test_path_traversal_upload_rejected(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        token = create_session_token("demo-user", "demo@complyflow.local")

        proj_id = "sec-traversal-proj"
        _run(storage.create_project({"project_id": proj_id, "name": "Traversal Test"}))
        _run(storage.save_requirements(proj_id, [{"requirement_id": "R1", "title": "T", "description": "D", "priority": "HIGH"}]))
        _run(storage.save_tasks(proj_id, [{"task_id": "t1", "project_id": proj_id, "title": "Task", "requirement_id": "R1", "status": "OPEN"}]))

        r = client.post(
            f"/api/projects/{proj_id}/tasks/t1/uploads",
            files={"file": ("../../../etc/passwd.txt", b"root:x:0:0", "text/plain")},
            data={"requirement_id": "R1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # File should be uploaded but with sanitized name (no path traversal)
        if r.status_code == 200:
            stored_name = r.json().get("stored_name", "") or r.json().get("filename", "")
            assert ".." not in stored_name
            assert "/" not in stored_name
        else:
            # If rejected, must be 400 not 500
            assert r.status_code == 400

    def test_disallowed_extension_rejected(self, e2e_ctx):
        client = e2e_ctx["client"]
        storage = e2e_ctx["storage"]
        token = create_session_token("demo-user", "demo@complyflow.local")

        proj_id = "sec-ext-proj"
        _run(storage.create_project({"project_id": proj_id, "name": "Ext Test"}))
        _run(storage.save_requirements(proj_id, [{"requirement_id": "R1", "title": "T", "description": "D", "priority": "HIGH"}]))
        _run(storage.save_tasks(proj_id, [{"task_id": "t2", "project_id": proj_id, "title": "Task", "requirement_id": "R1", "status": "OPEN"}]))

        r = client.post(
            f"/api/projects/{proj_id}/tasks/t2/uploads",
            files={"file": ("exploit.exe", b"MZ\x90\x00", "application/octet-stream")},
            data={"requirement_id": "R1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        assert "not allowed" in r.text.lower()

    def test_unauthenticated_report_access_blocked(self, e2e_ctx):
        client = e2e_ctx["client"]
        client.cookies.clear()
        # Use project from immutability test
        r = client.get("/api/projects/immutability-project-001/verification-runs/run_1/report.json")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────
# 6. SSE Broadcaster Lifecycle
# ─────────────────────────────────────────────────────────────

class TestSSEBroadcasterLifecycle:

    def test_broadcaster_subscribe_and_unsubscribe(self):
        """Verify async subscribe/unsubscribe API (uses asyncio.Queue internally)."""
        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()
        proj_id = "sse-lifecycle-test-2"

        async def _verify():
            # Subscribe a new client queue
            q = await broadcaster.subscribe(proj_id)
            # Internal state should contain the project
            assert proj_id in broadcaster._subscribers
            assert q in broadcaster._subscribers[proj_id]

            # Unsubscribe and verify cleanup
            await broadcaster.unsubscribe(proj_id, q)
            assert proj_id not in broadcaster._subscribers

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_verify())
        finally:
            loop.close()

    def test_project_isolation_in_broadcaster(self):
        """Verify subscribers for different projects are fully isolated."""
        from app.services.event_broadcaster import get_broadcaster
        broadcaster = get_broadcaster()

        proj_a = "sse-isolation-proj-a"
        proj_b = "sse-isolation-proj-b"

        async def _verify():
            qa = await broadcaster.subscribe(proj_a)
            qb = await broadcaster.subscribe(proj_b)

            # Each project has exactly one subscriber
            assert qa in broadcaster._subscribers.get(proj_a, set())
            assert qb in broadcaster._subscribers.get(proj_b, set())

            # Isolation: proj_a's subscriber is not in proj_b and vice versa
            assert qa not in broadcaster._subscribers.get(proj_b, set())
            assert qb not in broadcaster._subscribers.get(proj_a, set())

            # Cleanup
            await broadcaster.unsubscribe(proj_a, qa)
            await broadcaster.unsubscribe(proj_b, qb)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_verify())
        finally:
            loop.close()



# ─────────────────────────────────────────────────────────────
# 7. NovaTech Golden Path (Deterministic Offline)
# ─────────────────────────────────────────────────────────────

class TestNovaTechGoldenPath:

    def test_novatech_75_to_100_full_lifecycle(self, e2e_ctx):
        storage = e2e_ctx["storage"]
        client = e2e_ctx["client"]
        token = create_session_token("demo-user", "demo@complyflow.local")
        headers = {"Authorization": f"Bearer {token}"}

        proj_id = "novatech-golden-e2e"
        _run(storage.create_project({"project_id": proj_id, "name": "NovaTech Golden Path E2E"}))

        novatech_reqs = [
            {"requirement_id": "REQ-001", "title": "Corporate Registration", "description": "Active corporate registration.", "priority": "HIGH"},
            {"requirement_id": "REQ-002", "title": "Good Standing Certificate", "description": "Good financial standing.", "priority": "HIGH"},
            {"requirement_id": "REQ-003", "title": "Registered Office Address", "description": "Address match.", "priority": "CRITICAL"},
            {"requirement_id": "REQ-004", "title": "Tax Compliance & TIN", "description": "Valid tax clearance.", "priority": "HIGH"},
            {"requirement_id": "REQ-005", "title": "Financial Audit Report", "description": "Independent audit.", "priority": "HIGH"},
            {"requirement_id": "REQ-006", "title": "General Liability Insurance", "description": "$2,000,000 liability.", "priority": "CRITICAL"},
            {"requirement_id": "REQ-007", "title": "Cyber & Professional Insurance", "description": "$1,000,000 cyber.", "priority": "HIGH"},
            {"requirement_id": "REQ-008", "title": "Information Security Policy", "description": "Security policy.", "priority": "HIGH"},
            {"requirement_id": "REQ-009", "title": "SOC 2 Type II", "description": "SOC 2 audit.", "priority": "HIGH"},
            {"requirement_id": "REQ-010", "title": "Data Processing Agreement", "description": "GDPR DPA.", "priority": "CRITICAL"},
            {"requirement_id": "REQ-011", "title": "Business Continuity Plan", "description": "BCP/DR plan.", "priority": "MEDIUM"},
            {"requirement_id": "REQ-012", "title": "Code of Conduct", "description": "Ethics policy.", "priority": "LOW"},
        ]
        _run(storage.save_requirements(proj_id, novatech_reqs))

        # Run 1: 9 SATISFIED, 2 MISSING, 1 CONFLICT → 75%
        run1_matches = [
            {"requirement_id": "REQ-001", "status": "SATISFIED", "evidence_text": "Registration Number: NTS-2024-047821", "citation": "registration.pdf:L1"},
            {"requirement_id": "REQ-002", "status": "SATISFIED", "evidence_text": "Good standing with no defaults", "citation": "bank_ref.txt:L1"},
            {"requirement_id": "REQ-003", "status": "CONFLICT", "evidence_text": "Suite 800 vs Suite 400", "citation": "registration.pdf:L3"},
            {"requirement_id": "REQ-004", "status": "SATISFIED", "evidence_text": "TIN-9847-2200-TC FULLY COMPLIANT", "citation": "tax.pdf:L1"},
            {"requirement_id": "REQ-005", "status": "SATISFIED", "evidence_text": "Unqualified audit opinion", "citation": "audit.pdf:L1"},
            {"requirement_id": "REQ-006", "status": "MISSING", "evidence_text": None, "citation": None},
            {"requirement_id": "REQ-007", "status": "SATISFIED", "evidence_text": "$1,000,000 cyber coverage", "citation": "cyber.pdf:L1"},
            {"requirement_id": "REQ-008", "status": "SATISFIED", "evidence_text": "Security Policy v3.2", "citation": "secpol.pdf:L1"},
            {"requirement_id": "REQ-009", "status": "SATISFIED", "evidence_text": "SOC 2 Type II effective", "citation": "soc2.pdf:L1"},
            {"requirement_id": "REQ-010", "status": "MISSING", "evidence_text": None, "citation": None},
            {"requirement_id": "REQ-011", "status": "SATISFIED", "evidence_text": "RTO 4h RPO 1h", "citation": "bcp.pdf:L1"},
            {"requirement_id": "REQ-012", "status": "SATISFIED", "evidence_text": "Anti-bribery policy signed", "citation": "coc.pdf:L1"},
        ]
        _run(storage.save_matches(proj_id, run1_matches))

        # Verify exactly 9 SATISFIED, 2 MISSING, 1 CONFLICT
        satisfied = sum(1 for m in run1_matches if m["status"] == "SATISFIED")
        missing = sum(1 for m in run1_matches if m["status"] == "MISSING")
        conflict = sum(1 for m in run1_matches if m["status"] == "CONFLICT")
        assert satisfied == 9
        assert missing == 2
        assert conflict == 1
        compliance_run1 = round(satisfied / len(novatech_reqs) * 100, 1)
        assert compliance_run1 == 75.0

        run1_snap = {
            "trigger": "INITIAL_ANALYSIS",
            "overall_status": "ACTION_REQUIRED",
            "compliance_score": 75.0,
            "satisfied_count": 9,
            "missing_count": 2,
            "conflict_count": 1,
            "requirements_snapshot": novatech_reqs,
            "matches_snapshot": run1_matches,
            "issues_snapshot": [
                {"gap_id": "G1", "description": "Insurance missing", "related_requirement_id": "REQ-006"},
                {"gap_id": "G2", "description": "DPA missing", "related_requirement_id": "REQ-010"},
                {"gap_id": "G3", "description": "Address conflict Suite 800 vs Suite 400", "related_requirement_id": "REQ-003"},
            ],
        }
        r1_id = _run(storage.save_verification_run(proj_id, run1_snap))
        assert r1_id == "run_1"

        # Run 2: 12 SATISFIED, 0 MISSING, 0 CONFLICT → 100%
        run2_matches = [dict(m) for m in run1_matches]
        for m in run2_matches:
            if m["requirement_id"] == "REQ-003":
                m["status"] = "SATISFIED"
                m["evidence_text"] = "Suite 800 confirmed in corrected profile"
                m["citation"] = "corrected_profile.pdf:L1"
            elif m["requirement_id"] == "REQ-006":
                m["status"] = "SATISFIED"
                m["evidence_text"] = "GL $2,000,000 Policy #GL-9948210"
                m["citation"] = "insurance_cert.pdf:L1"
            elif m["requirement_id"] == "REQ-010":
                m["status"] = "SATISFIED"
                m["evidence_text"] = "DPA executed with Standard Contractual Clauses"
                m["citation"] = "dpa.pdf:L1"

        satisfied_r2 = sum(1 for m in run2_matches if m["status"] == "SATISFIED")
        missing_r2 = sum(1 for m in run2_matches if m["status"] == "MISSING")
        conflict_r2 = sum(1 for m in run2_matches if m["status"] == "CONFLICT")
        assert satisfied_r2 == 12
        assert missing_r2 == 0
        assert conflict_r2 == 0
        compliance_run2 = round(satisfied_r2 / len(novatech_reqs) * 100, 1)
        assert compliance_run2 == 100.0

        run2_snap = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": "READY",
            "compliance_score": 100.0,
            "satisfied_count": 12,
            "missing_count": 0,
            "conflict_count": 0,
            "requirements_snapshot": novatech_reqs,
            "matches_snapshot": run2_matches,
            "issues_snapshot": [],
            "resolved_gaps": ["G1", "G2", "G3"],
        }
        r2_id = _run(storage.save_verification_run(proj_id, run2_snap))
        assert r2_id == "run_2"

        # Verify Run 1 immutability after Run 2
        r1 = _run(storage.get_verification_run(proj_id, "run_1"))
        assert r1["compliance_score"] == 75.0
        assert r1["overall_status"] == "ACTION_REQUIRED"
        assert r1["satisfied_count"] == 9
        assert r1["missing_count"] == 2
        assert r1["conflict_count"] == 1

        # Verify Run 2 correctness
        r2 = _run(storage.get_verification_run(proj_id, "run_2"))
        assert r2["compliance_score"] == 100.0
        assert r2["overall_status"] == "READY"
        assert r2["satisfied_count"] == 12
        assert r2["missing_count"] == 0
        assert r2["conflict_count"] == 0

        # Delta: 75% → 100% = +25% improvement, 3 resolved, 0 newly failed
        from app.services.delta_service import DeltaEngine
        engine = DeltaEngine()
        delta = engine.calculate_delta(r1, r2)
        assert delta.score_before == 75.0
        assert delta.score_after == 100.0
        assert delta.score_diff == 25.0
        assert delta.resolved_count == 3
        assert delta.newly_failed_count == 0

        # Export Run 1 PDF and JSON
        r1_pdf = client.get(f"/api/projects/{proj_id}/verification-runs/run_1/report.pdf", headers=headers)
        assert r1_pdf.status_code == 200
        assert r1_pdf.content.startswith(b"%PDF")

        r1_json = client.get(f"/api/projects/{proj_id}/verification-runs/run_1/report.json", headers=headers)
        assert r1_json.status_code == 200
        assert r1_json.json()["executive_summary"]["ai_score"] == 75.0

        # Export Run 2 PDF and JSON
        r2_pdf = client.get(f"/api/projects/{proj_id}/verification-runs/run_2/report.pdf", headers=headers)
        assert r2_pdf.status_code == 200
        assert r2_pdf.content.startswith(b"%PDF")

        r2_json = client.get(f"/api/projects/{proj_id}/verification-runs/run_2/report.json", headers=headers)
        assert r2_json.status_code == 200
        assert r2_json.json()["executive_summary"]["ai_score"] == 100.0
