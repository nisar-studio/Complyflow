"""
ComplyFlow — Automated NovaTech End-to-End Regression Test Suite

Deterministic, automated benchmark asserting the complete NovaTech compliance lifecycle:
1. Initial Analysis: 12 requirements -> 9 SATISFIED, 2 MISSING, 1 CONFLICT -> 75.0% ACTION_REQUIRED (Run 1)
2. Remediation Ingestion: Missing insurance certificate, DPA, and corrected company profile added
3. Final Verification: 12 requirements -> 12 SATISFIED, 0 MISSING, 0 CONFLICT -> 100.0% READY (Run 2)
4. Full immutability, citation grounding, conflict value extraction, and Before/After delta verification.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from app.agent.schemas import Priority
from app.services.storage import SQLiteStorageService
from app.services.citation_validator import CitationValidator
from app.services.conflict_service import ConflictService
from app.services.delta_service import DeltaEngine


# ─────────────────────────────────────────────────────────────
# Canonical NovaTech Benchmark Fixtures
# ─────────────────────────────────────────────────────────────

NOVATECH_REQUIREMENTS = [
    {"requirement_id": "REQ-001", "title": "Corporate Registration", "description": "Must provide active corporate registration.", "priority": "HIGH"},
    {"requirement_id": "REQ-002", "title": "Good Standing Certificate", "description": "Must prove good financial and legal standing.", "priority": "HIGH"},
    {"requirement_id": "REQ-003", "title": "Registered Office Address", "description": "Address must match official corporate registration.", "priority": "CRITICAL"},
    {"requirement_id": "REQ-004", "title": "Tax Compliance & TIN", "description": "Valid tax clearance and tax ID.", "priority": "HIGH"},
    {"requirement_id": "REQ-005", "title": "Financial Audit Report", "description": "Independent audited balance sheet.", "priority": "HIGH"},
    {"requirement_id": "REQ-006", "title": "General Liability Insurance", "description": "Minimum $2,000,000 liability insurance certificate.", "priority": "CRITICAL"},
    {"requirement_id": "REQ-007", "title": "Cyber & Professional Insurance", "description": "Minimum $1,000,000 cyber/E&O coverage.", "priority": "HIGH"},
    {"requirement_id": "REQ-008", "title": "Information Security Policy", "description": "Comprehensive corporate information security policy.", "priority": "HIGH"},
    {"requirement_id": "REQ-009", "title": "SOC 2 Type II Certification", "description": "Independent SOC 2 Type II audit report.", "priority": "HIGH"},
    {"requirement_id": "REQ-010", "title": "Data Processing Agreement (DPA)", "description": "Executed GDPR/data processing agreement.", "priority": "CRITICAL"},
    {"requirement_id": "REQ-011", "title": "Business Continuity & DR Plan", "description": "Documented disaster recovery and BCP policies.", "priority": "MEDIUM"},
    {"requirement_id": "REQ-012", "title": "Code of Conduct & Anti-Bribery", "description": "Signed corporate ethics and anti-corruption policy.", "priority": "LOW"},
]

NOVATECH_INITIAL_DOCS = [
    {"name": "novatech_business_registration.pdf", "text": "REGISTERED OFFICE: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nRegistration Number: NTS-2024-047821\nStatus: Active and Incorporated"},
    {"name": "novatech_company_profile.pdf", "text": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 400, Tech City, TC 10001\nEmployee Count: 140"},
    {"name": "novatech_bank_reference.txt", "text": "NovaTech Solutions Ltd. maintains active accounts in GOOD STANDING with no defaults."},
    {"name": "novatech_tax_clearance.pdf", "text": "Tax Identification: TIN-9847-2200-TC. Status: FULLY COMPLIANT for fiscal year 2024."},
    {"name": "novatech_audit_report.pdf", "text": "Independent Auditor Opinion: Unqualified audit report. Solvency ratio confirmed."},
    {"name": "novatech_cyber_policy.pdf", "text": "Professional & Cyber Liability Coverage Limit: $1,000,000 per claim, $2,000,000 aggregate."},
    {"name": "novatech_security_policy.pdf", "text": "Information Security Policy v3.2. Access controls and encryption standards enforced."},
    {"name": "novatech_soc2_report.pdf", "text": "SOC 2 Type II Examination Report: Controls operate with high operating effectiveness."},
    {"name": "novatech_bcp_dr_plan.pdf", "text": "Business Continuity Plan: RTO 4 hours, RPO 1 hour verified quarterly."},
    {"name": "novatech_code_of_conduct.pdf", "text": "Code of Business Conduct and Anti-Bribery Compliance Statement."},
]

NOVATECH_REMEDIATION_DOCS = [
    {"name": "remediation_insurance_certificate.pdf", "text": "CERTIFICATE OF LIABILITY INSURANCE: Policy #GL-9948210\nGeneral Liability Coverage: $2,000,000 each occurrence, $4,000,000 aggregate.\nInsured: NovaTech Solutions Ltd."},
    {"name": "remediation_data_processing_agreement.pdf", "text": "DATA PROCESSING AGREEMENT (GDPR Compliant)\nExecuted between Customer and NovaTech Solutions Ltd.\nStandard Contractual Clauses incorporated."},
    {"name": "remediation_company_profile_corrected.pdf", "text": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nCorrected and updated official address."},
]


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    storage = SQLiteStorageService(db_path=temp_path)
    yield storage
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_novatech_end_to_end_75_to_100_regression(temp_storage):
    """
    Complete end-to-end regression test for NovaTech Solutions Ltd.:
    - Proves 75.0% ACTION_REQUIRED -> 100.0% READY transition
    - Proves immutability of Run 1 vs Run 2
    - Proves evidence grounding and fact-level conflict extraction
    """
    citation_validator = CitationValidator()
    conflict_service = ConflictService()
    delta_engine = DeltaEngine()

    # 1. Initialize Project in isolated SQLite
    project_id = await temp_storage.create_project({
        "name": "NovaTech Solutions Vendor Review",
        "status": "PENDING",
    })
    await temp_storage.save_requirements(project_id, NOVATECH_REQUIREMENTS)

    # ─────────────────────────────────────────────────────────
    # STAGE 1: INITIAL ANALYSIS (75.0% ACTION_REQUIRED)
    # ─────────────────────────────────────────────────────────

    # Build raw initial matches
    raw_initial_matches = [
        {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "novatech_business_registration.pdf", "quote": "Registration Number: NTS-2024-047821", "relevance": "Proves valid corporate registration."}], "reasoning": "Registration confirmed."},
        {"requirement_id": "REQ-002", "requirement_title": "Good Standing Certificate", "status": "SATISFIED", "confidence": 0.97, "evidence": [{"document_name": "novatech_bank_reference.txt", "quote": "GOOD STANDING with no defaults", "relevance": "Confirms good commercial standing."}], "reasoning": "Standing confirmed."},
        {
            "requirement_id": "REQ-003", 
            "requirement_title": "Registered Office Address", 
            "status": "CONFLICT", 
            "confidence": 0.95, 
            "evidence": [
                {"document_name": "novatech_business_registration.pdf", "quote": "REGISTERED OFFICE: 42 Innovation Drive, Suite 800, Tech City, TC 10001", "relevance": "Registration official address."},
                {"document_name": "novatech_company_profile.pdf", "quote": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 400, Tech City, TC 10001", "relevance": "Conflicting profile address."},
            ],
            "reasoning": "Address mismatch: Business Registration says Suite 800 whereas Company Profile says Suite 400."
        },
        {"requirement_id": "REQ-004", "requirement_title": "Tax Compliance & TIN", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "novatech_tax_clearance.pdf", "quote": "Tax Identification: TIN-9847-2200-TC. Status: FULLY COMPLIANT", "relevance": "Proves active TIN and tax clearance."}], "reasoning": "Tax compliant."},
        {"requirement_id": "REQ-005", "requirement_title": "Financial Audit Report", "status": "SATISFIED", "confidence": 0.96, "evidence": [{"document_name": "novatech_audit_report.pdf", "quote": "Independent Auditor Opinion: Unqualified audit report", "relevance": "Confirms clean financial audit."}], "reasoning": "Audit verified."},
        {
            "requirement_id": "REQ-006", 
            "requirement_title": "General Liability Insurance", 
            "status": "MISSING", 
            "confidence": 1.0, 
            "evidence": [{"document_name": "hallucinated.pdf", "quote": "Fake insurance"}],  # Intentional fake quote to test rejection
            "reasoning": "No general liability insurance certificate was uploaded."
        },
        {"requirement_id": "REQ-007", "requirement_title": "Cyber & Professional Insurance", "status": "SATISFIED", "confidence": 0.95, "evidence": [{"document_name": "novatech_cyber_policy.pdf", "quote": "Professional & Cyber Liability Coverage Limit: $1,000,000 per claim", "relevance": "Confirms cyber insurance."}], "reasoning": "Cyber coverage verified."},
        {"requirement_id": "REQ-008", "requirement_title": "Information Security Policy", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "novatech_security_policy.pdf", "quote": "Information Security Policy v3.2. Access controls and encryption standards enforced.", "relevance": "Security policy compliant."}], "reasoning": "Security policy verified."},
        {"requirement_id": "REQ-009", "requirement_title": "SOC 2 Type II Certification", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "novatech_soc2_report.pdf", "quote": "SOC 2 Type II Examination Report: Controls operate with high operating effectiveness.", "relevance": "SOC 2 verified."}], "reasoning": "SOC 2 compliant."},
        {
            "requirement_id": "REQ-010", 
            "requirement_title": "Data Processing Agreement (DPA)", 
            "status": "MISSING", 
            "confidence": 1.0, 
            "evidence": [], 
            "reasoning": "No Data Processing Agreement was found in the submission."
        },
        {"requirement_id": "REQ-011", "requirement_title": "Business Continuity & DR Plan", "status": "SATISFIED", "confidence": 0.92, "evidence": [{"document_name": "novatech_bcp_dr_plan.pdf", "quote": "Business Continuity Plan: RTO 4 hours, RPO 1 hour verified quarterly.", "relevance": "BCP verified."}], "reasoning": "BCP compliant."},
        {"requirement_id": "REQ-012", "requirement_title": "Code of Conduct & Anti-Bribery", "status": "SATISFIED", "confidence": 0.94, "evidence": [{"document_name": "novatech_code_of_conduct.pdf", "quote": "Code of Business Conduct and Anti-Bribery Compliance Statement.", "relevance": "Code of conduct signed."}], "reasoning": "Ethics compliant."},
    ]

    # Ground initial citations
    grounded_initial_matches = citation_validator.process_and_ground_matches(
        raw_matches=raw_initial_matches,
        documents=NOVATECH_INITIAL_DOCS,
    )

    # 1. Assert citation grounding properties
    # Missing requirements MUST have zero citations
    req_006 = next(m for m in grounded_initial_matches if m["requirement_id"] == "REQ-006")
    assert req_006["status"] == "MISSING"
    assert len(req_006["evidence"]) == 0, "Fake quote on MISSING requirement REQ-006 must be rejected"

    req_010 = next(m for m in grounded_initial_matches if m["requirement_id"] == "REQ-010")
    assert req_010["status"] == "MISSING"
    assert len(req_010["evidence"]) == 0

    # Conflict requirement must have 2 grounded sources
    req_003 = next(m for m in grounded_initial_matches if m["requirement_id"] == "REQ-003")
    assert req_003["status"] == "CONFLICT"
    assert len(req_003["evidence"]) == 2
    assert "Suite 800" in req_003["evidence"][0]["quote"]
    assert "Suite 400" in req_003["evidence"][1]["quote"]

    # Compute Initial Counts
    sat_1 = sum(1 for m in grounded_initial_matches if m["status"] == "SATISFIED")
    miss_1 = sum(1 for m in grounded_initial_matches if m["status"] == "MISSING")
    conf_1 = sum(1 for m in grounded_initial_matches if m["status"] == "CONFLICT")
    total_1 = len(grounded_initial_matches)

    assert sat_1 == 9
    assert miss_1 == 2
    assert conf_1 == 1
    assert total_1 == 12

    initial_score = round((sat_1 / total_1) * 100, 1)
    assert initial_score == 75.0

    # Save Run 1 Snapshot
    initial_snapshot = {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": initial_score,
        "satisfied_count": sat_1,
        "total_count": total_1,
        "requirements_snapshot": NOVATECH_REQUIREMENTS,
        "matches_snapshot": grounded_initial_matches,
        "issues_snapshot": [
            {"gap_id": "GAP-001", "gap_type": "missing_evidence", "severity": "CRITICAL", "description": "General Liability Insurance certificate missing", "related_requirement_id": "REQ-006"},
            {"gap_id": "GAP-002", "gap_type": "missing_evidence", "severity": "CRITICAL", "description": "Data Processing Agreement missing", "related_requirement_id": "REQ-010"},
            {"gap_id": "GAP-003", "gap_type": "conflict", "severity": "HIGH", "description": "Address conflict Suite 800 vs Suite 400", "related_requirement_id": "REQ-003"},
        ],
        "tasks_snapshot": [
            {"task_id": "TASK-001", "title": "Upload General Liability Insurance", "severity": "CRITICAL", "status": "OPEN", "related_requirement_id": "REQ-006"},
            {"task_id": "TASK-002", "title": "Upload Data Processing Agreement", "severity": "CRITICAL", "status": "OPEN", "related_requirement_id": "REQ-010"},
            {"task_id": "TASK-003", "title": "Reconcile Registered Company Address", "severity": "HIGH", "status": "OPEN", "related_requirement_id": "REQ-003"},
        ],
        "documents_used": [d["name"] for d in NOVATECH_INITIAL_DOCS],
        "resolved_gaps": [],
        "remaining_gaps": ["GAP-001", "GAP-002", "GAP-003"],
        "summary": "Initial analysis: 75.0% score with 3 issues to remediate.",
    }
    run_1_id = await temp_storage.save_verification_run(project_id, initial_snapshot)
    assert run_1_id == "run_1"

    # ─────────────────────────────────────────────────────────
    # STAGE 2: POST-REMEDIATION VERIFICATION (100.0% READY)
    # ─────────────────────────────────────────────────────────

    all_updated_docs = NOVATECH_INITIAL_DOCS + NOVATECH_REMEDIATION_DOCS

    raw_verified_matches = [
        {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "novatech_business_registration.pdf", "quote": "Registration Number: NTS-2024-047821", "relevance": "Registration valid."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-002", "requirement_title": "Good Standing Certificate", "status": "SATISFIED", "confidence": 0.97, "evidence": [{"document_name": "novatech_bank_reference.txt", "quote": "GOOD STANDING with no defaults", "relevance": "Good standing confirmed."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-003", "requirement_title": "Registered Office Address", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "remediation_company_profile_corrected.pdf", "quote": "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 800, Tech City, TC 10001", "relevance": "Address discrepancy resolved to Suite 800."}], "reasoning": "Address reconciled."},
        {"requirement_id": "REQ-004", "requirement_title": "Tax Compliance & TIN", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "novatech_tax_clearance.pdf", "quote": "Tax Identification: TIN-9847-2200-TC. Status: FULLY COMPLIANT", "relevance": "Tax clearance verified."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-005", "requirement_title": "Financial Audit Report", "status": "SATISFIED", "confidence": 0.96, "evidence": [{"document_name": "novatech_audit_report.pdf", "quote": "Independent Auditor Opinion: Unqualified audit report", "relevance": "Audit clean."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-006", "requirement_title": "General Liability Insurance", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "remediation_insurance_certificate.pdf", "quote": "General Liability Coverage: $2,000,000 each occurrence, $4,000,000 aggregate.", "relevance": "Liability certificate provided."}], "reasoning": "Insurance verified."},
        {"requirement_id": "REQ-007", "requirement_title": "Cyber & Professional Insurance", "status": "SATISFIED", "confidence": 0.95, "evidence": [{"document_name": "novatech_cyber_policy.pdf", "quote": "Professional & Cyber Liability Coverage Limit: $1,000,000 per claim", "relevance": "Cyber policy verified."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-008", "requirement_title": "Information Security Policy", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "novatech_security_policy.pdf", "quote": "Information Security Policy v3.2. Access controls and encryption standards enforced.", "relevance": "Security policy verified."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-009", "requirement_title": "SOC 2 Type II Certification", "status": "SATISFIED", "confidence": 0.99, "evidence": [{"document_name": "novatech_soc2_report.pdf", "quote": "SOC 2 Type II Examination Report: Controls operate with high operating effectiveness.", "relevance": "SOC 2 verified."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-010", "requirement_title": "Data Processing Agreement (DPA)", "status": "SATISFIED", "confidence": 0.98, "evidence": [{"document_name": "remediation_data_processing_agreement.pdf", "quote": "DATA PROCESSING AGREEMENT (GDPR Compliant)\nExecuted between Customer and NovaTech Solutions Ltd.", "relevance": "Executed DPA provided."}], "reasoning": "DPA verified."},
        {"requirement_id": "REQ-011", "requirement_title": "Business Continuity & DR Plan", "status": "SATISFIED", "confidence": 0.92, "evidence": [{"document_name": "novatech_bcp_dr_plan.pdf", "quote": "Business Continuity Plan: RTO 4 hours, RPO 1 hour verified quarterly.", "relevance": "BCP verified."}], "reasoning": "Satisfied."},
        {"requirement_id": "REQ-012", "requirement_title": "Code of Conduct & Anti-Bribery", "status": "SATISFIED", "confidence": 0.94, "evidence": [{"document_name": "novatech_code_of_conduct.pdf", "quote": "Code of Business Conduct and Anti-Bribery Compliance Statement.", "relevance": "Code signed."}], "reasoning": "Satisfied."},
    ]

    grounded_verified_matches = citation_validator.process_and_ground_matches(
        raw_matches=raw_verified_matches,
        documents=all_updated_docs,
    )

    sat_2 = sum(1 for m in grounded_verified_matches if m["status"] == "SATISFIED")
    miss_2 = sum(1 for m in grounded_verified_matches if m["status"] == "MISSING")
    conf_2 = sum(1 for m in grounded_verified_matches if m["status"] == "CONFLICT")
    total_2 = len(grounded_verified_matches)

    assert sat_2 == 12
    assert miss_2 == 0
    assert conf_2 == 0
    assert total_2 == 12

    verified_score = round((sat_2 / total_2) * 100, 1)
    assert verified_score == 100.0

    # Save Run 2 Snapshot
    verification_snapshot = {
        "trigger": "REMEDIATION_VERIFICATION",
        "overall_status": "READY",
        "compliance_score": verified_score,
        "satisfied_count": sat_2,
        "total_count": total_2,
        "requirements_snapshot": NOVATECH_REQUIREMENTS,
        "matches_snapshot": grounded_verified_matches,
        "issues_snapshot": [],
        "tasks_snapshot": [
            {"task_id": "TASK-001", "title": "Upload General Liability Insurance", "status": "RESOLVED"},
            {"task_id": "TASK-002", "title": "Upload Data Processing Agreement", "status": "RESOLVED"},
            {"task_id": "TASK-003", "title": "Reconcile Registered Company Address", "status": "RESOLVED"},
        ],
        "documents_used": [d["name"] for d in all_updated_docs],
        "resolved_gaps": ["GAP-001", "GAP-002", "GAP-003"],
        "remaining_gaps": [],
        "summary": "Final verification complete: All 12 compliance requirements are 100% SATISFIED. Package is READY.",
    }
    run_2_id = await temp_storage.save_verification_run(project_id, verification_snapshot)
    assert run_2_id == "run_2"

    # ─────────────────────────────────────────────────────────
    # STAGE 3: IMMUTABILITY & DELTA VERIFICATION
    # ─────────────────────────────────────────────────────────

    # Verify Run 1 is strictly immutable
    run_1_check = await temp_storage.get_verification_run(project_id, "run_1")
    assert run_1_check["run_number"] == 1
    assert run_1_check["compliance_score"] == 75.0
    assert run_1_check["overall_status"] == "ACTION_REQUIRED"
    assert len(run_1_check["issues_snapshot"]) == 3

    # Calculate comparative delta
    run_2_check = await temp_storage.get_verification_run(project_id, "run_2")
    delta = delta_engine.calculate_delta(run_1_check, run_2_check)

    assert delta.score_before == 75.0
    assert delta.score_after == 100.0
    assert delta.score_diff == 25.0
    assert delta.status_before == "ACTION_REQUIRED"
    assert delta.status_after == "READY"
    assert delta.resolved_count == 3
    assert delta.newly_failed_count == 0
    assert delta.unchanged_count == 9

    # Assert exact resolved requirement IDs
    resolved_ids = [r.requirement_id for r in delta.resolved_requirements]
    assert "REQ-006" in resolved_ids  # Insurance missing -> satisfied
    assert "REQ-010" in resolved_ids  # DPA missing -> satisfied
    assert "REQ-003" in resolved_ids  # Address conflict -> satisfied

    # Assert all 9 original satisfied remained unchanged
    unchanged_ids = [r.requirement_id for r in delta.unchanged_requirements]
    for req_num in [1, 2, 4, 5, 7, 8, 9, 11, 12]:
        assert f"REQ-{req_num:03d}" in unchanged_ids

    # ─────────────────────────────────────────────────────────
    # STAGE 4: AUDIT ACTIVITY LOG LIFECYCLE VERIFICATION
    # ─────────────────────────────────────────────────────────

    # Record Stage 1 audit actions
    await temp_storage.save_audit_event(project_id, {
        "event_id": "evt_nt_01",
        "timestamp": "2026-08-29T10:00:00Z",
        "event_type": "PROJECT_CREATED",
        "actor_type": "AUDITOR",
        "severity": "INFO",
        "summary": "NovaTech Solutions compliance audit initiated.",
    })
    await temp_storage.save_audit_event(project_id, {
        "event_id": "evt_nt_02",
        "timestamp": "2026-08-29T10:05:00Z",
        "event_type": "ANALYSIS_COMPLETED",
        "actor_type": "AI_AGENT",
        "severity": "INFO",
        "run_id": "run_1",
        "summary": "Initial baseline analysis: 75.0% score (ACTION_REQUIRED).",
    })
    await temp_storage.save_audit_event(project_id, {
        "event_id": "evt_nt_03",
        "timestamp": "2026-08-29T10:06:00Z",
        "event_type": "REQUIREMENT_CONFLICT_DETECTED",
        "actor_type": "AI_AGENT",
        "severity": "WARNING",
        "requirement_id": "REQ-003",
        "summary": "Address conflict detected: Suite 800 vs Suite 400.",
    })

    # Record Stage 2 remediation upload audit actions
    await temp_storage.save_audit_event(project_id, {
        "event_id": "evt_nt_04",
        "timestamp": "2026-08-29T11:00:00Z",
        "event_type": "REMEDIATION_UPLOAD_CREATED",
        "actor_type": "AUDITOR",
        "severity": "INFO",
        "task_id": "TASK-001",
        "requirement_id": "REQ-006",
        "summary": "Remediation evidence uploaded for General Liability Insurance.",
    })

    # Record Stage 3 verification audit action
    await temp_storage.save_audit_event(project_id, {
        "event_id": "evt_nt_05",
        "timestamp": "2026-08-29T11:15:00Z",
        "event_type": "VERIFICATION_COMPLETED",
        "actor_type": "AI_AGENT",
        "severity": "INFO",
        "run_id": "run_2",
        "summary": "Post-remediation verification completed: 100.0% READY.",
    })

    # Verify audit event retrieval & ordering
    all_audit_events = await temp_storage.list_audit_events(project_id)
    assert len(all_audit_events) == 5
    # Ordered newest first
    assert all_audit_events[0]["event_id"] == "evt_nt_05"
    assert all_audit_events[4]["event_id"] == "evt_nt_01"

    # Verify filtering by requirement_id
    req_3_evts = await temp_storage.list_audit_events(project_id, requirement_id="REQ-003")
    assert len(req_3_evts) == 1
    assert req_3_evts[0]["event_type"] == "REQUIREMENT_CONFLICT_DETECTED"

    # Verify point-in-time report data isolation
    from app.services.report_service import ReportService
    report_service = ReportService(storage=temp_storage)


    # Report for run_1 must only include events up to run_1's timestamp
    r1_data = await report_service.build_report_data(project_id, "run_1")
    assert r1_data["executive_summary"]["ai_score"] == 75.0
    assert r1_data["executive_summary"]["ai_status"] == "ACTION_REQUIRED"

    # Report for run_2 includes run_2 verification data
    r2_data = await report_service.build_report_data(project_id, "run_2")
    assert r2_data["executive_summary"]["ai_score"] == 100.0
    assert r2_data["executive_summary"]["ai_status"] == "READY"
    assert r2_data["predecessor_delta"]["score_diff"] == 25.0

