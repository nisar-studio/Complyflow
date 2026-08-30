"""
Tool 5: create_remediation_plan

Uses Gemini to reason over detected compliance gaps and convert them into
a prioritized, actionable remediation checklist.

For fact-level conflicts, generates specific resolution actions detailing
which documents to verify and update.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types


def _get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def create_remediation_plan(gaps_json: str) -> dict:
    """
    Convert compliance gaps into a prioritized, actionable remediation checklist.

    For each gap, produces a specific RemediationTask telling the user exactly what
    document to upload or what information/conflict to correct.

    Args:
        gaps_json: JSON string of the gaps list from detect_gaps.

    Returns:
        A dict with:
          - tasks: list of RemediationTask objects
          - total_tasks: total number of remediation tasks
          - estimated_effort: brief human-readable effort description
    """
    client = _get_gemini_client()
    model = _get_model()

    gaps = json.loads(gaps_json)

    if not gaps:
        return {
            "tasks": [],
            "total_tasks": 0,
            "estimated_effort": "No remediation required. All requirements satisfied.",
        }

    prompt = f"""You are a compliance project manager. Convert these compliance gaps into clear, actionable remediation tasks.

Compliance gaps to resolve:
{json.dumps(gaps, indent=2)}

For each gap, create one task. Tasks must be:
- Specific: tell the user exactly what document to upload or action to take
- Actionable: a user can complete this without additional clarification
- Prioritized: ordered CRITICAL first, then HIGH, MEDIUM, LOW
- For conflicts: specify the conflicting values and which documents need reconciliation (e.g. 'Reconcile company address between Business Registration and Company Profile')

Return ONLY valid JSON:
{{
  "tasks": [
    {{
      "task_id": "TASK-001",
      "title": "<short action title, e.g. 'Reconcile Registered Address' or 'Upload Insurance Certificate'>",
      "description": "<detailed description of what to do, mentioning specific values/documents>",
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "required_action": "<specific action: 'upload_document' | 'review_and_correct' | 'obtain_signature' | 'update_information'>",
      "related_requirement_id": "<REQ-xxx>",
      "related_requirement_title": "<title>",
      "status": "OPEN"
    }}
  ],
  "total_tasks": <number>,
  "estimated_effort": "<brief summary like '1 document to upload, 1 address discrepancy to resolve'>"
}}

Create one task per gap. Number tasks TASK-001, TASK-002, etc.
Order by severity: CRITICAL first, then HIGH, MEDIUM, LOW.
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
    tasks = result.get("tasks", [])

    # Ensure sequential IDs
    for i, task in enumerate(tasks):
        if "task_id" not in task or not task["task_id"]:
            task["task_id"] = f"TASK-{i+1:03d}"
        if "status" not in task:
            task["status"] = "OPEN"

    result["total_tasks"] = len(tasks)
    return result
