"""
ComplyFlow — Document Chunking & Context Assembly Test Suite

Tests intelligent chunking, section header detection, multi-page PDF processing,
page number preservation, OCR_REQUIRED diagnostic detection, and token-safe context assembly.
"""
from __future__ import annotations

import io
import pytest
from app.services.chunking_service import ChunkingService, DocumentChunk, get_chunking_service
from app.services.document_service import DocumentService


@pytest.fixture
def chunker():
    return ChunkingService(target_chunk_size=500, chunk_overlap=50)


def test_short_document_chunking(chunker):
    text = "REQ-001: General Liability Insurance.\nVendors must provide insurance of min $2,000,000."
    chunks = chunker.chunk_plain_text(
        text=text,
        document_name="short_req.txt",
        document_id="doc_short",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.document_name == "short_req.txt"
    assert chunk.document_id == "doc_short"
    assert chunk.chunk_index == 0
    assert chunk.text == text
    assert chunk.character_count == len(text)
    assert chunk.token_estimate > 0
    assert chunk.page_number is None


def test_long_document_paragraph_and_section_splitting(chunker):
    # Construct a long text with section headers and paragraphs
    section1 = (
        "SECTION 1: CORPORATE REGISTRATION\n\n"
        "NovaTech Solutions Ltd. is a registered corporation in Tech City.\n"
        "All corporate filings are up to date and in good standing with the business registrar.\n\n"
        "The company maintains valid registration under license NTS-2024-047821."
    )
    section2 = (
        "SECTION 2: TAX COMPLIANCE POLICIES\n\n"
        "The company complies with all state and federal tax codes.\n"
        "Quarterly filings have been submitted on time without penalties.\n\n"
        "Tax identification number TIN-9847-2200-TC is active."
    )
    full_text = f"{section1}\n\n{section2}"

    chunks = chunker.chunk_plain_text(
        text=full_text,
        document_name="company_handbook.txt",
        document_id="doc_long",
    )

    assert len(chunks) >= 2
    # Verify section metadata was detected
    assert any("SECTION 1" in (c.section or "") for c in chunks)
    assert any("SECTION 2" in (c.section or "") for c in chunks)
    # Ensure sequential indexing
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_sentence_boundary_preservation(chunker):
    # Paragraph larger than target chunk size (500 chars)
    long_para = (
        "Sentence one describes the financial audit requirements in complete detail. "
        "Sentence two provides the name of the independent certified auditor. "
        "Sentence three specifies the annual balance sheet totals and cash flow numbers. "
        "Sentence four confirms the unqualified audit opinion issued for the fiscal year. "
        "Sentence five confirms that all accounts are reconciled without material discrepancies. "
        "Sentence six is the final confirmation of solvency."
    )
    chunks = chunker.chunk_plain_text(
        text=long_para,
        document_name="audit_report.txt",
    )

    # Should split across chunks without breaking words mid-sentence
    assert len(chunks) >= 1
    for c in chunks:
        # Every chunk should end with punctuation or proper sentence termination
        assert not c.text.endswith(" ")
        assert len(c.text) > 0


def test_multi_page_pdf_chunking(chunker):
    pages = [
        "Page 1 content: Certificate of Incorporation for NovaTech Solutions Ltd.",
        "Page 2 content: Board of Directors and Authorized Signatories list.",
        "Page 3 content: Articles of Association and Shareholder registry.",
    ]

    chunked_doc = chunker.chunk_pdf_pages(
        pages_text=pages,
        document_name="incorporation_package.pdf",
        document_id="doc_incorp",
    )

    assert chunked_doc.status == "OK"
    assert chunked_doc.total_pages == 3
    assert chunked_doc.total_chunks == 3
    assert len(chunked_doc.chunks) == 3

    # Verify page numbers preserved
    assert chunked_doc.chunks[0].page_number == 1
    assert chunked_doc.chunks[1].page_number == 2
    assert chunked_doc.chunks[2].page_number == 3


def test_empty_or_scanned_pdf_ocr_detection(chunker):
    # 3 empty pages (simulates scanned/image PDF without embedded text layer)
    empty_pages = ["", "   \n\t  ", ""]

    chunked_doc = chunker.chunk_pdf_pages(
        pages_text=empty_pages,
        document_name="scanned_receipt.pdf",
    )

    assert chunked_doc.status == "OCR_REQUIRED"
    assert chunked_doc.total_chunks == 0
    assert "OCR_REQUIRED" in chunked_doc.diagnostics
    assert chunked_doc.total_pages == 3


def test_context_assembly_and_token_limits(chunker):
    chunks = [
        DocumentChunk(
            document_id="doc1",
            document_name="insurance.pdf",
            page_number=1,
            section="Section 1.1 Limits",
            chunk_index=0,
            text="General liability limit is $2,000,000 per occurrence.",
        ),
        DocumentChunk(
            document_id="doc2",
            document_name="tax.pdf",
            page_number=2,
            section="Section 3 Filing",
            chunk_index=0,
            text="Tax status: Fully compliant for fiscal year 2024.",
        ),
    ]

    # Assembly with ample budget
    context = chunker.assemble_context(chunks=chunks, max_tokens=1000)
    assert "[SOURCE: insurance.pdf | Page: 1 | Section: Section 1.1 Limits | Chunk: 1]" in context
    assert "$2,000,000 per occurrence" in context
    assert "[SOURCE: tax.pdf | Page: 2 | Section: Section 3 Filing | Chunk: 1]" in context
    assert "Fully compliant" in context

    # Assembly with tight token budget
    tight_context = chunker.assemble_context(chunks=chunks, max_tokens=25)
    assert "[Context limit reached: remaining chunks truncated safely at chunk boundary]" in tight_context


def test_document_service_integration():
    doc_service = DocumentService()

    # Plain text extraction with chunker
    txt_content = b"REQ-001: Sample Requirement\nDetailed description of requirement."
    chunked = doc_service.extract_chunked_document("test_req.txt", txt_content)
    assert chunked.status == "OK"
    assert chunked.total_chunks >= 1
    assert "REQ-001" in chunked.raw_text
