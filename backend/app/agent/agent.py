"""
ComplyFlow — ADK Agent Orchestrator

This module defines the Google ADK LlmAgent and provides the runner function
that orchestrates the full compliance workflow.

Architecture:
  FastAPI route → run_compliance_analysis() / run_verification()
      → ADK Runner → LlmAgent (Gemini)
          → Tool selection and execution (6 tools)
          → Observation → Next action
      → Structured results → Firestore → SSE/API response

The ADK agent autonomously decides which tools to call in what order.
We use the system prompt to guide this, but do NOT hard-code the sequence
in the runner — ADK handles orchestration.

Fallback: If the agent completes without calling all expected tools, we
detect this and call missing tools explicitly to guarantee the workflow.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable, List, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools.requirements import extract_requirements
from app.agent.tools.documents import analyze_documents
from app.agent.tools.matching import match_evidence
from app.agent.tools.gaps import detect_gaps
from app.agent.tools.remediation import create_remediation_plan
from app.agent.tools.verification import verify_compliance

# ─────────────────────────────────────────────────────────────
# ADK Agent Definition
# ─────────────────────────────────────────────────────────────

def _build_agent() -> LlmAgent:
    """Build the ComplyFlow ADK agent with all 6 tools registered."""
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    return LlmAgent(
        name="complyflow_agent",
        model=model,
        description="Autonomous compliance verification agent.",
        instruction=SYSTEM_PROMPT,
        tools=[
            extract_requirements,
            analyze_documents,
            match_evidence,
            detect_gaps,
            create_remediation_plan,
            verify_compliance,
        ],
    )


# ─────────────────────────────────────────────────────────────
# Event emission helper
# ─────────────────────────────────────────────────────────────

def _make_event(
    project_id: str,
    event_type: str,
    status: str,
    summary: str,
    tool: Optional[str] = None,
    data: Optional[dict] = None,
) -> dict:
    return {
        "event_id": "",  # filled by Firestore
        "project_id": project_id,
        "type": event_type,
        "tool": tool,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "data": data or {},
    }


# ─────────────────────────────────────────────────────────────
# Main Analysis Runner
# ─────────────────────────────────────────────────────────────

async def run_compliance_analysis(
    project_id: str,
    requirements_text: str,
    documents: List[dict],  # [{"name": str, "text": str}]
    emit_event: Callable[[dict], None],
) -> dict:
    """
    Run the full compliance analysis workflow via ADK.

    The ADK agent receives the goal and document context, then autonomously
    selects and calls tools. After ADK completes, we parse the tool call
    history to extract structured results.

    Args:
        project_id: Firestore project ID.
        requirements_text: Extracted text of the requirements document.
        documents: List of {"name": filename, "text": extracted_text} dicts.
        emit_event: Callback to emit agent events to Firestore/SSE queue.

    Returns:
        dict with keys: requirements, matches, gaps, tasks, compliance_score,
        overall_status, satisfied_count, total_count.
    """
    emit_event(_make_event(project_id, "AGENT_STARTED", "started",
                           "ComplyFlow agent starting compliance analysis"))

    try:
        agent = _build_agent()
        session_service = InMemorySessionService()
        app_name = f"complyflow_{project_id}"
        session_id = f"session_{project_id}"
        user_id = "demo-user"

        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )

        # Build the user message — provide all context for ADK to reason over
        documents_json = json.dumps(documents)
        user_message = f"""Perform a complete compliance analysis for project {project_id}.

REQUIREMENTS DOCUMENT:
{requirements_text}

EVIDENCE DOCUMENTS (JSON):
{documents_json}

Use your tools in this order:
1. extract_requirements — pass the requirements document text
2. analyze_documents — pass the documents JSON string
3. match_evidence — pass requirements and document analyses as JSON strings
4. detect_gaps — pass the matches as JSON string
5. create_remediation_plan — pass the gaps as JSON string

Complete all 5 steps and provide a final compliance summary."""

        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)],
        )

        # ── Track tool results from ADK event stream ─────────────────
        tool_results: dict = {}
        current_tool: Optional[str] = None

        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Reading and extracting requirements", tool="extract_requirements"))

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            if not hasattr(event, "content") or not event.content:
                continue

            for part in event.content.parts:
                # Tool call initiated by agent
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    current_tool = fc.name
                    emit_event(_make_event(
                        project_id, "TOOL_STARTED", "started",
                        f"Executing {fc.name}...", tool=fc.name
                    ))

                # Tool result returned
                elif hasattr(part, "function_response") and part.function_response:
                    fr = part.function_response
                    tool_name = fr.name
                    response_data = dict(fr.response) if fr.response else {}

                    tool_results[tool_name] = response_data

                    # Emit appropriate event based on tool
                    summaries = {
                        "extract_requirements": f"Extracted {response_data.get('total_count', 0)} requirements",
                        "analyze_documents": f"Analyzed {len(response_data.get('analyses', []))} documents",
                        "match_evidence": (
                            f"Matched evidence: {response_data.get('satisfied_count', 0)} satisfied, "
                            f"{response_data.get('missing_count', 0)} missing, "
                            f"{response_data.get('conflict_count', 0)} conflicts"
                        ),
                        "detect_gaps": f"Detected {len(response_data.get('gaps', []))} gaps",
                        "create_remediation_plan": f"Created {response_data.get('total_tasks', 0)} remediation tasks",
                    }
                    summary = summaries.get(tool_name, f"{tool_name} completed")
                    emit_event(_make_event(
                        project_id, "TOOL_COMPLETED", "completed", summary, tool=tool_name
                    ))

            if hasattr(event, "is_final_response") and event.is_final_response():
                break

        # ── Fallback: call missing tools explicitly ───────────────────
        results = await _ensure_complete_workflow(
            project_id, requirements_text, documents_json,
            tool_results, emit_event
        )

        emit_event(_make_event(
            project_id, "AGENT_COMPLETED", "completed",
            f"Analysis complete. Score: {results.get('compliance_score', 0)}% — "
            f"{results.get('overall_status', 'UNKNOWN')}"
        ))

        return results

    except Exception as e:
        # Sanitize error: never expose API keys, credentials, or stack traces
        safe_message = _sanitize_error(str(e))
        emit_event(_make_event(
            project_id, "AGENT_ERROR", "error",
            safe_message,
            tool=current_tool if 'current_tool' in dir() else None,
            data={"recoverable": True, "failed_stage": current_tool if 'current_tool' in dir() else "agent_init"},
        ))
        raise


async def _ensure_complete_workflow(
    project_id: str,
    requirements_text: str,
    documents_json: str,
    tool_results: dict,
    emit_event: Callable,
) -> dict:
    """
    Ensure all required tools were called. If ADK skipped any, call them directly.
    This is the reliability fallback — not the primary path.
    """
    # Step 1: extract_requirements
    if "extract_requirements" not in tool_results:
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Extracting requirements (fallback)", tool="extract_requirements"))
        tool_results["extract_requirements"] = extract_requirements(requirements_text)
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               f"Extracted {tool_results['extract_requirements'].get('total_count', 0)} requirements",
                               tool="extract_requirements"))

    req_result = tool_results["extract_requirements"]
    requirements = req_result.get("requirements", [])

    # Step 2: analyze_documents
    if "analyze_documents" not in tool_results:
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Analyzing documents (fallback)", tool="analyze_documents"))
        tool_results["analyze_documents"] = analyze_documents(documents_json)
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               "Document analysis complete", tool="analyze_documents"))

    analyses = tool_results["analyze_documents"].get("analyses", [])

    # Step 3: match_evidence
    if "match_evidence" not in tool_results:
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Mapping evidence to requirements (fallback)", tool="match_evidence"))
        tool_results["match_evidence"] = match_evidence(
            json.dumps(requirements),
            json.dumps(analyses),
        )
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               "Evidence mapping complete", tool="match_evidence"))

    match_result = tool_results["match_evidence"]
    matches = match_result.get("matches", [])

    # Step 4: detect_gaps
    if "detect_gaps" not in tool_results:
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Detecting compliance gaps (fallback)", tool="detect_gaps"))
        tool_results["detect_gaps"] = detect_gaps(json.dumps(matches))
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               f"Detected {len(tool_results['detect_gaps'].get('gaps', []))} gaps",
                               tool="detect_gaps"))

    gaps_result = tool_results["detect_gaps"]
    gaps = gaps_result.get("gaps", [])

    # Step 5: create_remediation_plan
    if "create_remediation_plan" not in tool_results:
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Creating remediation plan (fallback)", tool="create_remediation_plan"))
        tool_results["create_remediation_plan"] = create_remediation_plan(json.dumps(gaps))
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               f"Created {tool_results['create_remediation_plan'].get('total_tasks', 0)} tasks",
                               tool="create_remediation_plan"))

    remediation_result = tool_results["create_remediation_plan"]
    tasks = remediation_result.get("tasks", [])

    return {
        "requirements": requirements,
        "analyses": analyses,
        "matches": matches,
        "gaps": gaps,
        "tasks": tasks,
        "compliance_score": match_result.get("compliance_score", 0.0),
        "overall_status": "ACTION_REQUIRED" if gaps else "READY",
        "satisfied_count": match_result.get("satisfied_count", 0),
        "total_count": len(requirements),
    }


# ─────────────────────────────────────────────────────────────
# Error Sanitization
# ─────────────────────────────────────────────────────────────

_SENSITIVE_PATTERNS = [
    "api_key", "api-key", "apikey", "AIza", "Bearer ", "token=",
    "password", "secret", "credential", "GOOGLE_API_KEY",
    "GEMINI_API_KEY", "Authorization",
]


def _sanitize_error(error_str: str) -> str:
    """Remove sensitive data from error messages before exposing to frontend."""
    safe = error_str
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.lower() in safe.lower():
            safe = f"An internal service error occurred (contains sensitive data)."
            break
    # Truncate extremely long error messages
    if len(safe) > 500:
        safe = safe[:500] + "..."
    return safe


# ─────────────────────────────────────────────────────────────
# Verification Runner
# ─────────────────────────────────────────────────────────────

async def run_verification(
    project_id: str,
    requirements: List[dict],
    all_documents: List[dict],  # original + newly uploaded
    previous_gaps: List[dict],
    emit_event: Callable[[dict], None],
) -> dict:
    """
    Run re-verification after the user uploads corrected evidence.

    Uses a focused ADK agent run that calls analyze_documents on the
    updated document set and then verify_compliance.

    Args:
        project_id: Project ID.
        requirements: List of requirement dicts from original analysis.
        all_documents: Full updated document list (original + new uploads).
        previous_gaps: Gap list from the original analysis.
        emit_event: Callback for emitting agent events.

    Returns:
        VerificationResult dict.
    """
    current_tool = None
    try:
        emit_event(_make_event(project_id, "VERIFICATION_STARTED", "started",
                               "Re-verification started — analyzing updated documents"))

        # Re-analyze all documents (including new uploads)
        current_tool = "analyze_documents"
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Analyzing updated document set", tool="analyze_documents"))
        docs_json = json.dumps(all_documents)
        updated_analyses = analyze_documents(docs_json)
        analyses = updated_analyses.get("analyses", [])
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               f"Analyzed {len(analyses)} documents (including new uploads)",
                               tool="analyze_documents"))

        # Run verification
        current_tool = "verify_compliance"
        emit_event(_make_event(project_id, "TOOL_STARTED", "started",
                               "Verifying compliance against all requirements", tool="verify_compliance"))
        verification = verify_compliance(
            json.dumps(requirements),
            json.dumps(analyses),
            json.dumps(previous_gaps),
        )
        emit_event(_make_event(project_id, "TOOL_COMPLETED", "completed",
                               f"Verification complete: {verification.get('compliance_score', 0)}% — "
                               f"{verification.get('overall_status', 'UNKNOWN')}",
                               tool="verify_compliance"))

        emit_event(_make_event(
            project_id, "VERIFICATION_COMPLETED", "completed",
            f"Final result: {verification.get('overall_status')} ({verification.get('compliance_score')}%)"
        ))

        return verification

    except Exception as e:
        safe_message = _sanitize_error(str(e))
        emit_event(_make_event(
            project_id, "AGENT_ERROR", "error",
            f"Verification failed: {safe_message}",
            tool=current_tool,
            data={"recoverable": True, "failed_stage": current_tool or "verification_init"},
        ))
        raise

