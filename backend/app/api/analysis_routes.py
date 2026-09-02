"""
ComplyFlow — Analysis & Verification Routes

Provides:
  POST /api/projects/{id}/analyze                          (start analysis)
  POST /api/projects/{id}/verify                           (run verification)
  GET  /api/projects/{id}/verification-runs                (list runs)
  GET  /api/projects/{id}/verification-runs/{run_id}       (get run)
  GET  /api/projects/{id}/verification-runs/{run_id}/delta (run delta)
  GET  /api/projects/{id}/verification-delta               (custom delta)
  GET  /api/projects/{id}/verification-runs/{run_id}/report.pdf
  GET  /api/projects/{id}/verification-runs/{run_id}/report.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.agent.agent import _sanitize_error, run_compliance_analysis, run_verification
from app.services.summary_service import generate_executive_summary
from app.api._shared import _emit_factory, _get_storage
from app.services.document_service import DocumentService
from app.core.config import get_settings
from app.services.auth_service import (
    get_project_member_context,
    require_permission,
)
from app.services.audit_service import record_audit_event
from app.services.storage import StorageInterface

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────

async def _load_document_text(storage: StorageInterface, project_id: str, doc_id: str) -> Optional[str]:
    """Load extracted text for a specific document."""
    doc = await storage.get_document(project_id, doc_id)
    if doc:
        return doc.get("text", "")
    return None


async def _load_evidence_documents(storage: StorageInterface, project_id: str) -> list[dict]:
    """Load all evidence documents (role=evidence) for a project."""
    docs = await storage.list_documents(project_id, role="evidence")
    return [
        {"name": d.get("name", "unknown"), "text": d.get("text", "")}
        for d in docs
        if d.get("text", "").strip()
    ]


async def _check_evidence_expiration(
    storage: StorageInterface,
    project_id: str,
    emit_event=None,
) -> tuple[list[dict], list[dict]]:
    """Check all current evidence documents for expiration.
    
    Returns:
        (expiration_gaps, expiration_tasks) — deterministic gaps/tasks for
        expired evidence, using existing issue/task persistence.
    
    This function:
    1. Queries ALL current evidence documents via list_evidence_lifecycle
       (which correctly resolves doc_id from the documents table)
    2. Creates deterministic expired_evidence gaps for expired docs
    3. Creates deterministic remediation tasks for expired docs
    4. Generates EVIDENCE_EXPIRED / EVIDENCE_EXPIRING_SOON notifications
    
    Uses ON CONFLICT DO UPDATE so repeated analysis does not duplicate.
    """
    now = datetime.now(timezone.utc)
    threshold_days = 30
    expiration_gaps = []
    expiration_tasks = []
    
    # Use list_evidence_lifecycle which correctly queries the documents table
    # and resolves doc_id, name, and computes expiration status dynamically
    lifecycle = await storage.list_evidence_lifecycle(project_id)
    
    for item in lifecycle:
        doc_id = item.get("doc_id", "")
        doc_name = item.get("name", doc_id)
        expires_at = item.get("expires_at")
        version_number = item.get("current_version", 1)
        status = item.get("status", "NO_EXPIRATION")
        
        if status == "EXPIRED":
            # Create deterministic gap and task
            gap_id = f"expired_evidence:{project_id}:{doc_id}:v{version_number}"
            task_id = f"expired_evidence:{project_id}:{doc_id}:v{version_number}"
            
            gap = {
                "gap_id": gap_id,
                "gap_type": "expired_evidence",
                "severity": "HIGH",
                "description": f"Evidence '{doc_name}' (v{version_number}) has expired.",
                "document_id": doc_id,
                "document_name": doc_name,
                "version_number": version_number,
                "expires_at": expires_at,
            }
            expiration_gaps.append(gap)
            
            task = {
                "task_id": task_id,
                "title": f"Renew expired evidence: {doc_name}",
                "severity": "HIGH",
                "required_action": f"Upload a renewed version of '{doc_name}' to restore compliance.",
                "status": "OPEN",
                "related_gap_id": gap_id,
                "document_id": doc_id,
                "document_name": doc_name,
                "version_number": version_number,
                "expires_at": expires_at,
            }
            expiration_tasks.append(task)
            
            # Generate notification for all project members
            members = await storage.list_project_members(project_id)
            for member in members:
                member_id = member.get("user_id")
                if member_id:
                    await storage.save_notification(
                        user_id=member_id,
                        notification={
                            "notification_id": f"evidence_expired:{project_id}:{doc_id}:v{version_number}:{member_id}",
                            "project_id": project_id,
                            "type": "EVIDENCE_EXPIRED",
                            "title": "Evidence Expired",
                            "message": f"Evidence '{doc_name}' (v{version_number}) has expired.",
                            "metadata": {
                                "document_id": doc_id,
                                "document_name": doc_name,
                                "version_number": version_number,
                                "expires_at": expires_at,
                            },
                        },
                    )
            
            # Record audit event
            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="EVIDENCE_EXPIRED",
                actor_type="SYSTEM",
                document_id=doc_id,
                summary=f"Evidence '{doc_name}' (v{version_number}) has expired.",
                metadata={"document_id": doc_id, "version_number": version_number, "expires_at": expires_at},
                emit_event=emit_event,
            )
        
        elif status == "EXPIRING_SOON":
            # Create notification only (no gap/task yet)
            members = await storage.list_project_members(project_id)
            for member in members:
                member_id = member.get("user_id")
                if member_id:
                    await storage.save_notification(
                        user_id=member_id,
                        notification={
                            "notification_id": f"evidence_expiring:{project_id}:{doc_id}:v{version_number}:{member_id}",
                            "project_id": project_id,
                            "type": "EVIDENCE_EXPIRING_SOON",
                            "title": "Evidence Expiring Soon",
                            "message": f"Evidence '{doc_name}' (v{version_number}) expires on {expires_at}.",
                            "metadata": {
                                "document_id": doc_id,
                                "document_name": doc_name,
                                "version_number": version_number,
                                "expires_at": expires_at,
                            },
                        },
                    )
    
    # Persist expiration gaps and tasks using existing ON CONFLICT DO UPDATE
    if expiration_gaps:
        await storage.save_issues(project_id, expiration_gaps)
    if expiration_tasks:
        await storage.save_tasks(project_id, expiration_tasks)
    
    return expiration_gaps, expiration_tasks


# ── Analysis ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/analyze")
async def analyze_project(project_id: str, background_tasks: BackgroundTasks, ctx: Dict[str, Any] = Depends(require_permission("analysis:run"))):
    """
    Start the full compliance analysis workflow via ADK agent.
    Returns immediately; analysis runs in background.
    Monitor progress via GET /api/projects/{id}/events/stream
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load requirements text
    req_doc = await _load_document_text(storage, project_id, "requirements_doc")
    if not req_doc:
        raise HTTPException(
            status_code=400,
            detail="No requirements document found. Upload a requirements document first."
        )

    # Load evidence documents
    evidence_docs = await _load_evidence_documents(storage, project_id)
    if not evidence_docs:
        raise HTTPException(
            status_code=400,
            detail="No evidence documents found. Upload at least one evidence document."
        )

    await storage.update_project(project_id, {"status": "ANALYZING"})

    # Run analysis in background
    background_tasks.add_task(
        _run_analysis_task, project_id, req_doc, evidence_docs
    )

    return {"status": "ANALYZING", "project_id": project_id,
            "message": "Analysis started. Monitor progress via /events/stream"}


async def _run_analysis_task(
    project_id: str,
    requirements_text: str,
    evidence_docs: list[dict],
):
    """Background task: runs ADK agent and persists results."""
    storage = _get_storage()
    emit_event = _emit_factory(project_id, storage)

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="ANALYSIS_STARTED",
        actor_type="AI_AGENT",
        summary="Autonomous AI compliance analysis initiated.",
        emit_event=emit_event,
    )

    try:
        results = await run_compliance_analysis(
            project_id=project_id,
            requirements_text=requirements_text,
            documents=evidence_docs,
            emit_event=emit_event,
        )

        # Persist structured results to Storage
        reqs = results.get("requirements", [])
        matches = results.get("matches", [])
        gaps = results.get("gaps", [])
        tasks = results.get("tasks", [])
        
        # Build document references with version provenance
        doc_names = []
        doc_versions = []
        for d in evidence_docs:
            doc_name = d.get("name", "unknown")
            doc_id = d.get("doc_id", doc_name.split(".")[0] if "." in doc_name else doc_name)
            doc_ver = d.get("version_number", 1)
            doc_names.append(doc_name)
            doc_versions.append({
                "document_name": doc_name,
                "document_id": doc_id,
                "version_number": doc_ver,
            })

        await storage.save_requirements(project_id, reqs)
        await storage.save_matches(project_id, matches)
        await storage.save_issues(project_id, gaps)
        await storage.save_tasks(project_id, tasks)

        # Check all evidence documents for expiration (independent of AI matching)
        expiration_gaps, expiration_tasks = await _check_evidence_expiration(
            storage, project_id, emit_event=emit_event
        )
        gaps.extend(expiration_gaps)
        tasks.extend(expiration_tasks)

        # Record gap and conflict events
        for m in matches:
            req_id = m.get("requirement_id")
            if m.get("status") == "CONFLICT":
                await record_audit_event(
                    storage=storage,
                    project_id=project_id,
                    event_type="REQUIREMENT_CONFLICT_DETECTED",
                    actor_type="AI_AGENT",
                    requirement_id=req_id,
                    severity="WARNING",
                    summary=f"Fact-level document contradiction detected on requirement {req_id}.",
                    metadata={"requirement_id": req_id, "title": m.get("requirement_title")},
                    emit_event=emit_event,
                )
            elif m.get("status") == "MISSING":
                await record_audit_event(
                    storage=storage,
                    project_id=project_id,
                    event_type="REQUIREMENT_GAP_DETECTED",
                    actor_type="AI_AGENT",
                    requirement_id=req_id,
                    severity="WARNING",
                    summary=f"Missing evidence gap detected on requirement {req_id}.",
                    metadata={"requirement_id": req_id, "title": m.get("requirement_title")},
                    emit_event=emit_event,
                )

        for t in tasks:
            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="REMEDIATION_TASK_CREATED",
                actor_type="AI_AGENT",
                task_id=t.get("task_id"),
                requirement_id=t.get("related_requirement_id"),
                summary=f"Remediation task created: {t.get('title')}",
                metadata={"task_id": t.get("task_id"), "severity": t.get("severity")},
                emit_event=emit_event,
            )

        # Update project summary
        score = results.get("compliance_score", 0.0)
        status = results.get("overall_status", "ACTION_REQUIRED")
        await storage.update_project(project_id, {
            "status": status,
            "compliance_score": score,
            "overall_status": status,
            "requirements_count": results.get("total_count", len(reqs)),
            "issues_count": len(gaps),
        })

        # Extract framework metadata from project
        proj_obj = await storage.get_project(project_id)
        proj_meta = {}
        if proj_obj and proj_obj.get("metadata_json"):
            try:
                proj_meta = json.loads(proj_obj["metadata_json"]) if isinstance(proj_obj["metadata_json"], str) else proj_obj["metadata_json"]
            except Exception:
                proj_meta = {}

        fw_id = proj_meta.get("active_framework_id") or (reqs[0].get("framework_id") if reqs else None)
        fw_name = proj_meta.get("active_framework_name") or (reqs[0].get("framework_name") if reqs else "Built-in Framework")
        fw_ver = proj_meta.get("active_framework_version") or (reqs[0].get("framework_version") if reqs else "1.0")

        # Generate executive summary BEFORE snapshot finalization
        executive_summary = None
        try:
            proj_obj_for_name = await storage.get_project(project_id)
            proj_name = (proj_obj_for_name or {}).get("name", project_id)
            executive_summary = generate_executive_summary(
                verification_result=results,
                project_name=proj_name,
            )
        except Exception as summary_err:
            safe_summary_err = _sanitize_error(str(summary_err))
            logger.warning(f"Executive summary generation failed for {project_id}: {safe_summary_err}")
            executive_summary = None

        # Save immutable Run 1 Snapshot
        initial_snapshot = {
            "trigger": "INITIAL_ANALYSIS",
            "framework_id": fw_id,
            "framework_name": fw_name,
            "framework_version": fw_ver,
            "overall_status": status,
            "compliance_score": score,
            "satisfied_count": results.get("satisfied_count", 0),
            "total_count": len(reqs),
            "requirements_snapshot": reqs,
            "matches_snapshot": matches,
            "issues_snapshot": gaps,
            "tasks_snapshot": tasks,
            "documents_used": doc_names,
            "document_versions": doc_versions,
            "resolved_gaps": [],
            "remaining_gaps": [g.get("gap_id") for g in gaps if g.get("gap_id")],
            "summary": f"Initial compliance analysis completed. Score: {score}% with {len(gaps)} gap(s) identified.",
            "executive_summary": executive_summary,
        }
        await storage.save_verification_run(project_id, initial_snapshot)


        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="ANALYSIS_COMPLETED",
            actor_type="AI_AGENT",
            run_id="run_1",
            summary=f"Compliance analysis completed. Verdict: {status} ({score}%).",
            metadata={"compliance_score": score, "overall_status": status, "run_id": "run_1"},
            emit_event=emit_event,
        )

        # Record executive summary generation audit event
        if executive_summary is not None:
            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="SUMMARY_GENERATED",
                actor_type="AI_AGENT",
                run_id="run_1",
                summary="Executive summary generated for initial analysis.",
                metadata={"run_id": "run_1", "has_summary": True},
                emit_event=emit_event,
            )

    except Exception as e:
        safe_msg = _sanitize_error(str(e))
        error_event = {
            "project_id": project_id,
            "type": "AGENT_ERROR",
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Analysis failed: {safe_msg}",
            "tool": None,
            "data": {"recoverable": True, "failed_stage": "analysis_task"},
        }
        emit_event(error_event)
        await storage.update_project(project_id, {"status": "ERROR"})

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="ANALYSIS_FAILED",
            actor_type="AI_AGENT",
            severity="ERROR",
            summary=f"Analysis failed: {safe_msg}",
            emit_event=emit_event,
        )


# ── Verification ───────────────────────────────────────────────────

@router.post("/projects/{project_id}/verify")
async def verify_project(project_id: str, background_tasks: BackgroundTasks, ctx: Dict[str, Any] = Depends(require_permission("verification:run"))):
    """Start re-verification after user uploads corrected evidence."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    requirements = await storage.get_requirements(project_id)
    if not requirements:
        raise HTTPException(status_code=400, detail="No requirements found. Run analysis first.")

    previous_gaps = await storage.get_issues(project_id)
    all_documents = await _load_evidence_documents(storage, project_id)

    await storage.update_project(project_id, {"status": "ANALYZING"})

    background_tasks.add_task(
        _run_verification_task, project_id, requirements, all_documents, previous_gaps
    )

    return {"status": "VERIFYING", "project_id": project_id,
            "message": "Verification started. Monitor progress via /events/stream"}


async def _run_verification_task(
    project_id: str,
    requirements: list[dict],
    all_documents: list[dict],
    previous_gaps: list[dict],
):
    """Background task: run verification and persist results."""
    storage = _get_storage()
    emit_event = _emit_factory(project_id, storage)

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="VERIFICATION_STARTED",
        actor_type="AI_AGENT",
        summary="Post-remediation verification audit started.",
        emit_event=emit_event,
    )

    try:
        result = await run_verification(
            project_id=project_id,
            requirements=requirements,
            all_documents=all_documents,
            previous_gaps=previous_gaps,
            emit_event=emit_event,
        )

        matches = result.get("matches", [])
        remaining_gap_ids = result.get("remaining_gaps", [])
        all_gaps = await storage.get_issues(project_id)
        open_gaps = [g for g in all_gaps if g.get("gap_id") in remaining_gap_ids]
        tasks = await storage.get_tasks(project_id)
        
        # Build document references with version provenance
        doc_names = []
        doc_versions = []
        for d in all_documents:
            doc_name = d.get("name", "unknown")
            doc_id = d.get("doc_id", doc_name.split(".")[0] if "." in doc_name else doc_name)
            doc_ver = d.get("version_number", 1)
            doc_names.append(doc_name)
            doc_versions.append({
                "document_name": doc_name,
                "document_id": doc_id,
                "version_number": doc_ver,
            })
        # Extract framework metadata from project
        proj_obj = await storage.get_project(project_id)
        proj_meta = {}
        if proj_obj and proj_obj.get("metadata_json"):
            try:
                proj_meta = json.loads(proj_obj["metadata_json"]) if isinstance(proj_obj["metadata_json"], str) else proj_obj["metadata_json"]
            except Exception:
                proj_meta = {}

        fw_id = proj_meta.get("active_framework_id") or (requirements[0].get("framework_id") if requirements else None)
        fw_name = proj_meta.get("active_framework_name") or (requirements[0].get("framework_name") if requirements else "Built-in Framework")
        fw_ver = proj_meta.get("active_framework_version") or (requirements[0].get("framework_version") if requirements else "1.0")

        # Generate executive summary BEFORE snapshot finalization
        executive_summary = None
        try:
            proj_name = (await storage.get_project(project_id) or {}).get("name", project_id)
            executive_summary = generate_executive_summary(
                verification_result=result,
                project_name=proj_name,
            )
        except Exception as summary_err:
            safe_summary_err = _sanitize_error(str(summary_err))
            logger.warning(f"Executive summary generation failed for {project_id}: {safe_summary_err}")
            executive_summary = None

        verification_snapshot = {
            "trigger": "REMEDIATION_VERIFICATION",
            "framework_id": fw_id,
            "framework_name": fw_name,
            "framework_version": fw_ver,
            "overall_status": result.get("overall_status", "ACTION_REQUIRED"),
            "compliance_score": result.get("compliance_score", 0.0),
            "satisfied_count": result.get("satisfied_count", 0),
            "total_count": result.get("total_count", len(requirements)),
            "requirements_snapshot": requirements,
            "matches_snapshot": matches,
            "issues_snapshot": open_gaps,
            "tasks_snapshot": tasks,
            "documents_used": doc_names,
            "document_versions": doc_versions,
            "resolved_gaps": result.get("resolved_gaps", []),
            "remaining_gaps": remaining_gap_ids,
            "summary": result.get("summary", "Verification audit completed."),
            "executive_summary": executive_summary,
        }

        run_id = await storage.save_verification_run(project_id, verification_snapshot)

        await storage.save_matches(project_id, matches)

        # Check all evidence documents for expiration (independent of AI matching)
        expiration_gaps, expiration_tasks = await _check_evidence_expiration(
            storage, project_id, emit_event=emit_event
        )

        score = result.get("compliance_score", 0.0)
        status = result.get("overall_status", "ACTION_REQUIRED")
        await storage.update_project(project_id, {
            "status": status,
            "compliance_score": score,
            "overall_status": status,
            "issues_count": len(remaining_gap_ids) + len(expiration_gaps),
        })

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="VERIFICATION_COMPLETED",
            actor_type="AI_AGENT",
            run_id=run_id,
            summary=f"Verification completed. Verdict: {status} ({score}%).",
            metadata={"compliance_score": score, "overall_status": status, "run_id": run_id},
            emit_event=emit_event,
        )

        # Record executive summary generation audit event
        if executive_summary is not None:
            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="SUMMARY_GENERATED",
                actor_type="AI_AGENT",
                run_id=run_id,
                summary=f"Executive summary generated for verification run {run_id}.",
                metadata={"run_id": run_id, "has_summary": True},
                emit_event=emit_event,
            )

        # Generate notifications for all project members
        members = await storage.list_project_members(project_id)
        for member in members:
            member_id = member.get("user_id")
            if member_id:
                await storage.save_notification(
                    user_id=member_id,
                    notification={
                        "project_id": project_id,
                        "type": "VERIFICATION_COMPLETED",
                        "title": "Verification Completed",
                        "message": f"Verification completed. Score: {score}%, Status: {status}.",
                        "metadata": {
                            "run_id": run_id,
                            "compliance_score": score,
                            "overall_status": status,
                        },
                    },
                )

    except Exception as e:
        safe_msg = _sanitize_error(str(e))
        error_event = {
            "project_id": project_id,
            "type": "AGENT_ERROR",
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"Verification failed: {safe_msg}",
            "tool": None,
            "data": {"recoverable": True, "failed_stage": "verification_task"},
        }
        emit_event(error_event)
        await storage.update_project(project_id, {"status": "ERROR"})

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="VERIFICATION_FAILED",
            actor_type="AI_AGENT",
            severity="ERROR",
            summary=f"Verification failed: {safe_msg}",
            emit_event=emit_event,
        )


# ── Verification Runs / Delta / Reports ────────────────────────────

@router.get("/projects/{project_id}/verification-runs")
async def list_verification_runs(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get all immutable historical verification runs for a project."""
    storage = _get_storage()
    runs = await storage.list_verification_runs(project_id)
    return {"runs": runs}


@router.get("/projects/{project_id}/verification-runs/{run_id}")
async def get_verification_run_snapshot(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get a specific historical verification run snapshot."""
    storage = _get_storage()
    run = await storage.get_verification_run(project_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Verification run '{run_id}' not found")
    return {"run": run}


@router.get("/projects/{project_id}/verification-runs/{run_id}/delta")
async def get_run_delta_from_predecessor(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get comparative delta for a run compared against its immediate predecessor."""
    storage = _get_storage()
    from app.services.delta_service import get_delta_engine
    delta_engine = get_delta_engine()

    runs = await storage.list_verification_runs(project_id)
    target_idx = None
    for idx, r in enumerate(runs):
        if r.get("run_id") == run_id or str(r.get("run_number")) == str(run_id):
            target_idx = idx
            break

    if target_idx is None:
        raise HTTPException(status_code=404, detail=f"Verification run '{run_id}' not found")

    target_run = runs[target_idx]
    if target_idx == 0:
        empty_run = {
            "run_id": "run_0",
            "run_number": 0,
            "compliance_score": 0.0,
            "overall_status": "PENDING",
            "matches_snapshot": [],
            "issues_snapshot": [],
        }
        delta = delta_engine.calculate_delta(empty_run, target_run)
    else:
        prev_run = runs[target_idx - 1]
        delta = delta_engine.calculate_delta(prev_run, target_run)

    return delta.model_dump()


@router.get("/projects/{project_id}/verification-delta")
async def get_custom_verification_delta(
    project_id: str,
    ctx: Dict[str, Any] = Depends(get_project_member_context),
    from_run: str = Query(..., description="Run ID or run number for baseline run"),
    to_run: str = Query(..., description="Run ID or run number for comparison run"),
):
    """Calculate comparative delta between any two arbitrary verification runs."""
    storage = _get_storage()
    from app.services.delta_service import get_delta_engine
    delta_engine = get_delta_engine()

    run_a = await storage.get_verification_run(project_id, from_run)
    if not run_a:
        raise HTTPException(status_code=404, detail=f"Baseline verification run '{from_run}' not found")

    run_b = await storage.get_verification_run(project_id, to_run)
    if not run_b:
        raise HTTPException(status_code=404, detail=f"Comparison verification run '{to_run}' not found")

    delta = delta_engine.calculate_delta(run_a, run_b)
    return delta.model_dump()


@router.get("/projects/{project_id}/verification-runs/{run_id}/report.pdf")
async def export_verification_run_pdf(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(require_permission("reports:export"))):
    """Export a professional, point-in-time enterprise compliance audit report as a PDF."""
    storage = _get_storage()
    from app.services.report_service import ReportService
    report_service = ReportService(storage=storage)
    report_data = await report_service.build_report_data(project_id, run_id)
    pdf_bytes = report_service.generate_pdf(report_data)

    safe_pid = project_id.replace("/", "_").replace("\\", "_")
    safe_rid = run_id.replace("/", "_").replace("\\", "_")
    filename = f"compliance_report_{safe_pid}_{safe_rid}.pdf"

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="REPORT_EXPORTED",
        actor_type="AUDITOR",
        run_id=run_id,
        summary=f"Point-in-time compliance report PDF exported for run {run_id}.",
        metadata={"format": "pdf", "run_id": run_id, "filename": filename},
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/projects/{project_id}/verification-runs/{run_id}/report.json")
async def export_verification_run_json(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(require_permission("reports:export"))):
    """Export structured point-in-time compliance audit data as JSON."""
    storage = _get_storage()
    from app.services.report_service import ReportService
    report_service = ReportService(storage=storage)
    report_data = await report_service.build_report_data(project_id, run_id)


    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="REPORT_EXPORTED",
        actor_type="AUDITOR",
        run_id=run_id,
        summary=f"Structured compliance audit JSON exported for run {run_id}.",
        metadata={"format": "json", "run_id": run_id},
    )

    return report_data
