"""
ComplyFlow — Framework Routes

Provides:
  POST   /api/projects/{id}/frameworks/preview      (preview import)
  POST   /api/projects/{id}/frameworks/import       (confirm import)
  GET    /api/projects/{id}/frameworks              (list)
  GET    /api/projects/{id}/frameworks/{fid}        (details)
  GET    /api/projects/{id}/frameworks/{fid}/requirements (list reqs)
  POST   /api/projects/{id}/frameworks/{fid}/activate  (activate/deactivate)
  POST   /api/projects/{id}/frameworks/{fid}/apply     (apply to project)
  DELETE /api/projects/{id}/frameworks/{fid}        (delete)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api._shared import _get_storage
from app.services.auth_service import require_permission
from app.services.audit_service import record_audit_event
from app.services.framework_service import FrameworkImportService, FrameworkValidationError

router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────

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


# ── Framework Endpoints ────────────────────────────────────────────

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
