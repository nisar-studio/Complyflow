"""
ComplyFlow — Fact-Level Conflict Detection Test Suite

Tests fact-level conflict extraction, semantic normalization (avoiding false positives),
competing value grounding against source text, and NovaTech address conflict regression.
"""
from __future__ import annotations

import pytest
from app.agent.schemas import EvidenceCitation, Priority
from app.services.conflict_service import ConflictService, get_conflict_service


@pytest.fixture
def conflict_svc():
    return ConflictService()


def test_two_different_addresses_produces_conflict(conflict_svc):
    cit_a = EvidenceCitation(
        document_name="business_registration.pdf",
        page_number=1,
        section="Registered Office",
        quote="Registered Office: 42 Innovation Drive, Suite 800, Tech City, TC 10001",
        verified=True,
    )
    cit_b = EvidenceCitation(
        document_name="company_profile.pdf",
        page_number=2,
        section="Location",
        quote="Corporate Headquarters: 42 Innovation Drive, Suite 400, Tech City, TC 10001",
        verified=True,
    )

    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-003",
        fact="company_address",
        fact_label="Registered Company Address",
        citation_a=cit_a,
        value_a="Suite 800",
        citation_b=cit_b,
        value_b="Suite 400",
        explanation="Business registration lists Suite 800 while Company Profile lists Suite 400.",
        severity=Priority.HIGH,
    )

    assert conflict is not None
    assert conflict.fact == "company_address"
    assert conflict.source_a.value == "Suite 800"
    assert conflict.source_b.value == "Suite 400"
    assert conflict.source_a.citation.document_name == "business_registration.pdf"
    assert conflict.source_b.citation.document_name == "company_profile.pdf"
    assert conflict.severity == Priority.HIGH
    assert conflict.recommended_action is not None


def test_two_different_insurance_amounts_produces_conflict(conflict_svc):
    cit_a = EvidenceCitation(
        document_name="policy_summary.pdf",
        quote="Coverage Limit: $1,000,000 each claim",
        verified=True,
    )
    cit_b = EvidenceCitation(
        document_name="certificate_of_insurance.pdf",
        quote="General Liability: $2,000,000 aggregate",
        verified=True,
    )

    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-007",
        fact="insurance_limit",
        fact_label="Liability Coverage Amount",
        citation_a=cit_a,
        value_a="$1,000,000",
        citation_b=cit_b,
        value_b="$2,000,000",
        explanation="Policy summary states $1M but certificate states $2M.",
        severity=Priority.CRITICAL,
    )

    assert conflict is not None
    assert conflict.source_a.value == "$1,000,000"
    assert conflict.source_b.value == "$2,000,000"


def test_identical_values_no_conflict(conflict_svc):
    cit_a = EvidenceCitation(document_name="doc1.pdf", quote="Suite 800", verified=True)
    cit_b = EvidenceCitation(document_name="doc2.pdf", quote="Suite 800", verified=True)

    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-001",
        fact="address",
        fact_label="Address",
        citation_a=cit_a,
        value_a="Suite 800",
        citation_b=cit_b,
        value_b="Suite 800",
        explanation="No conflict.",
    )
    assert conflict is None


def test_semantic_formatting_differences_no_false_conflict(conflict_svc):
    # 1. Entity name legal suffix: Inc. vs Incorporated
    assert conflict_svc.are_values_equivalent("NovaTech Solutions Inc.", "NovaTech Solutions Incorporated") is True

    # 2. Address word abbreviation: Street vs St, Suite vs Ste
    assert conflict_svc.are_values_equivalent("123 Main Street, Suite 500", "123 Main St, Ste 500") is True

    # 3. Date format: 2026-01-15 vs January 15, 2026
    assert conflict_svc.are_values_equivalent("2026-01-15", "January 15, 2026") is True

    # 4. Monetary formatting: $2,000,000 vs 2M
    assert conflict_svc.are_values_equivalent("$2,000,000", "2M") is True


def test_fabricated_conflicting_values_are_rejected(conflict_svc):
    cit_a = EvidenceCitation(
        document_name="registration.pdf",
        quote="Official Address: 42 Innovation Drive, Tech City",
        verified=True,
    )
    cit_b = EvidenceCitation(
        document_name="profile.pdf",
        quote="Corporate Office: 42 Innovation Drive, Tech City",
        verified=True,
    )

    # Hallucinated value not present in quote
    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-001",
        fact="address",
        fact_label="Address",
        citation_a=cit_a,
        value_a="999 Fake Street, Gotham City",
        citation_b=cit_b,
        value_b="42 Innovation Drive",
        explanation="Fabricated conflict.",
    )
    assert conflict is None  # Rejection of ungrounded value


def test_metadata_preservation_in_conflict(conflict_svc):
    cit_a = EvidenceCitation(
        document_name="reg.pdf",
        page_number=4,
        section="SECTION 2: ADDRESS",
        quote="Suite 800, Innovation Park",
        verified=True,
    )
    cit_b = EvidenceCitation(
        document_name="profile.pdf",
        page_number=8,
        section="LOCATION DETAILS",
        quote="Suite 400, Innovation Park",
        verified=True,
    )

    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-003",
        fact="address",
        fact_label="Address",
        citation_a=cit_a,
        value_a="Suite 800",
        citation_b=cit_b,
        value_b="Suite 400",
        explanation="Conflicting suites.",
    )

    assert conflict is not None
    assert conflict.source_a.citation.page_number == 4
    assert conflict.source_a.citation.section == "SECTION 2: ADDRESS"
    assert conflict.source_b.citation.page_number == 8
    assert conflict.source_b.citation.section == "LOCATION DETAILS"


def test_novatech_address_discrepancy_regression(conflict_svc):
    # NovaTech dataset canonical facts
    reg_quote = "REGISTERED OFFICE: 42 Innovation Drive, Suite 800, Tech City, TC 10001"
    profile_quote = "CORPORATE HEADQUARTERS: 42 Innovation Drive, Suite 400, Tech City, TC 10001"

    cit_reg = EvidenceCitation(
        document_name="novatech_business_registration.pdf",
        page_number=1,
        section="Corporate Registration",
        quote=reg_quote,
        verified=True,
    )
    cit_profile = EvidenceCitation(
        document_name="novatech_company_profile.pdf",
        page_number=1,
        section="Contact Information",
        quote=profile_quote,
        verified=True,
    )

    conflict = conflict_svc.build_fact_conflict(
        requirement_id="REQ-003",
        fact="office_address",
        fact_label="Registered Office Address",
        citation_a=cit_reg,
        value_a="Suite 800",
        citation_b=cit_profile,
        value_b="Suite 400",
        explanation="Business registration specifies Suite 800 whereas Company Profile specifies Suite 400.",
        severity=Priority.HIGH,
    )

    assert conflict is not None
    assert "Suite 800" in conflict.source_a.value
    assert "Suite 400" in conflict.source_b.value
    assert "Suite 800" in conflict.source_a.citation.quote
    assert "Suite 400" in conflict.source_b.citation.quote
    assert conflict.source_a.citation.document_name == "novatech_business_registration.pdf"
    assert conflict.source_b.citation.document_name == "novatech_company_profile.pdf"
