"""
ComplyFlow — Audit Event Routes

Provides:
  GET  /api/projects/{id}/audit-events          (list with filters)
  GET  /api/projects/{id}/audit-events/{event_id}  (single event)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api._shared import _get_storage
from app.services.auth_service import require_permission

router = APIRouter()


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
