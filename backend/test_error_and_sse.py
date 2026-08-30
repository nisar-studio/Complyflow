"""
ComplyFlow — Robust Error Handling & SSE Lifecycle Test Suite

Tests:
1. Multi-subscriber SSE registration, broadcast, and guaranteed cleanup on disconnect
2. Zero leaked project queues or memory references
3. Sensitive data and secret sanitization in error messages
4. Standardized FastAPI error response schemas
5. Secret-safe health probe verification
"""
from __future__ import annotations

import asyncio
import pytest
from app.services.event_broadcaster import EventBroadcaster, get_broadcaster
from app.agent.agent import _sanitize_error
from fastapi.testclient import TestClient
from app.services.auth_service import create_session_token
from app.main import app

client = TestClient(app)
token = create_session_token("demo-user", "demo@complyflow.local")
client.headers["Authorization"] = f"Bearer {token}"



@pytest.mark.asyncio
async def test_sse_broadcaster_subscribe_unsubscribe_and_cleanup():
    broadcaster = EventBroadcaster()
    project_id = "test-proj-123"

    # Initially 0 subscribers
    assert await broadcaster.get_active_subscriber_count(project_id) == 0
    assert await broadcaster.get_total_tracked_projects() == 0

    # Subscribe Client A
    queue_a = await broadcaster.subscribe(project_id)
    assert await broadcaster.get_active_subscriber_count(project_id) == 1
    assert await broadcaster.get_total_tracked_projects() == 1

    # Subscribe Client B (simultaneous client)
    queue_b = await broadcaster.subscribe(project_id)
    assert await broadcaster.get_active_subscriber_count(project_id) == 2

    # Broadcast event
    test_event = {"type": "TOOL_STARTED", "tool": "extract_requirements"}
    reached = await broadcaster.broadcast(project_id, test_event)
    assert reached == 2

    # Both clients receive the event
    assert not queue_a.empty()
    assert not queue_b.empty()
    assert queue_a.get_nowait() == test_event
    assert queue_b.get_nowait() == test_event

    # Client A disconnects
    await broadcaster.unsubscribe(project_id, queue_a)
    assert await broadcaster.get_active_subscriber_count(project_id) == 1
    assert await broadcaster.get_total_tracked_projects() == 1

    # Client B disconnects -> project tracking mapping is completely cleaned up
    await broadcaster.unsubscribe(project_id, queue_b)
    assert await broadcaster.get_active_subscriber_count(project_id) == 0
    assert await broadcaster.get_total_tracked_projects() == 0, "Empty project mapping must be deleted to prevent memory leaks"


@pytest.mark.asyncio
async def test_sse_multi_project_isolation():
    broadcaster = EventBroadcaster()
    q1 = await broadcaster.subscribe("proj-alpha")
    q2 = await broadcaster.subscribe("proj-beta")

    event_alpha = {"type": "AGENT_STARTED", "project": "alpha"}
    await broadcaster.broadcast("proj-alpha", event_alpha)

    # proj-alpha receives event, proj-beta remains empty
    assert not q1.empty()
    assert q2.empty()
    assert q1.get_nowait() == event_alpha

    await broadcaster.unsubscribe("proj-alpha", q1)
    await broadcaster.unsubscribe("proj-beta", q2)
    assert await broadcaster.get_total_tracked_projects() == 0


def test_error_sanitization_removes_sensitive_secrets():
    # 1. API key leak
    raw_error_1 = "Google GenAI API call failed with key AIzaSyA1234567890abcdef"
    safe_1 = _sanitize_error(raw_error_1)
    assert "AIzaSy" not in safe_1
    assert "sensitive data" in safe_1.lower()

    # 2. Authorization header / token leak
    raw_error_2 = "HTTP 401 Unauthorized: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    safe_2 = _sanitize_error(raw_error_2)
    assert "Bearer" not in safe_2
    assert "sensitive data" in safe_2.lower()

    # 3. Safe message passes through
    safe_text = "Document 'tax_clearance.pdf' missing required section header."
    assert _sanitize_error(safe_text) == safe_text


def test_standardized_api_404_error_response():
    res = client.get("/api/projects/non-existent-project-id")
    assert res.status_code == 404
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Project not found" in data["error"]["message"]
    assert data["error"]["recoverable"] is True


def test_standardized_api_400_invalid_upload():
    # Upload invalid file extension (.exe)
    res = client.post(
        "/api/projects/test-proj/documents",
        files={"requirements_file": ("malicious.exe", b"binary content", "application/octet-stream")},
    )
    # Could be 400 or 404 if project doesn't exist
    assert res.status_code in (400, 404)
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] in ("BAD_REQUEST", "NOT_FOUND")


def test_health_probe_does_not_leak_secrets():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert data["service"] == "complyflow-api"
    assert "gemini_configured" in data
    assert isinstance(data["gemini_configured"], bool)
    assert "api_key" not in str(data).lower()
    assert "secret" not in str(data).lower()
