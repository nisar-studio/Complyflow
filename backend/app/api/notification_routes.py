"""
ComplyFlow — Notification Routes

Provides:
  GET  /api/notifications              (list notifications)
  GET  /api/notifications/unread-count (unread count)
  PUT  /api/notifications/{id}/read    (mark single read)
  PUT  /api/notifications/read-all     (mark all read)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api._shared import _get_storage
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/notifications")
async def list_notifications(
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    unread_only: bool = Query(False, description="Only show unread notifications"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List notifications for the authenticated user."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    notifications = await storage.get_notifications(
        user_id=user_id,
        project_id=project_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return {"notifications": notifications}


@router.get("/notifications/unread-count")
async def get_unread_count(
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
):
    """Get count of unread notifications for the authenticated user."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    count = await storage.count_unread_notifications(
        user_id=user_id,
        project_id=project_id,
    )
    return {"unread_count": count}


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark a single notification as read."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    updated = await storage.mark_notification_read(user_id, notification_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read", "notification_id": notification_id}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_id: Optional[str] = Query(None, description="Scope to a specific project"),
):
    """Mark all unread notifications as read for the authenticated user."""
    storage = _get_storage()
    user_id = current_user["user_id"]
    count = await storage.mark_all_notifications_read(user_id, project_id)
    return {"status": "read_all", "count": count}
