"""
ComplyFlow — FastAPI Routes

All API endpoints. Async throughout for SSE + long-running agent tasks.
Storage-agnostic: supports SQLite (local default) and Firestore (cloud).
Integrated with append-only immutable audit logging.
Authentication and RBAC enforced on all project-scoped endpoints.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.agent.agent import _sanitize_error, run_compliance_analysis, run_verification
from app.core.config import get_settings
from app.services.audit_service import record_audit_event
from app.services.auth_service import (
    get_current_user,
    get_project_member_context,
    has_permission,
    require_permission,
    Role,
)
from app.services.document_service import DocumentService
from app.services.framework_service import FrameworkImportService, FrameworkValidationError
from app.services.storage import get_storage, StorageInterface


router = APIRouter(prefix="/api")
settings = get_settings()

# ── Service instances ────────────────────────────────────────────
_document_service = DocumentService(upload_dir=settings.upload_dir)

def _get_storage() -> StorageInterface:
    return get_storage()


def _emit_factory(project_id: str, storage: StorageInterface):
    """Returns an emit_event callback that writes to Storage AND broadcasts to SSE clients."""
    from app.services.event_broadcaster import get_broadcaster
    broadcaster = get_broadcaster()

    def emit(event: dict):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        # Non-blocking async background storage write and SSE broadcast
        loop.create_task(storage.add_event(project_id, event))
        loop.create_task(broadcaster.broadcast(project_id, event))

    return emit


# ──────────────────────────────────────────────────────────────────
# GET /api/projects — List all compliance projects
# ──────────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all compliance projects the current user is a member of."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    user_projects = await storage.list_user_projects(user_id)
    return {"projects": user_projects}


# ──────────────────────────────────────────────────────────────────
# POST /api/projects — Create a new compliance project
# ──────────────────────────────────────────────────────────────────

@router.post("/projects")

async def create_project(
    name: str = Form(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new compliance project. Creator automatically becomes ADMIN."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    project_data = {
        "name": name,
        "status": "PENDING",
        "compliance_score": None,
        "overall_status": None,
        "requirements_count": 0,
        "documents_count": 0,
        "issues_count": 0,
        "user_id": user_id,
    }
    project_id = await storage.create_project(project_data)
    # Auto-assign creator as ADMIN
    await storage.add_project_member(project_id, user_id, Role.ADMIN.value)
    project = await storage.get_project(project_id)

    # Record Audit Event with authenticated identity
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="PROJECT_CREATED",
        actor_type="AUDITOR",
        actor_id=user_id,
        summary=f"Compliance review project '{name}' initialized.",
        metadata={"project_name": name, "project_id": project_id, "user_id": user_id, "role": "ADMIN"},
    )

    return project


# ──────────────────────────────────────────────────────────────────
# DELETE /api/projects/{id} — Delete a project (ADMIN only)
# ──────────────────────────────────────────────────────────────────

@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("project:delete")),
):
    """Delete a compliance project and all associated files. Requires ADMIN role."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = ctx["user"]
    user_id = user.get("user_id", "admin")

    # Record Audit Event
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="PROJECT_DELETED",
        actor_type="AUDITOR",
        actor_id=user_id,
        summary=f"Compliance review project '{project.get('name')}' deleted.",
        metadata={"project_id": project_id, "project_name": project.get("name")},
    )

    await storage.delete_project(project_id)

    # Clean up local uploads directory
    project_upload_dir = Path(settings.upload_dir) / project_id
    if project_upload_dir.exists() and project_upload_dir.is_dir():
        import shutil
        try:
            shutil.rmtree(project_upload_dir, ignore_errors=True)
        except Exception:
            pass

    return {"status": "deleted", "project_id": project_id}


# ──────────────────────────────────────────────────────────────────
# POST /api/projects/{id}/documents — Upload files
# ──────────────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/documents")
async def upload_documents(
    project_id: str,
    requirements_file: Optional[UploadFile] = File(None),
    evidence_files: Optional[list[UploadFile]] = File(None),
    is_remediation: bool = Form(False),
    ctx: Dict[str, Any] = Depends(require_permission("documents:upload")),
):
    """
    Upload requirements document and/or evidence files.
    On is_remediation=True, adds new evidence to existing project.
    Requires: ADMIN or AUDITOR role.

    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    saved_docs = []

    # Save requirements file
    if requirements_file and not is_remediation:
        content = await requirements_file.read()
        error = _document_service.validate_file(requirements_file.filename, content)
        if error:
            raise HTTPException(status_code=400, detail=error)
        chunked = _document_service.extract_chunked_document(
            requirements_file.filename, content, "requirements_doc"
        )
        _document_service.save_upload(requirements_file.filename, content, project_id)
        now_ts = datetime.now(timezone.utc).isoformat()
        await storage.save_document_analysis(project_id, "requirements_doc", {
            "doc_id": "requirements_doc",
            "name": requirements_file.filename,
            "role": "requirements",
            "text": chunked.raw_text,
            "status": chunked.status,
            "diagnostics": chunked.diagnostics,
            "total_pages": chunked.total_pages,
            "total_chunks": chunked.total_chunks,
            "total_characters": chunked.total_characters,
            "file_size": len(content),
            "file_type": Path(requirements_file.filename).suffix.lower(),
            "chunks": [c.model_dump() for c in chunked.chunks],
            "uploaded_at": now_ts,
        })
        saved_docs.append({
            "doc_id": "requirements_doc",
            "name": requirements_file.filename,
            "role": "requirements",
            "status": chunked.status,
            "total_pages": chunked.total_pages,
            "total_chunks": chunked.total_chunks,
        })

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="DOCUMENT_UPLOADED",
            actor_type="AUDITOR",
            document_id="requirements_doc",
            summary=f"Requirements checklist '{requirements_file.filename}' uploaded.",
            metadata={"filename": requirements_file.filename, "role": "requirements", "size": len(content)},
        )

    # Save evidence files
    if evidence_files:
        for ef in evidence_files:
            if not ef.filename:
                continue
            content = await ef.read()
            error = _document_service.validate_file(ef.filename, content)
            if error:
                raise HTTPException(status_code=400, detail=f"{ef.filename}: {error}")
            doc_id = Path(ef.filename).stem.replace(" ", "_")
            chunked = _document_service.extract_chunked_document(
                ef.filename, content, doc_id
            )
            _document_service.save_upload(ef.filename, content, project_id)
            now_ts = datetime.now(timezone.utc).isoformat()
            await storage.save_document_analysis(project_id, doc_id, {
                "doc_id": doc_id,
                "name": ef.filename,
                "role": "evidence",
                "text": chunked.raw_text,
                "status": chunked.status,
                "diagnostics": chunked.diagnostics,
                "total_pages": chunked.total_pages,
                "total_chunks": chunked.total_chunks,
                "total_characters": chunked.total_characters,
                "file_size": len(content),
                "file_type": Path(ef.filename).suffix.lower(),
                "chunks": [c.model_dump() for c in chunked.chunks],
                "uploaded_at": now_ts,
            })
            saved_docs.append({
                "doc_id": doc_id,
                "name": ef.filename,
                "role": "evidence",
                "status": chunked.status,
                "total_pages": chunked.total_pages,
                "total_chunks": chunked.total_chunks,
            })

            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="DOCUMENT_UPLOADED",
                actor_type="AUDITOR",
                document_id=doc_id,
                summary=f"Evidence document '{ef.filename}' uploaded.",
                metadata={"filename": ef.filename, "role": "evidence", "size": len(content)},
            )

    return {"saved": saved_docs, "project_id": project_id}


# ──────────────────────────────────────────────────────────────────
# POST /api/projects/{id}/analyze — Start agent analysis
# ──────────────────────────────────────────────────────────────────

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
        doc_names = [d.get("name", "unknown") for d in evidence_docs]

        await storage.save_requirements(project_id, reqs)
        await storage.save_matches(project_id, matches)
        await storage.save_issues(project_id, gaps)
        await storage.save_tasks(project_id, tasks)

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
            "resolved_gaps": [],
            "remaining_gaps": [g.get("gap_id") for g in gaps if g.get("gap_id")],
            "summary": f"Initial compliance analysis completed. Score: {score}% with {len(gaps)} gap(s) identified.",
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


# ──────────────────────────────────────────────────────────────────
# GET /api/projects/{id} — Get project details
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}")
async def get_project_details(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get project overview and current compliance metrics."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs = await storage.list_documents(project_id)
    issues = await storage.get_issues(project_id)
    tasks = await storage.get_tasks(project_id)
    runs = await storage.list_verification_runs(project_id)
    overrides = await storage.list_auditor_overrides(project_id)
    matches = await storage.get_matches(project_id)

    override_map = {o["requirement_id"]: o for o in overrides}
    ai_score = project.get("compliance_score", 0.0)

    if overrides and matches:
        total = len(matches)
        adjusted_score_sum = 0.0
        for m in matches:
            req_id = m.get("requirement_id")
            effective_status = override_map[req_id]["overridden_status"] if req_id in override_map else m.get("status", "UNKNOWN")
            if effective_status == "SATISFIED":
                adjusted_score_sum += 100.0
            elif effective_status == "PARTIAL":
                adjusted_score_sum += 50.0
        auditor_adjusted_score = round(adjusted_score_sum / total, 1) if total > 0 else ai_score
    else:
        auditor_adjusted_score = ai_score

    return {
        "project": project,
        "documents": docs,
        "issues": issues,
        "tasks": tasks,
        "verification_runs_count": len(runs),
        "ai_compliance_score": ai_score,
        "auditor_adjusted_score": auditor_adjusted_score,
        "has_auditor_overrides": len(overrides) > 0,
        **project,
    }



# ──────────────────────────────────────────────────────────────────
# GET /api/projects/{id}/results — Detailed evaluation results
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/results")
async def get_project_results(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get full compliance evaluation results."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = await storage.get_results(project_id)
    overrides = await storage.list_auditor_overrides(project_id)
    matches = results.get("matches", [])
    override_map = {o["requirement_id"]: o for o in overrides}

    ai_score = project.get("compliance_score", 0.0)
    if overrides and matches:
        total = len(matches)
        adjusted_score_sum = 0.0
        for m in matches:
            req_id = m.get("requirement_id")
            effective_status = override_map[req_id]["overridden_status"] if req_id in override_map else m.get("status", "UNKNOWN")
            if effective_status == "SATISFIED":
                adjusted_score_sum += 100.0
            elif effective_status == "PARTIAL":
                adjusted_score_sum += 50.0
        auditor_adjusted_score = round(adjusted_score_sum / total, 1) if total > 0 else ai_score
    else:
        auditor_adjusted_score = ai_score

    results["ai_compliance_score"] = ai_score
    results["auditor_adjusted_score"] = auditor_adjusted_score
    results["has_auditor_overrides"] = len(overrides) > 0
    return results


# ──────────────────────────────────────────────────────────────────
# POST /api/projects/{id}/verify — Run verification
# ──────────────────────────────────────────────────────────────────

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
        doc_names = [d.get("name", "unknown") for d in all_documents]
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
            "resolved_gaps": result.get("resolved_gaps", []),
            "remaining_gaps": remaining_gap_ids,
            "summary": result.get("summary", "Verification audit completed."),
        }

        run_id = await storage.save_verification_run(project_id, verification_snapshot)

        await storage.save_matches(project_id, matches)

        score = result.get("compliance_score", 0.0)
        status = result.get("overall_status", "ACTION_REQUIRED")
        await storage.update_project(project_id, {
            "status": status,
            "compliance_score": score,
            "overall_status": status,
            "issues_count": len(remaining_gap_ids),
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


# ──────────────────────────────────────────────────────────────────
# GET /api/projects/{id}/verification-runs — List all snapshots
# ──────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────
# Report Export Endpoints (PDF & JSON)
# ──────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────
# Documents API
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/documents")
async def list_project_documents(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """List all uploaded documents with chunk counts, OCR status, and supported requirements."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs = await storage.list_documents(project_id)
    matches = await storage.get_matches(project_id)

    doc_supported_reqs: dict[str, list[dict]] = {}
    for match in matches:
        req_id = match.get("requirement_id")
        req_title = match.get("requirement_title") or req_id
        status = match.get("status")
        for ev in match.get("evidence", []):
            doc_name = ev.get("document_name")
            if doc_name:
                if doc_name not in doc_supported_reqs:
                    doc_supported_reqs[doc_name] = []
                if not any(r["requirement_id"] == req_id for r in doc_supported_reqs[doc_name]):
                    doc_supported_reqs[doc_name].append({
                        "requirement_id": req_id,
                        "title": req_title,
                        "status": status,
                        "quote": ev.get("quote"),
                        "page_number": ev.get("page_number"),
                    })

    enriched_docs = []
    for doc in docs:
        name = doc.get("name", "")
        doc_id = doc.get("doc_id", "")
        enriched_docs.append({
            "doc_id": doc_id,
            "name": name,
            "role": doc.get("role", "evidence"),
            "status": doc.get("status", "OK"),
            "diagnostics": doc.get("diagnostics", ""),
            "total_pages": doc.get("total_pages", 1),
            "total_chunks": doc.get("total_chunks", len(doc.get("chunks", []))),
            "total_characters": doc.get("total_characters", len(doc.get("text", ""))),
            "file_size": doc.get("file_size", len(doc.get("text", "").encode("utf-8"))),
            "file_type": doc.get("file_type", Path(name).suffix.lower() if name else ".txt"),
            "uploaded_at": doc.get("uploaded_at"),
            "supported_requirements": doc_supported_reqs.get(name, []),
        })

    return {"documents": enriched_docs}


@router.get("/projects/{project_id}/documents/{doc_id}")
async def get_document_details(project_id: str, doc_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get full document with all structured chunks and cited evidence excerpts."""
    safe_doc_id = Path(doc_id).name.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_doc_id:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = await storage.get_document(project_id, safe_doc_id)
    if not doc:
        all_docs = await storage.list_documents(project_id)
        for d in all_docs:
            if d.get("name") == doc_id or d.get("doc_id") == doc_id:
                doc = d
                break

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    chunks = doc.get("chunks")
    if not chunks:
        from app.services.chunking_service import get_chunking_service
        chunker = get_chunking_service()
        raw_text = doc.get("text", "")
        doc_chunks = chunker.chunk_plain_text(
            text=raw_text,
            document_name=doc.get("name", safe_doc_id),
            document_id=safe_doc_id,
            page_number=1,
        )
        chunks = [c.model_dump() for c in doc_chunks]

    matches = await storage.get_matches(project_id)
    name = doc.get("name", safe_doc_id)
    supported_reqs = []
    for match in matches:
        req_id = match.get("requirement_id")
        req_title = match.get("requirement_title") or req_id
        for ev in match.get("evidence", []):
            if ev.get("document_name") == name or ev.get("document_id") == safe_doc_id:
                supported_reqs.append({
                    "requirement_id": req_id,
                    "title": req_title,
                    "status": match.get("status"),
                    "quote": ev.get("quote"),
                    "page_number": ev.get("page_number"),
                    "section": ev.get("section"),
                    "relevance": ev.get("relevance"),
                })

    return {
        "document": {
            "doc_id": doc.get("doc_id", safe_doc_id),
            "name": name,
            "role": doc.get("role", "evidence"),
            "status": doc.get("status", "OK"),
            "diagnostics": doc.get("diagnostics", ""),
            "total_pages": doc.get("total_pages", 1),
            "total_chunks": len(chunks),
            "total_characters": doc.get("total_characters", len(doc.get("text", ""))),
            "file_size": doc.get("file_size", len(doc.get("text", "").encode("utf-8"))),
            "file_type": doc.get("file_type", Path(name).suffix.lower() if name else ".txt"),
            "uploaded_at": doc.get("uploaded_at"),
            "raw_text": doc.get("text", ""),
            "chunks": chunks,
            "supported_requirements": supported_reqs,
        }
    }


# ──────────────────────────────────────────────────────────────────
# Auditor Overrides & Notes API Endpoints
# ──────────────────────────────────────────────────────────────────

class AuditorOverridePayload(BaseModel):
    overridden_status: str
    auditor_reason: str
    auditor_note: Optional[str] = ""


class AuditorNotePayload(BaseModel):
    note_text: str


VALID_OVERRIDE_STATUSES = {"SATISFIED", "MISSING", "PARTIAL", "CONFLICT"}


@router.post("/projects/{project_id}/requirements/{requirement_id}/override")
async def save_requirement_override(
    project_id: str,
    requirement_id: str,
    payload: AuditorOverridePayload,
    ctx: Dict[str, Any] = Depends(require_permission("overrides:create")),
):
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    status_upper = payload.overridden_status.strip().upper()
    if status_upper not in VALID_OVERRIDE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid override status '{payload.overridden_status}'. Must be one of: {', '.join(sorted(VALID_OVERRIDE_STATUSES))}"
        )

    if not payload.auditor_reason or not payload.auditor_reason.strip():
        raise HTTPException(status_code=400, detail="Auditor reason is required for an override.")

    matches = await storage.get_matches(project_id)
    target_match = next((m for m in matches if m.get("requirement_id") == requirement_id), None)
    
    reqs = await storage.get_requirements(project_id)
    target_req = next((r for r in reqs if r.get("requirement_id") == requirement_id), None)

    if not target_match and not target_req:
        raise HTTPException(status_code=404, detail=f"Requirement '{requirement_id}' not found in project '{project_id}'")

    existing = await storage.get_auditor_override(project_id, requirement_id)
    original_ai_status = target_match.get("status", "UNKNOWN") if target_match else "UNKNOWN"

    override_data = {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "original_ai_status": original_ai_status,
        "overridden_status": status_upper,
        "auditor_reason": payload.auditor_reason.strip(),
        "auditor_note": payload.auditor_note.strip() if payload.auditor_note else "",
    }

    override_id = await storage.save_auditor_override(project_id, requirement_id, override_data)
    override_data["override_id"] = override_id

    event_type = "AUDITOR_OVERRIDE_UPDATED" if existing else "AUDITOR_OVERRIDE_CREATED"
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type=event_type,
        actor_type="AUDITOR",
        requirement_id=requirement_id,
        summary=f"Auditor override on {requirement_id}: status set to {status_upper}.",
        metadata={
            "requirement_id": requirement_id,
            "original_ai_status": original_ai_status,
            "overridden_status": status_upper,
            "reason": payload.auditor_reason.strip(),
        },
    )

    return {"status": "success", "override": override_data}


@router.get("/projects/{project_id}/overrides")
async def list_project_overrides(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    overrides = await storage.list_auditor_overrides(project_id)
    return {"overrides": overrides}


@router.get("/projects/{project_id}/requirements/{requirement_id}/override")
async def get_requirement_override(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    override = await storage.get_auditor_override(project_id, requirement_id)
    return {"override": override}


@router.delete("/projects/{project_id}/requirements/{requirement_id}/override")
async def delete_requirement_override(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(require_permission("overrides:revoke"))):
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    deleted = await storage.delete_auditor_override(project_id, requirement_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No active override found for requirement '{requirement_id}'")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="AUDITOR_OVERRIDE_REVOKED",
        actor_type="AUDITOR",
        requirement_id=requirement_id,
        summary=f"Auditor override revoked for requirement {requirement_id}.",
        metadata={"requirement_id": requirement_id},
    )

    return {"status": "revoked", "project_id": project_id, "requirement_id": requirement_id}


@router.post("/projects/{project_id}/requirements/{requirement_id}/notes")
async def add_auditor_note(
    project_id: str,
    requirement_id: str,
    payload: AuditorNotePayload,
    ctx: Dict[str, Any] = Depends(require_permission("notes:create")),
):
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.note_text or not payload.note_text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty.")

    note_data = {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "note_text": payload.note_text.strip(),
    }
    note_id = await storage.save_auditor_note(project_id, requirement_id, note_data)
    note_data["note_id"] = note_id

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="AUDITOR_NOTE_CREATED",
        actor_type="AUDITOR",
        requirement_id=requirement_id,
        summary=f"Auditor note added on requirement {requirement_id}.",
        metadata={"requirement_id": requirement_id, "note_id": note_id},
    )

    return {"status": "success", "note": note_data}


@router.get("/projects/{project_id}/requirements/{requirement_id}/notes")
async def list_requirement_notes(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    notes = await storage.list_auditor_notes(project_id, requirement_id)
    return {"notes": notes}


@router.delete("/projects/{project_id}/notes/{note_id}")
async def delete_auditor_note(project_id: str, note_id: str, ctx: Dict[str, Any] = Depends(require_permission("notes:delete"))):
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    deleted = await storage.delete_auditor_note(project_id, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="AUDITOR_NOTE_DELETED",
        actor_type="AUDITOR",
        summary=f"Auditor note {note_id} deleted.",
        metadata={"note_id": note_id},
    )

    return {"status": "deleted", "note_id": note_id}


# ──────────────────────────────────────────────────────────────────
# Bulk Auditor Operations
# ──────────────────────────────────────────────────────────────────

class BulkOverrideItem(BaseModel):
    requirement_id: str
    overridden_status: str


class BulkOverridePayload(BaseModel):
    requirement_ids: List[str]
    overridden_status: str
    auditor_reason: str
    auditor_note: Optional[str] = ""


class BulkNotePayload(BaseModel):
    requirement_ids: List[str]
    note_text: str


class BulkDeleteDocumentsPayload(BaseModel):
    doc_ids: List[str]


@router.post("/projects/{project_id}/bulk/overrides")
async def bulk_create_overrides(
    project_id: str,
    payload: BulkOverridePayload,
    ctx: Dict[str, Any] = Depends(require_permission("overrides:create")),
):
    """
    Create or update auditor overrides for multiple requirements atomically.
    Each requirement receives an individual override record and audit event.
    Returns per-item success/failure results — never silently discards failures.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.requirement_ids:
        raise HTTPException(status_code=400, detail="requirement_ids cannot be empty")

    if len(payload.requirement_ids) > 200:
        raise HTTPException(status_code=400, detail="Cannot bulk override more than 200 requirements at once")

    status_upper = payload.overridden_status.strip().upper()
    if status_upper not in VALID_OVERRIDE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid override status '{payload.overridden_status}'. Must be one of: {', '.join(sorted(VALID_OVERRIDE_STATUSES))}"
        )

    if not payload.auditor_reason or not payload.auditor_reason.strip():
        raise HTTPException(status_code=400, detail="Auditor reason is required for bulk override.")

    # Deduplicate requirement_ids, preserve order
    seen = set()
    unique_ids = []
    for rid in payload.requirement_ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(rid)

    # Validate all requirement IDs belong to this project
    matches = await storage.get_matches(project_id)
    reqs = await storage.get_requirements(project_id)
    valid_req_ids = {m.get("requirement_id") for m in matches} | {r.get("requirement_id") for r in reqs}
    match_map = {m.get("requirement_id"): m for m in matches}

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    results_success = []
    results_failed = []
    errors = []

    for req_id in unique_ids:
        if req_id not in valid_req_ids:
            results_failed.append(req_id)
            errors.append({"requirement_id": req_id, "error": "Requirement not found in this project"})
            continue

        try:
            existing = await storage.get_auditor_override(project_id, req_id)
            original_ai_status = match_map.get(req_id, {}).get("status", "UNKNOWN") if req_id in match_map else "UNKNOWN"

            override_data = {
                "project_id": project_id,
                "requirement_id": req_id,
                "original_ai_status": original_ai_status,
                "overridden_status": status_upper,
                "auditor_reason": payload.auditor_reason.strip(),
                "auditor_note": payload.auditor_note.strip() if payload.auditor_note else "",
            }

            override_id = await storage.save_auditor_override(project_id, req_id, override_data)
            override_data["override_id"] = override_id

            event_type = "AUDITOR_OVERRIDE_UPDATED" if existing else "AUDITOR_OVERRIDE_CREATED"
            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type=event_type,
                actor_type="AUDITOR",
                actor_id=actor_id,
                requirement_id=req_id,
                summary=f"Bulk override: {req_id} status set to {status_upper}.",
                metadata={
                    "requirement_id": req_id,
                    "original_ai_status": original_ai_status,
                    "overridden_status": status_upper,
                    "reason": payload.auditor_reason.strip(),
                    "bulk_operation": True,
                },
            )

            results_success.append({"requirement_id": req_id, "override_id": override_id})

        except Exception as exc:
            results_failed.append(req_id)
            errors.append({"requirement_id": req_id, "error": str(exc)})

    return {
        "status": "partial" if results_failed else "success",
        "overridden_status": status_upper,
        "success": results_success,
        "failed": results_failed,
        "errors": errors,
        "total_requested": len(unique_ids),
        "total_succeeded": len(results_success),
        "total_failed": len(results_failed),
    }


@router.post("/projects/{project_id}/bulk/notes")
async def bulk_create_notes(
    project_id: str,
    payload: BulkNotePayload,
    ctx: Dict[str, Any] = Depends(require_permission("notes:create")),
):
    """
    Add the same auditor note to multiple requirements.
    Each requirement gets an individual note record and audit event.
    Returns per-item results.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.requirement_ids:
        raise HTTPException(status_code=400, detail="requirement_ids cannot be empty")

    if len(payload.requirement_ids) > 200:
        raise HTTPException(status_code=400, detail="Cannot bulk-note more than 200 requirements at once")

    if not payload.note_text or not payload.note_text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty.")

    reqs = await storage.get_requirements(project_id)
    matches = await storage.get_matches(project_id)
    valid_req_ids = {r.get("requirement_id") for r in reqs} | {m.get("requirement_id") for m in matches}

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    seen = set()
    unique_ids = [rid for rid in payload.requirement_ids if rid not in seen and not seen.add(rid)]

    results_success = []
    results_failed = []
    errors = []

    for req_id in unique_ids:
        if req_id not in valid_req_ids:
            results_failed.append(req_id)
            errors.append({"requirement_id": req_id, "error": "Requirement not found in this project"})
            continue

        try:
            note_data = {
                "project_id": project_id,
                "requirement_id": req_id,
                "note_text": payload.note_text.strip(),
            }
            note_id = await storage.save_auditor_note(project_id, req_id, note_data)

            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="AUDITOR_NOTE_CREATED",
                actor_type="AUDITOR",
                actor_id=actor_id,
                requirement_id=req_id,
                summary=f"Bulk note added on requirement {req_id}.",
                metadata={"requirement_id": req_id, "note_id": note_id, "bulk_operation": True},
            )

            results_success.append({"requirement_id": req_id, "note_id": note_id})

        except Exception as exc:
            results_failed.append(req_id)
            errors.append({"requirement_id": req_id, "error": str(exc)})

    return {
        "status": "partial" if results_failed else "success",
        "success": results_success,
        "failed": results_failed,
        "errors": errors,
        "total_requested": len(unique_ids),
        "total_succeeded": len(results_success),
        "total_failed": len(results_failed),
    }


@router.post("/projects/{project_id}/bulk/documents/delete")
async def bulk_delete_documents(
    project_id: str,
    payload: BulkDeleteDocumentsPayload,
    ctx: Dict[str, Any] = Depends(require_permission("documents:delete")),
):
    """
    Delete multiple project documents by doc_id.
    Removes database records and physical files safely.
    Returns per-item results — never silently discards failures.
    Filesystem paths are never exposed in the response.
    """
    import shutil
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids cannot be empty")

    if len(payload.doc_ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot bulk-delete more than 100 documents at once")

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    seen = set()
    unique_ids = [did for did in payload.doc_ids if did not in seen and not seen.add(did)]

    results_success = []
    results_failed = []
    errors = []

    for doc_id in unique_ids:
        try:
            doc = await storage.get_document(project_id, doc_id)
            if not doc:
                # Try by name
                all_docs = await storage.list_documents(project_id)
                doc = next((d for d in all_docs if d.get("doc_id") == doc_id or d.get("name") == doc_id), None)

            if not doc:
                results_failed.append(doc_id)
                errors.append({"doc_id": doc_id, "error": "Document not found in this project"})
                continue

            doc_name = doc.get("name", doc_id)

            # Delete physical file safely
            file_path = Path(settings.upload_dir) / project_id / doc_name
            if file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                except OSError:
                    pass  # Proceed with DB deletion even if file removal fails

            # Delete from database
            deleted = await storage.delete_document(project_id, doc_id)

            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="DOCUMENT_DELETED",
                actor_type="AUDITOR",
                actor_id=actor_id,
                summary=f"Document '{doc_name}' deleted.",
                metadata={"doc_id": doc_id, "doc_name": doc_name, "bulk_operation": True},
            )

            results_success.append({"doc_id": doc_id, "name": doc_name})

        except Exception as exc:
            results_failed.append(doc_id)
            errors.append({"doc_id": doc_id, "error": str(exc)})

    return {
        "status": "partial" if results_failed else "success",
        "success": results_success,
        "failed": results_failed,
        "errors": errors,
        "total_requested": len(unique_ids),
        "total_succeeded": len(results_success),
        "total_failed": len(results_failed),
    }




@router.post("/projects/{project_id}/tasks/{task_id}/uploads")
async def upload_remediation_evidence(
    project_id: str,
    task_id: str,
    requirement_id: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    ctx: Dict[str, Any] = Depends(require_permission("remediation:upload")),
):
    """Upload a remediation evidence file and link it to a specific task + requirement."""

    from app.services.file_utils import get_extension, sanitize_filename, validate_upload
    import uuid as _uuid

    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tasks = await storage.get_tasks(project_id)
    task_ids = {t.get("task_id") for t in tasks}
    if task_id not in task_ids:
        raise HTTPException(status_code=404, detail="Task not found in this project")

    requirements = await storage.get_requirements(project_id)
    req_ids = {r.get("requirement_id") for r in requirements}
    if requirement_id not in req_ids:
        raise HTTPException(status_code=400, detail=f"requirement_id '{requirement_id}' does not belong to this project")

    file_bytes = await validate_upload(file)

    upload_id = str(_uuid.uuid4())
    safe_name = sanitize_filename(file.filename or "upload")
    ext = get_extension(safe_name)

    # Physical storage path (constructed on demand for file I/O)
    physical_path = (
        Path(settings.upload_dir) / project_id / task_id / f"{upload_id}{ext}"
    )
    physical_path.parent.mkdir(parents=True, exist_ok=True)
    physical_path.write_bytes(file_bytes)

    # Relative path only — never expose absolute server filesystem paths
    relative_path = str(Path(project_id) / task_id / f"{upload_id}{ext}")

    upload_data = {
        "upload_id": upload_id,
        "project_id": project_id,
        "task_id": task_id,
        "requirement_id": requirement_id,
        "filename": safe_name,
        "stored_filename": relative_path,
        "file_type": ext.lstrip(".") or "bin",
        "file_size": len(file_bytes),
        "upload_status": "PENDING_VERIFICATION",
        "description": (description or "").strip(),
    }

    saved_id = await storage.save_remediation_upload(project_id, task_id, upload_data)

    emit_event = _emit_factory(project_id, storage)
    emit_event({
        "type": "REMEDIATION_UPLOAD_CREATED",
        "project_id": project_id,
        "task_id": task_id,
        "upload_id": saved_id,
        "requirement_id": requirement_id,
        "filename": safe_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "summary": f"Remediation evidence uploaded: {safe_name}",
    })

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="REMEDIATION_UPLOAD_CREATED",
        actor_type="AUDITOR",
        task_id=task_id,
        requirement_id=requirement_id,
        upload_id=saved_id,
        summary=f"Remediation evidence '{safe_name}' uploaded for task {task_id}.",
        metadata={"filename": safe_name, "task_id": task_id, "requirement_id": requirement_id, "size": len(file_bytes)},
        emit_event=emit_event,
    )

    return {
        "status": "created",
        "upload": {
            "upload_id": saved_id,
            "task_id": task_id,
            "requirement_id": requirement_id,
            "filename": safe_name,
            "file_type": upload_data["file_type"],
            "file_size": len(file_bytes),
            "uploaded_at": upload_data.get("uploaded_at"),
            "upload_status": "PENDING_VERIFICATION",
            "description": upload_data["description"],
        },
    }


@router.get("/projects/{project_id}/tasks/{task_id}/uploads")
async def list_task_uploads(project_id: str, task_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """List all remediation uploads for a specific task."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    uploads = await storage.list_remediation_uploads(project_id, task_id=task_id)
    safe_uploads = [
        {k: v for k, v in u.items() if k != "stored_filename"}
        for u in uploads
    ]
    return {"uploads": safe_uploads}


@router.get("/projects/{project_id}/uploads/{upload_id}")
async def get_upload(project_id: str, upload_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get metadata for a single remediation upload."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    upload = await storage.get_remediation_upload(project_id, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    safe = {k: v for k, v in upload.items() if k != "stored_filename"}
    return {"upload": safe}


@router.delete("/projects/{project_id}/uploads/{upload_id}")
async def delete_upload(project_id: str, upload_id: str, ctx: Dict[str, Any] = Depends(require_permission("remediation:delete"))):
    """Delete a remediation upload record and its stored file."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    upload = await storage.get_remediation_upload(project_id, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    deleted = await storage.delete_remediation_upload(project_id, upload_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Upload not found or already deleted")

    emit_event = _emit_factory(project_id, storage)
    emit_event({
        "type": "REMEDIATION_UPLOAD_DELETED",
        "project_id": project_id,
        "task_id": upload.get("task_id"),
        "upload_id": upload_id,
        "requirement_id": upload.get("requirement_id"),
        "filename": upload.get("filename"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "summary": f"Remediation upload deleted: {upload.get('filename', upload_id)}",
    })

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="REMEDIATION_UPLOAD_DELETED",
        actor_type="AUDITOR",
        task_id=upload.get("task_id"),
        requirement_id=upload.get("requirement_id"),
        upload_id=upload_id,
        summary=f"Remediation upload '{upload.get('filename')}' deleted.",
        metadata={"filename": upload.get("filename"), "task_id": upload.get("task_id"), "requirement_id": upload.get("requirement_id")},
        emit_event=emit_event,
    )

    return {"status": "deleted", "upload_id": upload_id}


# ──────────────────────────────────────────────────────────────────
# Agent Events API (Polling + SSE Streaming)
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/events")
async def list_agent_events(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """List all agent execution events for a project (polling fallback for SSE)."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    events = await storage.get_events(project_id)
    return {"events": events}


@router.get("/projects/{project_id}/events/stream")
async def stream_agent_events(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """
    Server-Sent Events (SSE) stream for real-time agent execution monitoring.
    Subscribes to the EventBroadcaster and streams events as they arrive.
    Cleans up the subscription when the client disconnects.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.event_broadcaster import get_broadcaster
    broadcaster = get_broadcaster()

    queue = await broadcaster.subscribe(project_id)

    async def event_generator():
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'CONNECTED', 'project_id': project_id, 'summary': 'SSE stream connected'})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'HEARTBEAT', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await broadcaster.unsubscribe(project_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────
# Remediation Task Status API
# ──────────────────────────────────────────────────────────────────

class TaskStatusPayload(BaseModel):
    status: str


class TaskAssignPayload(BaseModel):
    assigned_to: str
    due_date: Optional[str] = None


VALID_TASK_STATUSES = {"OPEN", "RESOLVED"}


@router.put("/projects/{project_id}/tasks/{task_id}/status")
async def update_task_status(
    project_id: str,
    task_id: str,
    payload: TaskStatusPayload,
    ctx: Dict[str, Any] = Depends(require_permission("remediation:manage")),
):
    """
    Update the status of a remediation task (OPEN ↔ RESOLVED).
    Emits an immutable audit event for the transition.
    """
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    status_upper = payload.status.strip().upper()
    if status_upper not in VALID_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task status '{payload.status}'. Must be one of: {', '.join(sorted(VALID_TASK_STATUSES))}"
        )

    # Verify the task belongs to this project
    tasks = await storage.get_tasks(project_id)
    target_task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not target_task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found in this project")

    old_status = target_task.get("status", "OPEN")
    if old_status == status_upper:
        return {"status": "unchanged", "task_id": task_id, "task_status": old_status}

    await storage.update_task_status(project_id, task_id, status_upper)

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="TASK_STATUS_UPDATED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        task_id=task_id,
        requirement_id=target_task.get("related_requirement_id"),
        summary=f"Task '{task_id}' status changed from {old_status} to {status_upper}.",
        metadata={
            "task_id": task_id,
            "old_status": old_status,
            "new_status": status_upper,
            "task_title": target_task.get("title"),
        },
    )

    return {
        "status": "updated",
        "task_id": task_id,
        "old_status": old_status,
        "new_status": status_upper,
    }


@router.put("/projects/{project_id}/tasks/{task_id}/assign")
async def assign_task(
    project_id: str,
    task_id: str,
    payload: TaskAssignPayload,
    ctx: Dict[str, Any] = Depends(require_permission("remediation:manage")),
):
    """
    Assign a remediation task to a project member.
    Only ADMIN/AUDITOR roles may assign tasks.
    Emits an immutable TASK_ASSIGNED audit event.
    """
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify the task belongs to this project
    tasks = await storage.get_tasks(project_id)
    target_task = next((t for t in tasks if t.get("task_id") == task_id), None)
    if not target_task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found in this project")

    # Verify target user is an active member of this project
    member = await storage.get_project_member(project_id, payload.assigned_to)
    if not member:
        raise HTTPException(
            status_code=400,
            detail=f"User '{payload.assigned_to}' is not a member of this project",
        )
    if not member.get("is_active", True):
        raise HTTPException(
            status_code=400,
            detail=f"User '{payload.assigned_to}' is not an active member",
        )

    # Validate due_date if provided
    if payload.due_date:
        try:
            from datetime import datetime as _dt
            _dt.fromisoformat(payload.due_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid due_date '{payload.due_date}'. Must be ISO-8601.",
            )

    old_assignee = target_task.get("assigned_to")
    await storage.assign_task(
        project_id=project_id,
        task_id=task_id,
        assigned_to=payload.assigned_to,
        assigned_by=ctx.get("user", {}).get("user_id"),
        due_date=payload.due_date,
    )

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="TASK_ASSIGNED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        task_id=task_id,
        requirement_id=target_task.get("related_requirement_id"),
        summary=f"Task '{task_id}' assigned to '{payload.assigned_to}' by '{actor_id}'.",
        metadata={
            "task_id": task_id,
            "old_assignee": old_assignee,
            "new_assignee": payload.assigned_to,
            "assigned_by": actor_id,
            "due_date": payload.due_date,
            "task_title": target_task.get("title"),
        },
    )

    return {
        "status": "assigned",
        "task_id": task_id,
        "assigned_to": payload.assigned_to,
        "assigned_by": actor_id,
        "due_date": payload.due_date,
    }


# ──────────────────────────────────────────────────────────────────
# Audit Activity Timeline API
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/audit-events")
async def list_project_audit_events(
    project_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("audit:view")),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    actor_type: Optional[str] = Query(None, description="Filter by actor (SYSTEM, AI_AGENT, AUDITOR)"),
    severity: Optional[str] = Query(None, description="Filter by severity (INFO, WARNING, ERROR)"),
    requirement_id: Optional[str] = Query(None, description="Filter by requirement reference"),
    run_id: Optional[str] = Query(None, description="Filter by verification run reference"),
    from_timestamp: Optional[str] = Query(None, description="ISO timestamp floor"),
    to_timestamp: Optional[str] = Query(None, description="ISO timestamp ceiling"),
    limit: int = Query(50, ge=1, le=200, description="Max events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List immutable chronological audit events for a project (newest first).
    Append-only: events cannot be mutated or deleted.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    events = await storage.list_audit_events(
        project_id=project_id,
        event_type=event_type,
        actor_type=actor_type,
        severity=severity,
        requirement_id=requirement_id,
        run_id=run_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
        limit=limit,
        offset=offset,
    )

    total = await storage.count_audit_events(
        project_id=project_id,
        event_type=event_type,
        actor_type=actor_type,
        severity=severity,
        requirement_id=requirement_id,
        run_id=run_id,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )

    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/projects/{project_id}/audit-events/{event_id}")
async def get_single_audit_event(project_id: str, event_id: str, ctx: Dict[str, Any] = Depends(require_permission("audit:view"))):
    """Retrieve a single immutable audit event."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    event = await storage.get_audit_event(project_id, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Audit event '{event_id}' not found")

    if event.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail=f"Audit event '{event_id}' does not belong to this project")

    return {"event": event}


# ──────────────────────────────────────────────────────────────────
# Enterprise Compliance Analytics
# ──────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/analytics")
async def get_project_analytics(
    project_id: str,
    ctx: Dict[str, Any] = Depends(get_project_member_context),
):
    """
    Read-only enterprise compliance analytics for a single project.
    Aggregates score trends, requirement status, issues, tasks, audit activity,
    framework coverage, remediation effectiveness, documents, and override impact.
    """
    storage = _get_storage()
    from app.services.analytics_service import AnalyticsService
    analytics = AnalyticsService(storage=storage)

    data = await analytics.get_project_analytics(project_id)
    if not data:
        raise HTTPException(status_code=404, detail="Project not found")
    return data


@router.get("/analytics/portfolio")
async def get_portfolio_analytics(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Read-only cross-project portfolio analytics for the authenticated user.
    Returns aggregate metrics across all projects the user is a member of.
    """
    storage = _get_storage()
    from app.services.analytics_service import AnalyticsService
    analytics = AnalyticsService(storage=storage)

    data = await analytics.get_portfolio_analytics(current_user["user_id"])
    return data


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────
# Custom Compliance Framework Endpoints
# ──────────────────────────────────────────────────────────────────

class FrameworkMetaPayload(BaseModel):
    name: str
    version: str = "1.0"
    description: Optional[str] = ""
    source: Optional[str] = "Custom Import"
    status: Optional[str] = "ACTIVE"


class FrameworkConfirmImportPayload(BaseModel):
    framework: FrameworkMetaPayload
    requirements: List[Dict[str, Any]]


class FrameworkStatusPayload(BaseModel):
    status: str


@router.post("/projects/{project_id}/frameworks/preview")
async def preview_framework_import(
    project_id: str,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:import")),
):
    """
    Upload and pre-validate a custom compliance framework file (JSON, CSV, XLSX).
    Generates preview metadata and breakdown without persisting anything.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded framework file is empty")

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    try:
        preview = FrameworkImportService.parse_and_validate(
            filename=file.filename or "framework.json",
            content=content,
            default_name=name,
            default_version=version,
        )

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="FRAMEWORK_IMPORT_VALIDATED",
            actor_type="AUDITOR",
            actor_id=actor_id,
            summary=f"Framework import preview validated for '{preview['framework']['name']}' v{preview['framework']['version']} ({preview['requirement_count']} requirements).",
            metadata={
                "filename": file.filename,
                "framework_name": preview["framework"]["name"],
                "framework_version": preview["framework"]["version"],
                "requirement_count": preview["requirement_count"],
            },
        )

        return {"status": "preview_ready", **preview}

    except FrameworkValidationError as exc:
        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="FRAMEWORK_IMPORT_FAILED",
            actor_type="AUDITOR",
            actor_id=actor_id,
            severity="WARNING",
            summary=f"Framework import validation failed for '{file.filename}': {exc.message}",
            metadata={"filename": file.filename, "error": exc.message, "details_count": len(exc.details)},
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "FRAMEWORK_IMPORT_INVALID",
                "message": exc.message,
                "details": exc.details,
            },
        )


@router.post("/projects/{project_id}/frameworks/import")
async def confirm_framework_import(
    project_id: str,
    payload: FrameworkConfirmImportPayload,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:import")),
):
    """
    Explicitly confirm and atomically persist a validated custom framework.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.requirements:
        raise HTTPException(status_code=400, detail="Cannot import framework with zero requirements")

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    framework_meta = payload.framework.model_dump()
    framework_meta["created_by"] = actor_id
    framework_meta["project_id"] = project_id

    fw_id = await storage.create_framework(framework_meta, payload.requirements)

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="FRAMEWORK_IMPORTED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        summary=f"Custom compliance framework '{framework_meta['name']}' v{framework_meta['version']} imported ({len(payload.requirements)} requirements).",
        metadata={
            "framework_id": fw_id,
            "framework_name": framework_meta["name"],
            "framework_version": framework_meta["version"],
            "requirement_count": len(payload.requirements),
        },
    )

    return {
        "status": "created",
        "framework_id": fw_id,
        "framework": framework_meta,
        "requirement_count": len(payload.requirements),
    }


@router.get("/projects/{project_id}/frameworks")
async def list_available_frameworks(
    project_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:view")),
):
    """List all available global and project-scoped compliance frameworks."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    frameworks = await storage.list_frameworks(project_id)
    return {"frameworks": frameworks}


@router.get("/projects/{project_id}/frameworks/{framework_id}")
async def get_framework_details(
    project_id: str,
    framework_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:view")),
):
    """Get single framework metadata and requirement metrics."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    framework = await storage.get_framework(framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    reqs = await storage.get_framework_requirements(framework_id)

    cat_counts: Dict[str, int] = {}
    sev_counts: Dict[str, int] = {}
    for r in reqs:
        cat = r.get("category", "General")
        sev = r.get("severity", "MEDIUM")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    return {
        "framework": framework,
        "requirement_count": len(reqs),
        "category_breakdown": cat_counts,
        "severity_breakdown": sev_counts,
    }


@router.get("/projects/{project_id}/frameworks/{framework_id}/requirements")
async def list_framework_requirements(
    project_id: str,
    framework_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:view")),
):
    """Retrieve full list of requirements defined in a framework."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    framework = await storage.get_framework(framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    reqs = await storage.get_framework_requirements(framework_id)
    return {"requirements": reqs}


@router.post("/projects/{project_id}/frameworks/{framework_id}/activate")
async def update_framework_status(
    project_id: str,
    framework_id: str,
    payload: FrameworkStatusPayload,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:manage")),
):
    """Activate or deactivate a framework status."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    framework = await storage.get_framework(framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    status_upper = payload.status.strip().upper()
    if status_upper not in {"ACTIVE", "INACTIVE", "DRAFT"}:
        raise HTTPException(status_code=400, detail="Status must be one of: ACTIVE, INACTIVE, DRAFT")

    await storage.update_framework_status(framework_id, status_upper)

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    event_type = "FRAMEWORK_ACTIVATED" if status_upper == "ACTIVE" else "FRAMEWORK_DEACTIVATED"
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type=event_type,
        actor_type="AUDITOR",
        actor_id=actor_id,
        summary=f"Framework '{framework['name']}' v{framework['version']} status changed to {status_upper}.",
        metadata={"framework_id": framework_id, "status": status_upper},
    )

    return {"status": "updated", "framework_id": framework_id, "new_status": status_upper}


@router.post("/projects/{project_id}/frameworks/{framework_id}/apply")
async def apply_framework_to_project(
    project_id: str,
    framework_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:apply")),
):
    """
    Apply a framework's requirements to the project workspace.
    Saves requirements to the project and records framework identity in project metadata.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    framework = await storage.get_framework(framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    if framework.get("status") == "INACTIVE":
        raise HTTPException(status_code=400, detail="Cannot apply an INACTIVE framework. Activate it first.")

    reqs = await storage.get_framework_requirements(framework_id)
    if not reqs:
        raise HTTPException(status_code=400, detail="Framework contains zero requirement definitions")

    # Map framework requirements to project requirements
    project_reqs = []
    for r in reqs:
        project_reqs.append({
            "requirement_id": r["requirement_id"],
            "title": r["title"],
            "description": r["description"],
            "required_evidence": r.get("guidance") or r.get("required_evidence") or "",
            "priority": r.get("priority") or r.get("severity") or "MEDIUM",
            "source_reference": r.get("source_reference") or "",
            "category": r.get("category") or "General",
            "framework_id": framework_id,
            "framework_name": framework["name"],
            "framework_version": framework["version"],
        })

    # Save to project requirements
    await storage.save_requirements(project_id, project_reqs)

    # Update project metadata
    project_meta = project.get("metadata_json") or "{}"
    if isinstance(project_meta, str):
        try:
            meta_dict = json.loads(project_meta)
        except Exception:
            meta_dict = {}
    else:
        meta_dict = dict(project_meta)

    meta_dict["active_framework_id"] = framework_id
    meta_dict["active_framework_name"] = framework["name"]
    meta_dict["active_framework_version"] = framework["version"]

    await storage.update_project(project_id, {
        "requirements_count": len(project_reqs),
        "metadata_json": json.dumps(meta_dict),
    })

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="FRAMEWORK_APPLIED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        summary=f"Framework '{framework['name']}' v{framework['version']} ({len(project_reqs)} requirements) applied to project workspace.",
        metadata={
            "framework_id": framework_id,
            "framework_name": framework["name"],
            "framework_version": framework["version"],
            "requirement_count": len(project_reqs),
        },
    )

    return {
        "status": "applied",
        "project_id": project_id,
        "framework_id": framework_id,
        "framework_name": framework["name"],
        "framework_version": framework["version"],
        "requirements_count": len(project_reqs),
    }


@router.delete("/projects/{project_id}/frameworks/{framework_id}")
async def delete_framework(
    project_id: str,
    framework_id: str,
    ctx: Dict[str, Any] = Depends(require_permission("frameworks:manage")),
):
    """
    Delete an unused draft or custom framework.
    Guarantees historical snapshot immutability by rejecting deletion if referenced in completed runs.
    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    framework = await storage.get_framework(framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")

    # Prevent deletion if referenced in historical verification runs
    if await storage.is_framework_referenced_in_runs(framework_id):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete framework '{framework['name']}' because it is referenced in immutable historical verification runs."
        )

    deleted = await storage.delete_framework(framework_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Framework not found or already deleted")

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="FRAMEWORK_DELETED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        summary=f"Framework '{framework['name']}' v{framework['version']} deleted.",
        metadata={"framework_id": framework_id, "framework_name": framework["name"]},
    )

    return {"status": "deleted", "framework_id": framework_id}

