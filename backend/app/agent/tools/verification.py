"""
Tool 6: verify_compliance

Final verification tool. Called after the user uploads corrected/missing evidence.
Uses Gemini to re-evaluate all requirements against the updated document set,
determines whether previously identified gaps are resolved, extracts grounded citations,
and produces a final READY or ACTION_REQUIRED verdict.
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


def verify_compliance(
    requirements_json: str,
    updated_document_analyses_json: str,
    previous_gaps_json: str,
) -> dict:
    """
    Verify compliance after the user has uploaded corrected or missing evidence.

    Re-evaluates all requirements against the updated document set, determines
    which previously identified gaps have been resolved, extracts grounded evidence citations,
    and produces a final READY or ACTION_REQUIRED verdict with a full updated compliance score.

    Args:
        requirements_json: JSON string of the requirements list (from extract_requirements).
        updated_document_analyses_json: JSON string of analyses of ALL documents
            (original + newly uploaded), from analyze_documents run on the updated set.
        previous_gaps_json: JSON string of the gaps list from the previous detect_gaps run.

    Returns:
        A dict with:
          - overall_status: "READY" or "ACTION_REQUIRED"
          - compliance_score: 0.0-100.0
          - satisfied_count: number of satisfied requirements
          - total_count: total requirements
          - resolved_gaps: list of gap_ids that were resolved
          - remaining_gaps: list of gap_ids still open
          - new_issues: list of any new issues found
          - summary: human-readable summary of verification result
          - matches: updated list of grounded requirement matches
    """
    client = _get_gemini_client()
    model = _get_model()
    validator = get_citation_validator()

    requirements = json.loads(requirements_json)
    analyses = json.loads(updated_document_analyses_json)
    previous_gaps = json.loads(previous_gaps_json)

    # Build evidence summary from updated documents
    evidence_summary = []
    reconstructed_documents = []

    for a in analyses:
        doc_name = a.get("doc_name", "unknown")
        statements = a.get("evidence_statements", [])
        facts = a.get("key_facts", [])
        inconsistencies = a.get("possible_inconsistencies", [])
        
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

    previous_gap_ids = [g.get("gap_id") for g in previous_gaps]

    prompt = f"""You are a compliance analyst performing a FINAL VERIFICATION AUDIT.

The user has uploaded additional/corrected evidence. Re-evaluate ALL requirements against
the UPDATED document set, extract exact grounded citations, and determine whether each gap has been resolved.

Requirements ({len(requirements)} total):
{json.dumps(requirements, indent=2)}

Updated Evidence from ALL Documents (original + newly uploaded):
{chr(10).join(evidence_summary)}

Previous gaps that needed resolution:
{json.dumps(previous_gaps, indent=2)}

Previous gap IDs: {previous_gap_ids}

Return ONLY valid JSON matching this schema:
{{
  "overall_status": "<READY|ACTION_REQUIRED>",
  "compliance_score": <0.0-100.0>,
  "satisfied_count": <number>,
  "total_count": {len(requirements)},
  "resolved_gaps": ["<gap_id of resolved gaps>"],
  "remaining_gaps": ["<gap_id of still-open gaps>"],
  "new_issues": ["<description of any new issue found, empty if none>"],
  "summary": "<2-3 sentence human-readable summary of the verification result>",
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
      "reasoning": "<concise explanation of compliance decision>"
    }}
  ]
}}

CRITICAL GROUNDING RULES:
1. Every "quote" in "evidence" MUST be an exact verbatim substring from the source document.
2. For MISSING requirements, "evidence" MUST be an empty array [].
3. For CONFLICT requirements, include two evidence entries.
4. overall_status must be "READY" only if ALL {len(requirements)} requirements are SATISFIED with 0 remaining gaps.
Return valid JSON only."""

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

    # Ground all citations
    grounded_matches = validator.process_and_ground_matches(
        raw_matches=raw_matches,
        documents=reconstructed_documents,
    )
    result["matches"] = grounded_matches

    # Enforce score and status consistency
    satisfied = sum(1 for m in grounded_matches if m.get("status") == "SATISFIED")
    total = len(requirements)
    score = round((satisfied / total) * 100, 1) if total > 0 else 0.0

    result["satisfied_count"] = satisfied
    result["total_count"] = total
    result["compliance_score"] = score
    result["overall_status"] = "READY" if satisfied == total else "ACTION_REQUIRED"

    return result
