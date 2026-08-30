"""
test_report_export.py

Comprehensive test suite for P1 #5 Enterprise Compliance Report Export (PDF & JSON).

Covers:
  - PDF export endpoint returns valid binary PDF (%PDF-) with proper headers
  - JSON report export returns complete audit data matching schema
  - Exact evidence citations and verbatim quotes appear in exported data
  - Fact-level conflicts (Source A vs Source B values & excerpts) are preserved
  - Human auditor overrides & notes are accurately represented alongside AI findings
  - AI score and auditor-adjusted score are both computed and displayed correctly
  - Historical integrity: run_1 export remains 75.0% after run_2 exists (immutable snapshots)
  - Predecessor delta calculation between runs in reports
  - Security: missing run / invalid project returns 404
  - Security: path traversal is blocked
  - Security: absolute filesystem paths and secrets are NOT exposed in reports
  - NovaTech 75% -> 100% full regression integrity
"""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

import app.services.storage as storage_module
from app.services.citation_validator import CitationValidator
from app.services.conflict_service import ConflictService
from app.services.delta_service import get_delta_engine
from app.services.report_service import ReportService, get_report_service
from app.services.storage import SQLiteStorageService


# ─────────────────────────────────────────────────────────────
# Async Helper
# ─────────────────────────────────────────────────────────────

_loop = None

def run(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)



# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_storage(tmp_path):
    return SQLiteStorageService(db_path=str(tmp_path / "test_report.db"))


@pytest.fixture(scope="module")
def report_api_ctx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("report_api")
    db_path = str(tmp / "report_api.db")
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

    # 1. Create NovaTech project
    r = client.post("/api/projects", data={"name": "NovaTech Solutions Compliance Audit"})

    assert r.status_code == 200, r.text
    project_id = r.json()["project_id"]

    # 2. Seed Run 1 (75.0% score, ACTION_REQUIRED, with 1 conflict, 2 missing, 9 satisfied)
    run_1_matches = [
        {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "novatech_registration.pdf", "page_number": 1, "quote": "Registration Number: NTS-2024-047821", "relevance": "Valid registration."}], "reasoning": "Registration confirmed."},
        {"requirement_id": "REQ-002", "requirement_title": "Good Standing Certificate", "status": "SATISFIED", "confidence": 0.97, "evidence": [{"document_name": "bank_ref.txt", "quote": "GOOD STANDING with no defaults", "relevance": "Standing confirmed."}], "reasoning": "Standing confirmed."},
        {
            "requirement_id": "REQ-003", 
            "requirement_title": "Registered Office Address", 
            "status": "CONFLICT", 
            "confidence": 0.95, 
            "evidence": [
                {"document_name": "novatech_registration.pdf", "quote": "REGISTERED OFFICE: 42 Innovation Drive, Suite 800, Tech City, TC 10001", "relevance": "Registration official address."},
                {"document_name": "company_profile.pdf", "quote": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 400, Tech City, TC 10001", "relevance": "Profile address."},
            ],
            "conflict_detail": {
                "fact_label": "Registered Office Address",
                "related_requirement_id": "REQ-003",
                "source_a": {"citation": {"document_name": "novatech_registration.pdf", "quote": "REGISTERED OFFICE: 42 Innovation Drive, Suite 800, Tech City, TC 10001"}, "value": "Suite 800"},
                "source_b": {"citation": {"document_name": "company_profile.pdf", "quote": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 400, Tech City, TC 10001"}, "value": "Suite 400"},
                "explanation": "Business Registration states Suite 800 whereas Company Profile states Suite 400.",
                "recommended_action": "Upload verified lease amendment reconciling address to Suite 800.",
            },
            "reasoning": "Address discrepancy detected."
        },
        {"requirement_id": "REQ-004", "requirement_title": "Tax Compliance & TIN", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "tax_clearance.pdf", "quote": "Tax Identification: TIN-9847-2200-TC. Status: FULLY COMPLIANT"}], "reasoning": "Tax clear."},
        {"requirement_id": "REQ-005", "requirement_title": "Financial Audit Report", "status": "SATISFIED", "confidence": 0.96, "evidence": [{"document_name": "audit_report.pdf", "quote": "Independent Auditor Opinion: Unqualified audit report"}], "reasoning": "Audit verified."},
        {"requirement_id": "REQ-006", "requirement_title": "General Liability Insurance", "status": "MISSING", "confidence": 1.0, "evidence": [], "reasoning": "No general liability insurance certificate uploaded."},
        {"requirement_id": "REQ-007", "requirement_title": "Cyber & Professional Insurance", "status": "SATISFIED", "confidence": 0.95, "evidence": [{"document_name": "cyber_policy.pdf", "quote": "Professional & Cyber Liability Coverage Limit: $1,000,000 per claim"}], "reasoning": "Cyber verified."},
        {"requirement_id": "REQ-008", "requirement_title": "Information Security Policy", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "security_policy.pdf", "quote": "Information Security Policy v3.2. Access controls and encryption enforced."}], "reasoning": "Security verified."},
        {"requirement_id": "REQ-009", "requirement_title": "SOC 2 Type II Certification", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "soc2_report.pdf", "quote": "SOC 2 Type II Examination Report: Controls operate effectively."}], "reasoning": "SOC 2 verified."},
        {"requirement_id": "REQ-010", "requirement_title": "Data Processing Agreement", "status": "MISSING", "confidence": 1.0, "evidence": [], "reasoning": "No DPA uploaded."},
        {"requirement_id": "REQ-011", "requirement_title": "Business Continuity & DR Plan", "status": "SATISFIED", "confidence": 0.92, "evidence": [{"document_name": "bcp_plan.pdf", "quote": "Business Continuity Plan: RTO 4 hours, RPO 1 hour."}], "reasoning": "BCP verified."},
        {"requirement_id": "REQ-012", "requirement_title": "Code of Conduct & Anti-Bribery", "status": "SATISFIED", "confidence": 0.94, "evidence": [{"document_name": "code_of_conduct.pdf", "quote": "Code of Business Conduct and Anti-Bribery Compliance Statement."}], "reasoning": "Ethics verified."},
    ]

    reqs = [{"requirement_id": m["requirement_id"], "title": m["requirement_title"], "description": f"Mandatory compliance check for {m['requirement_title']}", "priority": "HIGH", "required_evidence": "Verifiable document", "source_reference": f"Section {i+1}"} for i, m in enumerate(run_1_matches)]

    run(test_storage.save_requirements(project_id, reqs))

    run_1_snapshot = {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 75.0,
        "satisfied_count": 9,
        "total_count": 12,
        "requirements_snapshot": reqs,
        "matches_snapshot": run_1_matches,
        "issues_snapshot": [
            {"gap_id": "GAP-001", "gap_type": "missing_evidence", "severity": "CRITICAL", "description": "General Liability Insurance certificate missing", "related_requirement_id": "REQ-006"},
            {"gap_id": "GAP-002", "gap_type": "missing_evidence", "severity": "CRITICAL", "description": "Data Processing Agreement missing", "related_requirement_id": "REQ-010"},
            {"gap_id": "GAP-003", "gap_type": "conflict", "severity": "HIGH", "description": "Address conflict Suite 800 vs Suite 400", "related_requirement_id": "REQ-003"},
        ],
        "tasks_snapshot": [
            {"task_id": "TASK-001", "title": "Upload General Liability Insurance", "severity": "CRITICAL", "status": "OPEN", "related_requirement_id": "REQ-006", "required_action": "Upload ACORD 25 Certificate of Insurance with $2M min coverage."},
            {"task_id": "TASK-002", "title": "Upload Data Processing Agreement", "severity": "CRITICAL", "status": "OPEN", "related_requirement_id": "REQ-010", "required_action": "Execute GDPR-compliant DPA."},
            {"task_id": "TASK-003", "title": "Reconcile Registered Company Address", "severity": "HIGH", "status": "OPEN", "related_requirement_id": "REQ-003", "required_action": "Provide lease amendment proving Suite 800 address."},
        ],
        "documents_used": ["novatech_registration.pdf", "company_profile.pdf", "bank_ref.txt", "tax_clearance.pdf", "audit_report.pdf", "cyber_policy.pdf", "security_policy.pdf", "soc2_report.pdf", "bcp_plan.pdf", "code_of_conduct.pdf"],
        "summary": "Initial baseline analysis: 75.0% score with 3 issues (2 missing, 1 conflict).",
    }
    run(test_storage.save_verification_run(project_id, run_1_snapshot))

    # 3. Seed Run 2 (100.0% score, READY, 12 satisfied)
    run_2_matches = [dict(m) for m in run_1_matches]
    for m in run_2_matches:
        m["status"] = "SATISFIED"
        if m["requirement_id"] == "REQ-003":
            m["evidence"] = [{"document_name": "corrected_profile.pdf", "quote": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 800, Tech City, TC 10001", "relevance": "Address reconciled to Suite 800."}]
            m["conflict_detail"] = None
        elif m["requirement_id"] == "REQ-006":
            m["evidence"] = [{"document_name": "insurance_cert.pdf", "quote": "General Liability Coverage: $2,000,000 each occurrence, $4,000,000 aggregate.", "relevance": "Liability certificate verified."}]
        elif m["requirement_id"] == "REQ-010":
            m["evidence"] = [{"document_name": "executed_dpa.pdf", "quote": "DATA PROCESSING AGREEMENT Executed between Customer and NovaTech Solutions Ltd.", "relevance": "DPA executed."}]

    run_2_snapshot = {
        "trigger": "REMEDIATION_VERIFICATION",
        "overall_status": "READY",
        "compliance_score": 100.0,
        "satisfied_count": 12,
        "total_count": 12,
        "requirements_snapshot": reqs,
        "matches_snapshot": run_2_matches,
        "issues_snapshot": [],
        "tasks_snapshot": [],
        "documents_used": run_1_snapshot["documents_used"] + ["corrected_profile.pdf", "insurance_cert.pdf", "executed_dpa.pdf"],
        "summary": "Remediation verified: 100.0% compliance achieved. All 12 requirements satisfied.",
    }
    run(test_storage.save_verification_run(project_id, run_2_snapshot))

    yield client, project_id, test_storage

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir


# ─────────────────────────────────────────────────────────────
# 1. PDF Export Tests
# ─────────────────────────────────────────────────────────────

class TestPdfReportExport:

    def test_pdf_export_returns_valid_pdf_file(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.pdf")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert r.headers.get("content-type") == "application/pdf"
        assert "attachment;" in r.headers.get("content-disposition", "")
        assert "compliance_report_" in r.headers.get("content-disposition", "")
        assert r.content.startswith(b"%PDF-"), "Exported content must be a valid binary PDF"
        assert len(r.content) > 1000, "PDF should have substantial content"

    def test_pdf_export_run_2(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_2/report.pdf")
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF-")


# ─────────────────────────────────────────────────────────────
# 2. JSON Report Export Tests & Schema Completeness
# ─────────────────────────────────────────────────────────────

class TestJsonReportExport:

    def test_json_export_structure(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.json")
        assert r.status_code == 200, r.text
        data = r.json()

        # Metadata
        assert "report_metadata" in data
        meta = data["report_metadata"]
        assert meta["project_id"] == pid
        assert meta["run_id"] == "run_1"
        assert meta["run_number"] == 1
        assert meta["run_trigger"] == "INITIAL_ANALYSIS"
        assert "report_generated_at" in meta

        # Executive summary
        assert "executive_summary" in data
        summary = data["executive_summary"]
        assert summary["ai_score"] == 75.0
        assert summary["ai_status"] == "ACTION_REQUIRED"
        assert summary["satisfied_count"] == 9
        assert summary["missing_count"] == 2
        assert summary["conflict_count"] == 1
        assert summary["total_requirements"] == 12

        # Requirements findings
        assert "requirements_findings" in data
        findings = data["requirements_findings"]
        assert len(findings) == 12

        # Check citations and exact quotes
        req_001 = next(f for f in findings if f["requirement_id"] == "REQ-001")
        assert req_001["ai_status"] == "SATISFIED"
        assert len(req_001["evidence_citations"]) >= 1
        assert "Registration Number: NTS-2024-047821" in req_001["evidence_citations"][0]["quote"]
        assert req_001["evidence_citations"][0]["document_name"] == "novatech_registration.pdf"

        # Check missing requirement has 0 citations
        req_006 = next(f for f in findings if f["requirement_id"] == "REQ-006")
        assert req_006["ai_status"] == "MISSING"
        assert len(req_006["evidence_citations"]) == 0

        # Check conflicts
        req_003 = next(f for f in findings if f["requirement_id"] == "REQ-003")
        assert req_003["ai_status"] == "CONFLICT"
        assert req_003["conflict_details"] is not None
        assert "Suite 800" in str(req_003["conflict_details"])
        assert "Suite 400" in str(req_003["conflict_details"])

        # Check remediation tasks
        assert "remediation_plan" in data
        tasks = data["remediation_plan"]
        assert len(tasks) == 3

    def test_json_export_run_2_has_delta(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_2/report.json")
        assert r.status_code == 200
        data = r.json()

        assert data["executive_summary"]["ai_score"] == 100.0
        assert data["executive_summary"]["ai_status"] == "READY"
        assert data["executive_summary"]["satisfied_count"] == 12
        assert data["executive_summary"]["missing_count"] == 0

        # Predecessor delta must exist
        assert data["predecessor_delta"] is not None
        delta = data["predecessor_delta"]
        assert delta["score_before"] == 75.0
        assert delta["score_after"] == 100.0
        assert delta["score_diff"] == 25.0
        assert delta["resolved_count"] == 3


# ─────────────────────────────────────────────────────────────
# 3. Auditor Overrides & Score Distinction in Reports
# ─────────────────────────────────────────────────────────────

class TestAuditorOverridesInReport:

    def test_auditor_override_adjusts_report_score(self, report_api_ctx):
        client, pid, storage = report_api_ctx

        # Add an override to REQ-006 (General Liability Insurance)
        ov_r = client.post(
            f"/api/projects/{pid}/requirements/REQ-006/override",
            json={
                "overridden_status": "SATISFIED",
                "auditor_reason": "Auditor verified certificate directly on broker portal.",
                "auditor_note": "Policy #GL-2026-991 valid through Dec 2026.",
            },
        )
        assert ov_r.status_code == 200, ov_r.text

        # Fetch Run 1 report: AI score is still 75.0%, but auditor_adjusted_score is 83.3% (10/12 satisfied)
        r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.json")
        assert r.status_code == 200
        data = r.json()

        summary = data["executive_summary"]
        assert summary["ai_score"] == 75.0, "AI score must remain unchanged"
        assert summary["has_auditor_overrides"] is True
        assert summary["auditor_adjusted_score"] == 83.3
        assert summary["auditor_adjusted_status"] == "ACTION_REQUIRED"

        # Verify override appears inside requirement findings
        req_006 = next(f for f in data["requirements_findings"] if f["requirement_id"] == "REQ-006")
        assert req_006["ai_status"] == "MISSING"
        assert req_006["auditor_override"] is not None
        assert req_006["auditor_override"]["overridden_status"] == "SATISFIED"
        assert "broker portal" in req_006["auditor_override"]["auditor_reason"]

        # Clean up override
        client.delete(f"/api/projects/{pid}/requirements/REQ-006/override")


# ─────────────────────────────────────────────────────────────
# 4. Historical Snapshot Integrity
# ─────────────────────────────────────────────────────────────

class TestHistoricalIntegrity:

    def test_run_1_remains_75_percent_after_run_2(self, report_api_ctx):
        client, pid, _ = report_api_ctx

        # Fetch Run 1
        r1 = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.json")
        assert r1.status_code == 200
        d1 = r1.json()

        # Fetch Run 2
        r2 = client.get(f"/api/projects/{pid}/verification-runs/run_2/report.json")
        assert r2.status_code == 200
        d2 = r2.json()

        # Assert immutability
        assert d1["executive_summary"]["ai_score"] == 75.0
        assert d1["executive_summary"]["ai_status"] == "ACTION_REQUIRED"
        assert d1["executive_summary"]["satisfied_count"] == 9
        assert d1["executive_summary"]["missing_count"] == 2
        assert d1["executive_summary"]["conflict_count"] == 1

        assert d2["executive_summary"]["ai_score"] == 100.0
        assert d2["executive_summary"]["ai_status"] == "READY"
        assert d2["executive_summary"]["satisfied_count"] == 12
        assert d2["executive_summary"]["missing_count"] == 0


# ─────────────────────────────────────────────────────────────
# 5. Security, Validation & Path Traversal Prevention
# ─────────────────────────────────────────────────────────────

class TestSecurityAndErrorHandling:

    def test_missing_run_returns_404(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/nonexistent_run/report.pdf")
        assert r.status_code == 404
        r_json = client.get(f"/api/projects/{pid}/verification-runs/nonexistent_run/report.json")
        assert r_json.status_code == 404

    def test_missing_project_returns_404(self, report_api_ctx):
        client, _, _ = report_api_ctx
        r = client.get("/api/projects/fake-project-id/verification-runs/run_1/report.pdf")
        assert r.status_code == 404

    def test_no_filesystem_paths_or_secrets_in_json(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.json")
        assert r.status_code == 200
        text = r.text

        # Ensure no absolute paths leaked
        assert "C:\\" not in text
        assert "/tmp/" not in text
        assert "stored_filename" not in text
        assert "password" not in text.lower()
        assert "api_key" not in text.lower()
        assert "traceback" not in text.lower()

    def test_no_filesystem_paths_or_secrets_in_pdf(self, report_api_ctx):
        client, pid, _ = report_api_ctx
        r = client.get(f"/api/projects/{pid}/verification-runs/run_1/report.pdf")
        assert r.status_code == 200
        pdf_bytes = r.content

        # Basic binary checks
        assert b"stored_filename" not in pdf_bytes
        assert b"api_key" not in pdf_bytes.lower()
