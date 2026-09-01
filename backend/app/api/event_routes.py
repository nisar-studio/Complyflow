"""
ComplyFlow — Event & SSE Routes

Provides:
  GET  /api/projects/{id}/events         (polling fallback)
  GET  /api/projects/{id}/events/stream  (SSE streaming)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api._shared import _get_storage
from app.services.auth_service import get_project_member_context

router = APIRouter()


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
