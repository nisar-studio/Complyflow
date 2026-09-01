"""
ComplyFlow — Auditor Override & Notes Routes

Provides:
  POST   /api/projects/{id}/requirements/{rid}/override   (create/update)
  GET    /api/projects/{id}/overrides                      (list all)
  GET    /api/projects/{id}/requirements/{rid}/override    (get single)
  DELETE /api/projects/{id}/requirements/{rid}/override    (revoke)
  POST   /api/projects/{id}/requirements/{rid}/notes       (add note)
  GET    /api/projects/{id}/requirements/{rid}/notes       (list notes)
  DELETE /api/projects/{id}/notes/{note_id}                (delete note)
  POST   /api/projects/{id}/bulk/overrides                 (bulk overrides)
  POST   /api/projects/{id}/bulk/notes                     (bulk notes)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api._shared import _get_storage
from app.services.auth_service import get_project_member_context, require_permission
from app.services.audit_service import record_audit_event

router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────

VALID_OVERRIDE_STATUSES = {"SATISFIED", "MISSING", "PARTIAL", "CONFLICT"}


# ── Models ─────────────────────────────────────────────────────────

class AuditorOverridePayload(BaseModel):
    overridden_status: str
    auditor_reason: str
    auditor_note: Optional[str] = ""


class AuditorNotePayload(BaseModel):
    note_text: str


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


# ── Single Override Endpoints ──────────────────────────────────────

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


# ── Notes Endpoints ────────────────────────────────────────────────

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


# ── Bulk Override & Note Endpoints ─────────────────────────────────

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
