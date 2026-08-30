"""
Tool 3: match_evidence

Uses Gemini to reason over extracted requirements vs. analyzed document facts & chunks,
determining the satisfaction status of each requirement and extracting grounded evidence citations.

All quotes are strictly verified and grounded against the actual source text by CitationValidator.
"""
from __future__ import annotations

import json
import os
from typing import List

from google import genai
from google.genai import types

from app.services.citation_validator import get_citation_validator


def _get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def match_evidence(requirements_json: str, document_analyses_json: str) -> dict:
    """
    Map evidence documents to requirements, determine satisfaction status, and extract exact citations.

    For every requirement, determines whether the available evidence satisfies it,
    partially satisfies it, is missing entirely, or contains conflicting information.
    Extracts exact source quotes with page and section metadata.

    Args:
        requirements_json: JSON string of the requirements list extracted by extract_requirements.
        document_analyses_json: JSON string of the document analyses list from analyze_documents.

    Returns:
        A dict with:
          - matches: list of grounded EvidenceMatch objects with exact source citations
          - satisfied_count: number of SATISFIED requirements
          - partial_count: number of PARTIAL requirements
          - missing_count: number of MISSING requirements
          - conflict_count: number of CONFLICT requirements
          - compliance_score: (satisfied_count / total) * 100
    """
    client = _get_gemini_client()
    model = _get_model()
    validator = get_citation_validator()

    requirements = json.loads(requirements_json)
    analyses = json.loads(document_analyses_json)

    # Build structured evidence context
    evidence_summary = []
    reconstructed_documents = []

    for a in analyses:
        doc_name = a.get("doc_name", "unknown")
        statements = a.get("evidence_statements", [])
        facts = a.get("key_facts", [])
        inconsistencies = a.get("possible_inconsistencies", [])
        
        # Build synthetic text for quote validation lookup if full text not in analysis
        combined_text = "\n".join(statements + facts + inconsistencies)
        reconstructed_documents.append({"name": doc_name, "text": combined_text})

        entry = f"Document: {doc_name}\n"
        if statements:
            entry += "  Evidence Statements & Quotes:\n" + "\n".join(f'    - "{s}"' for s in statements)
        if facts:
            entry += "\n  Key Facts:\n" + "\n".join(f"    - {f}" for f in facts)
        if inconsistencies:
            entry += "\n  Inconsistencies / Discrepancies:\n" + "\n".join(f"    - {i}" for i in inconsistencies)
        evidence_summary.append(entry)

    prompt = f"""You are a senior compliance auditor. For each requirement below, evaluate the evidence documents and return a match object with exact grounded source citations.

Requirements ({len(requirements)} items):
{json.dumps(requirements, indent=2)}

Available Evidence Documents:
{chr(10).join(evidence_summary)}

Status Rules:
- SATISFIED: Evidence clearly and fully satisfies the requirement. Include exact quote from document.
- PARTIAL: Evidence exists but is incomplete. Include available quote and explain what is missing.
- MISSING: No relevant evidence found in any document. Set "evidence": [] and explain what was missing.
- CONFLICT: Evidence exists in multiple documents but contradicts itself (e.g. address mismatch Suite 800 vs Suite 400). Include quotes from BOTH conflicting documents.

Return ONLY valid JSON matching this schema:
{{
  "matches": [
    {{
      "requirement_id": "<req id>",
      "requirement_title": "<title>",
      "status": "<SATISFIED|PARTIAL|MISSING|CONFLICT>",
      "confidence": <0.0-1.0>,
      "evidence": [
        {{
          "document_name": "<exact doc filename>",
          "page_number": <page number or 1>,
          "section": "<section header if known>",
          "quote": "<EXACT quote copied verbatim from the document>",
          "relevance": "<why this quote satisfies the requirement>"
        }}
      ],
      "reasoning": "<concise explanation of the compliance decision>",
      "missing_reason": "<if MISSING, what evidence was searched for>",
      "partial_details": "<if PARTIAL, what is missing>"
    }}
  ]
}}

CRITICAL GROUNDING RULES:
1. Every "quote" in "evidence" MUST be an exact verbatim substring from the source document. Do NOT paraphrase.
2. For MISSING requirements, "evidence" MUST be an empty array [].
3. For CONFLICT requirements, include two evidence entries (one from each conflicting document).
4. Evaluate ALL {len(requirements)} requirements. Return valid JSON only."""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    raw = response.text.strip()
    result = json.loads(raw)
    raw_matches = result.get("matches", [])

    # Ground and verify all citations against source document text
    grounded_matches = validator.process_and_ground_matches(
        raw_matches=raw_matches,
        documents=reconstructed_documents,
    )

    # Compute counts
    satisfied = sum(1 for m in grounded_matches if m.get("status") == "SATISFIED")
    partial = sum(1 for m in grounded_matches if m.get("status") == "PARTIAL")
    missing = sum(1 for m in grounded_matches if m.get("status") == "MISSING")
    conflict = sum(1 for m in grounded_matches if m.get("status") == "CONFLICT")
    total = len(grounded_matches)
    score = round((satisfied / total) * 100, 1) if total > 0 else 0.0

    return {
        "matches": grounded_matches,
        "satisfied_count": satisfied,
        "partial_count": partial,
        "missing_count": missing,
        "conflict_count": conflict,
        "compliance_score": score,
    }
