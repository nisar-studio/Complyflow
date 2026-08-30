"""
Tool 4: detect_gaps

Uses Gemini to reason over evidence match results and identify compliance gaps:
missing evidence, fact-level conflicts, expired documents, and incomplete evidence.

Every conflict gap includes structured, fact-level comparisons (Source A value vs Source B value).
"""
from __future__ import annotations

import json
import os
from typing import List

from google import genai
from google.genai import types

from app.agent.schemas import EvidenceCitation, Priority
from app.services.conflict_service import get_conflict_service


def _get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def detect_gaps(matches_json: str) -> dict:
    """
    Identify compliance gaps and fact-level conflicts from evidence match results.

    Analyzes match results to identify missing evidence, conflicting information,
    expired documents, and incomplete requirements.
    For conflicts, extracts explicit contrasting facts, values, and source citations.

    Args:
        matches_json: JSON string of the matches list from match_evidence.

    Returns:
        A dict with:
          - gaps: list of Gap objects (including fact-level conflict_detail)
          - critical_count: number of CRITICAL gaps
          - high_count: number of HIGH gaps
          - medium_count: number of MEDIUM gaps
          - low_count: number of LOW gaps
    """
    client = _get_gemini_client()
    model = _get_model()
    conflict_service = get_conflict_service()

    matches = json.loads(matches_json)

    # Filter to only non-satisfied matches for efficiency
    problem_matches = [m for m in matches if m.get("status") != "SATISFIED"]

    if not problem_matches:
        return {
            "gaps": [],
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
        }

    prompt = f"""You are a senior compliance auditor. Based on these evidence match results, identify and describe each compliance gap in detail.

Match results with issues:
{json.dumps(problem_matches, indent=2)}

For each problematic match, create a gap object. Gap types:
- missing_evidence: Required evidence document/information is absent
- conflict: Two or more sources contradict each other on a specific fact (e.g. address, dates, coverage amounts)
- incomplete: Evidence exists but is insufficient or partial
- expired: Evidence may be outdated
- ambiguous: Evidence is unclear or could be interpreted multiple ways

For "conflict" gaps, you MUST extract:
- fact: machine-readable key (e.g. "company_address", "insurance_limit", "effective_date")
- fact_label: human-readable name (e.g. "Registered Office Address", "General Liability Limit")
- value_a: exact value claimed by Source A
- value_b: exact value claimed by Source B
- conflict_explanation: 1-2 sentences explaining why the values contradict

Return ONLY valid JSON matching this schema:
{{
  "gaps": [
    {{
      "gap_id": "GAP-001",
      "gap_type": "<missing_evidence|conflict|incomplete|expired|ambiguous>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "description": "<clear description of the gap>",
      "related_requirement_id": "<REQ-xxx>",
      "related_requirement_title": "<title>",
      "affected_documents": ["<doc name>"],
      "recommended_action": "<specific action the user should take>",
      "conflict_fact": "<fact key if conflict, else null>",
      "conflict_fact_label": "<fact label if conflict, else null>",
      "conflict_value_a": "<value in source A if conflict, else null>",
      "conflict_value_b": "<value in source B if conflict, else null>",
      "conflict_explanation": "<why contradictory if conflict, else null>"
    }}
  ]
}}

Create exactly one gap per problematic match. Number gaps sequentially: GAP-001, GAP-002, etc.
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
    raw_gaps = result.get("gaps", [])

    # Map matches by requirement_id for rapid citation lookup
    match_by_req = {m.get("requirement_id"): m for m in problem_matches}

    final_gaps = []
    for i, gap in enumerate(raw_gaps):
        gap_id = f"GAP-{i+1:03d}"
        gap["gap_id"] = gap_id
        gap_type = gap.get("gap_type", "missing_evidence")
        req_id = gap.get("related_requirement_id", "")
        req_match = match_by_req.get(req_id, {})
        evidence_list = req_match.get("evidence", [])

        # Process conflict detail if this is a conflict
        conflict_detail = None
        if gap_type == "conflict" and len(evidence_list) >= 2:
            cit_a = EvidenceCitation(**evidence_list[0])
            cit_b = EvidenceCitation(**evidence_list[1])
            val_a = gap.get("conflict_value_a") or cit_a.quote[:60]
            val_b = gap.get("conflict_value_b") or cit_b.quote[:60]
            fact = gap.get("conflict_fact") or "conflicting_fact"
            fact_label = gap.get("conflict_fact_label") or "Conflicting Information"
            explanation = gap.get("conflict_explanation") or gap.get("description", "")

            # Build and ground through ConflictService
            constructed = conflict_service.build_fact_conflict(
                requirement_id=req_id,
                fact=fact,
                fact_label=fact_label,
                citation_a=cit_a,
                value_a=val_a,
                citation_b=cit_b,
                value_b=val_b,
                explanation=explanation,
                severity=Priority(gap.get("severity", "HIGH")),
                recommended_action=gap.get("recommended_action", ""),
            )
            if constructed:
                conflict_detail = constructed.model_dump()

        final_gaps.append({
            "gap_id": gap_id,
            "gap_type": gap_type,
            "severity": gap.get("severity", "HIGH"),
            "description": gap.get("description", ""),
            "related_requirement_id": req_id,
            "related_requirement_title": gap.get("related_requirement_title", ""),
            "affected_documents": gap.get("affected_documents", []),
            "recommended_action": gap.get("recommended_action", ""),
            "conflict_detail": conflict_detail,
        })

    critical = sum(1 for g in final_gaps if g.get("severity") == "CRITICAL")
    high = sum(1 for g in final_gaps if g.get("severity") == "HIGH")
    medium = sum(1 for g in final_gaps if g.get("severity") == "MEDIUM")
    low = sum(1 for g in final_gaps if g.get("severity") == "LOW")

    return {
        "gaps": final_gaps,
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
    }
