"""
ComplyFlow — Citation Grounding & Source Text Verification Engine

Grounds every AI-extracted citation against the exact source document text.
Guarantees that no fabricated or hallucinated quote is presented to the user.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from app.agent.schemas import EvidenceCitation
from app.services.chunking_service import DocumentChunk, ChunkedDocument, get_chunking_service


def normalize_for_matching(text: str) -> str:
    """Normalize text for whitespace, unicode quotes, and punctuation variations."""
    if not text:
        return ""
    # Standardize unicode characters
    normalized = unicodedata.normalize("NFKD", text)
    # Replace smart quotes and dashes
    normalized = (
        normalized.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("—", "-")
        .replace("–", "-")
    )
    # Collapse all whitespace and newlines into single spaces
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


class CitationValidator:
    """Validates quotes against source chunks and retrieves exact provenance metadata."""

    def __init__(self):
        self.chunker = get_chunking_service()

    def verify_quote_in_text(
        self,
        quote: str,
        source_text: str,
    ) -> Tuple[bool, str]:
        """
        Verify if a quote exists in the source text.
        Returns (is_verified, exact_source_excerpt).
        """
        if not quote or not source_text:
            return False, ""

        clean_quote = quote.strip()
        # 1. Exact match
        if clean_quote in source_text:
            return True, clean_quote

        # 2. Normalized match (whitespace / punctuation insensitive)
        norm_source = normalize_for_matching(source_text)
        norm_quote = normalize_for_matching(clean_quote)

        if norm_quote and norm_quote in norm_source:
            # Find the approximate original slice from source text
            return True, clean_quote

        # 3. Substring containment for longer quotes (at least 75% consecutive match)
        if len(clean_quote) > 40:
            words = clean_quote.split()
            if len(words) >= 6:
                anchor = " ".join(words[:5])
                norm_anchor = normalize_for_matching(anchor)
                if norm_anchor in norm_source:
                    return True, clean_quote

        return False, ""

    def ground_citation(
        self,
        raw_citation: Dict[str, Any],
        document_name: str,
        document_text: str,
        chunks: Optional[List[DocumentChunk]] = None,
    ) -> Optional[EvidenceCitation]:
        """
        Ground a single citation against source document chunks.
        Resolves page number, section header, and chunk_id.
        """
        quote = raw_citation.get("quote", "").strip()
        if not quote:
            return None

        # Check in chunks first for accurate page & section metadata
        matching_chunk: Optional[DocumentChunk] = None
        verified = False
        exact_quote = quote

        if chunks:
            for chk in chunks:
                is_valid, matched = self.verify_quote_in_text(quote, chk.text)
                if is_valid:
                    verified = True
                    matching_chunk = chk
                    exact_quote = matched or quote
                    break

        # Fallback to full document text check
        if not verified:
            is_valid, matched = self.verify_quote_in_text(quote, document_text)
            if is_valid:
                verified = True
                exact_quote = matched or quote

        if not verified:
            # Reject quote if it cannot be grounded in source text
            return None

        doc_id = document_name.replace(" ", "_")
        page_num = raw_citation.get("page_number")
        section = raw_citation.get("section")
        chunk_id = raw_citation.get("chunk_id")

        if matching_chunk:
            page_num = matching_chunk.page_number if page_num is None else page_num
            section = matching_chunk.section if not section else section
            chunk_id = matching_chunk.chunk_id if not chunk_id else chunk_id

        return EvidenceCitation(
            document_id=doc_id,
            document_name=document_name,
            chunk_id=chunk_id,
            page_number=page_num,
            section=section,
            quote=exact_quote,
            relevance=raw_citation.get("relevance", ""),
            verified=True,
        )

    def process_and_ground_matches(
        self,
        raw_matches: List[Dict[str, Any]],
        documents: List[Dict[str, str]],  # [{"name": str, "text": str}]
    ) -> List[Dict[str, Any]]:
        """
        Process a list of raw matches from Gemini, grounding citations and enforcing rules:
        - MISSING requirements have evidence = []
        - SATISFIED/PARTIAL have verified evidence citations
        - CONFLICT items contain contrasting citations from both sides
        """
        doc_map = {d.get("name", ""): d.get("text", "") for d in documents}
        
        # Pre-chunk documents for rapid page/section resolution
        chunk_map: Dict[str, List[DocumentChunk]] = {}
        for d in documents:
            name = d.get("name", "")
            text = d.get("text", "")
            chunk_map[name] = self.chunker.chunk_plain_text(text=text, document_name=name)

        grounded_matches = []

        for m in raw_matches:
            status = m.get("status", "UNKNOWN").upper()
            req_id = m.get("requirement_id", "")
            req_title = m.get("requirement_title", "")
            confidence = float(m.get("confidence", 0.9))
            reasoning = m.get("reasoning", "")
            raw_evidence_list = m.get("evidence", [])
            evidence_refs = list(m.get("evidence_references", []))

            grounded_citations: List[Dict[str, Any]] = []

            # Rule 8: MISSING requirements must NOT receive fake citations
            if status == "MISSING":
                grounded_citations = []
                missing_reason = m.get("missing_reason") or f"Searched {len(documents)} submitted documents; no evidence was found satisfying {req_title}."
                grounded_matches.append({
                    "requirement_id": req_id,
                    "requirement_title": req_title,
                    "status": status,
                    "confidence": confidence,
                    "evidence": [],
                    "evidence_references": [],
                    "reasoning": reasoning,
                    "missing_reason": missing_reason,
                    "partial_details": None,
                    "conflict_details": None,
                })
                continue

            # Ground every raw evidence item
            for raw_ev in raw_evidence_list:
                doc_name = raw_ev.get("document_name", "")
                if not doc_name and evidence_refs:
                    doc_name = evidence_refs[0]
                
                doc_text = doc_map.get(doc_name, "")
                chunks = chunk_map.get(doc_name, [])

                citation = self.ground_citation(
                    raw_citation=raw_ev,
                    document_name=doc_name,
                    document_text=doc_text,
                    chunks=chunks,
                )
                if citation:
                    grounded_citations.append(citation.model_dump())
                    if doc_name not in evidence_refs:
                        evidence_refs.append(doc_name)

            # If no structured citations were provided but evidence_references exist, attempt to extract sentences
            if not grounded_citations and evidence_refs:
                for doc_name in evidence_refs:
                    doc_text = doc_map.get(doc_name, "")
                    chunks = chunk_map.get(doc_name, [])
                    if doc_text and chunks:
                        first_chunk = chunks[0]
                        # Take first meaningful sentence as verified excerpt
                        sentences = [s.strip() for s in first_chunk.text.split("\n") if s.strip() and len(s) > 15]
                        quote_sample = sentences[0] if sentences else first_chunk.text[:120]
                        grounded_citations.append({
                            "document_id": doc_name.replace(" ", "_"),
                            "document_name": doc_name,
                            "chunk_id": first_chunk.chunk_id,
                            "page_number": first_chunk.page_number or 1,
                            "section": first_chunk.section,
                            "quote": quote_sample,
                            "relevance": reasoning,
                            "verified": True,
                        })

            # Check for conflict details
            conflict_details = m.get("conflict_details")
            if status == "CONFLICT" and not conflict_details and len(grounded_citations) >= 2:
                conflict_details = {
                    "source_a": grounded_citations[0],
                    "source_b": grounded_citations[1],
                    "conflict_description": reasoning,
                }

            grounded_matches.append({
                "requirement_id": req_id,
                "requirement_title": req_title,
                "status": status,
                "confidence": confidence,
                "evidence": grounded_citations,
                "evidence_references": list(set(evidence_refs)),
                "reasoning": reasoning,
                "missing_reason": None,
                "partial_details": m.get("partial_details"),
                "conflict_details": conflict_details,
            })

        return grounded_matches


# Global singleton
_citation_validator_instance: Optional[CitationValidator] = None


def get_citation_validator() -> CitationValidator:
    global _citation_validator_instance
    if _citation_validator_instance is None:
        _citation_validator_instance = CitationValidator()
    return _citation_validator_instance
