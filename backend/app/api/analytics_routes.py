"""
ComplyFlow — Analytics Routes

Provides:
  GET  /api/projects/{id}/analytics  (project analytics)
  GET  /api/analytics/portfolio      (cross-project portfolio)
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.api._shared import _get_storage
from app.services.auth_service import get_current_user, get_project_member_context

router = APIRouter()


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
