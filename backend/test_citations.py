"""
ComplyFlow — Citation Grounding & Evidence Provenance Test Suite

Tests exact quote preservation, quote validation/rejection of hallucinations,
page and section metadata preservation, multiple citations, zero citations on MISSING,
conflict citation pairs, and normalized quote matching.
"""
from __future__ import annotations

import pytest
from app.services.citation_validator import CitationValidator, normalize_for_matching
from app.services.chunking_service import DocumentChunk, ChunkingService


@pytest.fixture
def validator():
    return CitationValidator()


def test_quote_exact_verification(validator):
    source_text = "This is to certify that NovaTech Solutions Ltd. is registered under license NTS-2024-047821."
    quote = "NovaTech Solutions Ltd. is registered under license NTS-2024-047821"

    is_valid, matched = validator.verify_quote_in_text(quote, source_text)
    assert is_valid is True
    assert matched == quote


def test_quote_validation_rejects_fabricated_text(validator):
    source_text = "General liability insurance limit is $2,000,000 per occurrence."
    fabricated_quote = "The company has cybersecurity insurance coverage of $5,000,000 with AIG"

    is_valid, _ = validator.verify_quote_in_text(fabricated_quote, source_text)
    assert is_valid is False


def test_normalized_quote_matching_whitespace_and_quotes(validator):
    # Source has standard quotes and multi-line breaks
    source_text = 'REGISTERED OFFICE ADDRESS:\n  42 Innovation Drive, Suite 800,\n  Tech City, TC 10001'
    # Quote from LLM has collapsed spaces and quotes
    quote = "REGISTERED OFFICE ADDRESS: 42 Innovation Drive, Suite 800, Tech City, TC 10001"

    is_valid, _ = validator.verify_quote_in_text(quote, source_text)
    assert is_valid is True


def test_grounding_preserves_page_and_section_metadata(validator):
    chunks = [
        DocumentChunk(
            document_id="doc_ins",
            document_name="insurance_policy.pdf",
            page_number=3,
            section="SECTION 4: LIABILITY LIMITS",
            chunk_index=2,
            text="Professional liability each claim limit: $1,000,000. Annual aggregate: $2,000,000.",
        )
    ]

    raw_citation = {
        "quote": "Professional liability each claim limit: $1,000,000",
        "relevance": "Confirms professional liability limit meets criteria.",
    }

    grounded = validator.ground_citation(
        raw_citation=raw_citation,
        document_name="insurance_policy.pdf",
        document_text=chunks[0].text,
        chunks=chunks,
    )

    assert grounded is not None
    assert grounded.verified is True
    assert grounded.page_number == 3
    assert grounded.section == "SECTION 4: LIABILITY LIMITS"
    assert grounded.document_name == "insurance_policy.pdf"
    assert "Professional liability" in grounded.quote


def test_missing_requirement_has_zero_citations(validator):
    raw_matches = [
        {
            "requirement_id": "REQ-006",
            "requirement_title": "Insurance Certificate",
            "status": "MISSING",
            "confidence": 1.0,
            "reasoning": "No insurance document was provided in the submission.",
            "evidence": [
                {
                    "document_name": "unknown.pdf",
                    "quote": "Some hallucinated quote",
                }
            ],
        }
    ]

    documents = [{"name": "tax.pdf", "text": "Tax compliance cert"}]
    grounded_matches = validator.process_and_ground_matches(raw_matches, documents)

    assert len(grounded_matches) == 1
    m = grounded_matches[0]
    assert m["status"] == "MISSING"
    assert len(m["evidence"]) == 0  # Zero citations enforced for MISSING
    assert m["missing_reason"] is not None


def test_partial_requirement_contains_supporting_citations(validator):
    raw_matches = [
        {
            "requirement_id": "REQ-010",
            "requirement_title": "Technical Specs & SLA",
            "status": "PARTIAL",
            "confidence": 0.85,
            "reasoning": "Technical specifications provided but 99.99% premium SLA is missing.",
            "evidence": [
                {
                    "document_name": "tech_specs.txt",
                    "page_number": 1,
                    "section": "SLA",
                    "quote": "Standard SLA: 99.9% uptime, 4-hour response",
                    "relevance": "Confirms standard SLA exists.",
                }
            ],
            "partial_details": "Standard SLA provided; premium SLA document missing.",
        }
    ]

    documents = [
        {"name": "tech_specs.txt", "text": "TECHNICAL SPECIFICATIONS\nStandard SLA: 99.9% uptime, 4-hour response"}
    ]
    grounded_matches = validator.process_and_ground_matches(raw_matches, documents)

    assert len(grounded_matches) == 1
    m = grounded_matches[0]
    assert m["status"] == "PARTIAL"
    assert len(m["evidence"]) == 1
    assert m["evidence"][0]["quote"] == "Standard SLA: 99.9% uptime, 4-hour response"
    assert m["partial_details"] is not None


def test_conflict_contains_citations_to_both_sources(validator):
    raw_matches = [
        {
            "requirement_id": "REQ-003",
            "requirement_title": "Address Confirmation",
            "status": "CONFLICT",
            "confidence": 0.95,
            "reasoning": "Registration document lists Suite 800 whereas Company Profile lists Suite 400.",
            "evidence": [
                {
                    "document_name": "registration.txt",
                    "page_number": 1,
                    "quote": "Registered Address: 42 Innovation Drive, Suite 800, Tech City",
                    "relevance": "Official legal address.",
                },
                {
                    "document_name": "company_profile.txt",
                    "page_number": 1,
                    "quote": "REGISTERED OFFICE ADDRESS: 42 Innovation Drive, Suite 400, Tech City",
                    "relevance": "Conflicting office address.",
                },
            ],
        }
    ]

    documents = [
        {"name": "registration.txt", "text": "Registered Address: 42 Innovation Drive, Suite 800, Tech City"},
        {"name": "company_profile.txt", "text": "REGISTERED OFFICE ADDRESS: 42 Innovation Drive, Suite 400, Tech City"},
    ]

    grounded_matches = validator.process_and_ground_matches(raw_matches, documents)

    assert len(grounded_matches) == 1
    m = grounded_matches[0]
    assert m["status"] == "CONFLICT"
    assert len(m["evidence"]) == 2
    assert "Suite 800" in m["evidence"][0]["quote"]
    assert "Suite 400" in m["evidence"][1]["quote"]
    assert m["conflict_details"] is not None


def test_multiple_citations_for_single_requirement(validator):
    raw_matches = [
        {
            "requirement_id": "REQ-001",
            "requirement_title": "Business Registration & Standing",
            "status": "SATISFIED",
            "confidence": 0.98,
            "reasoning": "Registration number and good standing confirmed across two official documents.",
            "evidence": [
                {
                    "document_name": "reg_cert.txt",
                    "page_number": 1,
                    "quote": "Registration Number: NTS-2024-047821",
                    "relevance": "Proves valid registration number.",
                },
                {
                    "document_name": "bank_ref.txt",
                    "page_number": 1,
                    "quote": "Account is currently active and in GOOD STANDING",
                    "relevance": "Confirms good commercial standing.",
                },
            ],
        }
    ]

    documents = [
        {"name": "reg_cert.txt", "text": "Registration Number: NTS-2024-047821\nStatus: ACTIVE"},
        {"name": "bank_ref.txt", "text": "Account is currently active and in GOOD STANDING"},
    ]

    grounded_matches = validator.process_and_ground_matches(raw_matches, documents)

    assert len(grounded_matches) == 1
    m = grounded_matches[0]
    assert m["status"] == "SATISFIED"
    assert len(m["evidence"]) == 2
    assert m["evidence"][0]["document_name"] == "reg_cert.txt"
    assert m["evidence"][1]["document_name"] == "bank_ref.txt"
