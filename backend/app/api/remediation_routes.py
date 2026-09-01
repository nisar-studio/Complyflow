"""
ComplyFlow — Remediation Routes

Provides:
  PUT    /api/projects/{id}/tasks/{tid}/status      (update status)
  PUT    /api/projects/{id}/tasks/{tid}/assign      (assign task)
  PUT    /api/projects/{id}/tasks/{tid}/due-date    (set/clear due date)
  POST   /api/projects/{id}/bulk/tasks/status       (bulk status)
  POST   /api/projects/{id}/bulk/tasks/assign       (bulk assign)
  POST   /api/projects/{id}/tasks/{tid}/uploads     (upload evidence)
  GET    /api/projects/{id}/tasks/{tid}/uploads     (list uploads)
  GET    /api/projects/{id}/uploads/{uid}           (get upload)
  DELETE /api/projects/{id}/uploads/{uid}           (delete upload)
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api._shared import _emit_factory, _get_storage, settings
from app.services.auth_service import get_project_member_context, require_permission
from app.services.audit_service import record_audit_event

router = APIRouter()


# ── Models ─────────────────────────────────────────────────────────

class TaskStatusPayload(BaseModel):
    status: str


class TaskAssignPayload(BaseModel):
    assigned_to: str
    due_date: Optional[str] = None


class TaskDueDatePayload(BaseModel):
    due_date: Optional[str] = None  # null to clear


VALID_TASK_STATUSES = {"OPEN", "RESOLVED"}

MAX_BULK_TASKS = 50


class BulkTaskStatusPayload(BaseModel):
    task_ids: List[str]
    status: str


class BulkTaskAssignPayload(BaseModel):
    task_ids: List[str]
    assigned_to: str
    due_date: Optional[str] = None


# ── Task Status ────────────────────────────────────────────────────

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


# ── Task Assignment ────────────────────────────────────────────────

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

    # Generate in-app notification for the assignee
    if payload.assigned_to != actor_id:  # don't notify self
        await storage.save_notification(
            user_id=payload.assigned_to,
            notification={
                "project_id": project_id,
                "type": "TASK_ASSIGNED",
                "title": "Task Assigned",
                "message": f"Task '{target_task.get('title', task_id)}' has been assigned to you.",
                "metadata": {
                    "task_id": task_id,
                    "assigned_by": actor_id,
                    "due_date": payload.due_date,
                },
            },
        )

    return {
        "status": "assigned",
        "task_id": task_id,
        "assigned_to": payload.assigned_to,
        "assigned_by": actor_id,
        "due_date": payload.due_date,
    }


# ── Due Date Management ────────────────────────────────────────────

@router.put("/projects/{project_id}/tasks/{task_id}/due-date")
async def update_task_due_date(
    project_id: str,
    task_id: str,
    payload: TaskDueDatePayload,
    ctx: Dict[str, Any] = Depends(require_permission("remediation:manage")),
):
    """
    Set, change, or clear the due date for a remediation task.
    Only ADMIN/AUDITOR roles may modify due dates.
    Send due_date: null to clear the due date.
    Overdue status is informational only — it does not block verification.
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

    old_due_date = target_task.get("due_date")

    # Validate due_date format if provided
    if payload.due_date is not None:
        try:
            from datetime import datetime as _dt
            _dt.fromisoformat(payload.due_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid due_date '{payload.due_date}'. Must be ISO-8601.",
            )

    await storage.update_task_due_date(project_id, task_id, payload.due_date)

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    action = "set" if payload.due_date else "cleared"
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="TASK_DUE_DATE_UPDATED",
        actor_type="AUDITOR",
        actor_id=actor_id,
        task_id=task_id,
        requirement_id=target_task.get("related_requirement_id"),
        summary=f"Task '{task_id}' due date {action} by '{actor_id}'.",
        metadata={
            "task_id": task_id,
            "old_due_date": old_due_date,
            "new_due_date": payload.due_date,
            "action": action,
            "task_title": target_task.get("title"),
        },
    )

    return {
        "status": "updated",
        "task_id": task_id,
        "due_date": payload.due_date,
    }


# ── Bulk Task Operations ───────────────────────────────────────────

@router.post("/projects/{project_id}/bulk/tasks/status")
async def bulk_update_task_status(
    project_id: str,
    payload: BulkTaskStatusPayload,
    ctx: Dict[str, Any] = Depends(require_permission("remediation:manage")),
):
    """
    Atomically update the status of multiple remediation tasks.
    All tasks must belong to the project. If any task ID is invalid,
    no tasks are modified (atomic behavior).
    Maximum batch size: 50.
    """
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="task_ids cannot be empty")

    if len(payload.task_ids) > MAX_BULK_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot bulk-update more than {MAX_BULK_TASKS} tasks at once",
        )

    status_upper = payload.status.strip().upper()
    if status_upper not in VALID_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task status '{payload.status}'. Must be one of: {', '.join(sorted(VALID_TASK_STATUSES))}",
        )

    # Deduplicate while preserving order
    seen = set()
    unique_ids = [tid for tid in payload.task_ids if tid not in seen and not seen.add(tid)]

    # Validate ALL task IDs belong to this project (atomic check)
    tasks = await storage.get_tasks(project_id)
    task_map = {t.get("task_id"): t for t in tasks}
    invalid_ids = [tid for tid in unique_ids if tid not in task_map]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Tasks not found in this project: {', '.join(invalid_ids[:5])}{', ...' if len(invalid_ids) > 5 else ''}",
        )

    # Apply status updates
    updated_count = 0
    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    for tid in unique_ids:
        target_task = task_map[tid]
        old_status = target_task.get("status", "OPEN")
        if old_status == status_upper:
            continue  # skip unchanged

        await storage.update_task_status(project_id, tid, status_upper)
        updated_count += 1

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="TASK_STATUS_UPDATED",
            actor_type="AUDITOR",
            actor_id=actor_id,
            task_id=tid,
            requirement_id=target_task.get("related_requirement_id"),
            summary=f"Bulk status update: task '{tid}' changed from {old_status} to {status_upper}.",
            metadata={
                "task_id": tid,
                "old_status": old_status,
                "new_status": status_upper,
                "task_title": target_task.get("title"),
                "bulk_operation": True,
            },
        )

    return {
        "status": "success",
        "new_status": status_upper,
        "total_requested": len(unique_ids),
        "total_updated": updated_count,
        "total_unchanged": len(unique_ids) - updated_count,
    }


@router.post("/projects/{project_id}/bulk/tasks/assign")
async def bulk_assign_tasks(
    project_id: str,
    payload: BulkTaskAssignPayload,
    ctx: Dict[str, Any] = Depends(require_permission("remediation:manage")),
):
    """
    Atomically assign multiple remediation tasks to a project member.
    All tasks must belong to the project. Target user must be an active member.
    If any validation fails, no tasks are modified (atomic behavior).
    Maximum batch size: 50.
    """
    storage = _get_storage()

    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="task_ids cannot be empty")

    if len(payload.task_ids) > MAX_BULK_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot bulk-assign more than {MAX_BULK_TASKS} tasks at once",
        )

    # Validate target user is an active member
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
    if payload.due_date is not None:
        try:
            from datetime import datetime as _dt
            _dt.fromisoformat(payload.due_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid due_date '{payload.due_date}'. Must be ISO-8601.",
            )

    # Deduplicate while preserving order
    seen = set()
    unique_ids = [tid for tid in payload.task_ids if tid not in seen and not seen.add(tid)]

    # Validate ALL task IDs belong to this project (atomic check)
    tasks = await storage.get_tasks(project_id)
    task_map = {t.get("task_id"): t for t in tasks}
    invalid_ids = [tid for tid in unique_ids if tid not in task_map]
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Tasks not found in this project: {', '.join(invalid_ids[:5])}{', ...' if len(invalid_ids) > 5 else ''}",
        )

    # Apply assignments
    assigned_count = 0
    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    for tid in unique_ids:
        target_task = task_map[tid]
        await storage.assign_task(
            project_id=project_id,
            task_id=tid,
            assigned_to=payload.assigned_to,
            assigned_by=actor_id,
            due_date=payload.due_date,
        )
        assigned_count += 1

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="TASK_ASSIGNED",
            actor_type="AUDITOR",
            actor_id=actor_id,
            task_id=tid,
            requirement_id=target_task.get("related_requirement_id"),
            summary=f"Bulk assignment: task '{tid}' assigned to '{payload.assigned_to}'.",
            metadata={
                "task_id": tid,
                "old_assignee": target_task.get("assigned_to"),
                "new_assignee": payload.assigned_to,
                "assigned_by": actor_id,
                "due_date": payload.due_date,
                "task_title": target_task.get("title"),
                "bulk_operation": True,
            },
        )

    return {
        "status": "success",
        "assigned_to": payload.assigned_to,
        "total_requested": len(unique_ids),
        "total_assigned": assigned_count,
    }


# ── Remediation Uploads ────────────────────────────────────────────

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
