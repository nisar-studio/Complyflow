"""
ComplyFlow — Project Routes

Provides:
  GET    /api/projects                    (list user's projects)
  POST   /api/projects                    (create project)
  DELETE /api/projects/{project_id}       (delete project, ADMIN only)
  GET    /api/projects/{project_id}       (project details)
  GET    /api/projects/{project_id}/results (evaluation results)
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, HTTPException

from app.api._shared import _get_storage, settings
from app.services.audit_service import record_audit_event
from app.services.auth_service import (
    Role,
    get_current_user,
    get_project_member_context,
    require_permission,
)

router = APIRouter()


@router.get("/projects")
async def list_projects(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all compliance projects the current user is a member of."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    user_projects = await storage.list_user_projects(user_id)
    return {"projects": user_projects}


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
        try:
            shutil.rmtree(project_upload_dir, ignore_errors=True)
        except Exception:
            pass

    return {"status": "deleted", "project_id": project_id}


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
