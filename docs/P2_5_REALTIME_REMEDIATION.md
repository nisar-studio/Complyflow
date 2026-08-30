# P2 #5 — Real-Time Agent Monitoring & Remediation Lifecycle Completion

## Executive Summary

P2 #5 completes two previously broken core workflows in ComplyFlow:

1. **Real-time agent monitoring** — The `EventBroadcaster` service and `useAgentEvents` hook existed but had no HTTP endpoints. The SSE streaming infrastructure was dead code. Users could not see live agent tool execution progress.

2. **Remediation task lifecycle** — The `update_task_status` storage method existed and was tested, but no API endpoint exposed it. Remediation tasks could never be marked RESOLVED, making the task-status analytics metric meaningless and the remediation workflow incomplete.

Both issues have been resolved with minimal, focused changes that reuse existing infrastructure.

## Problem

### Real-Time Monitoring
- `EventBroadcaster` class: ✅ implemented (`event_broadcaster.py`)
- `_emit_factory()` in routes: ✅ broadcasts to SSE queues
- Frontend `useAgentEvents.js`: ✅ connects via `EventSource` + polling fallback
- **Missing:** No `GET /api/projects/{id}/events/stream` SSE endpoint
- **Missing:** No `GET /api/projects/{id}/events` polling endpoint

### Remediation Lifecycle
- `storage.update_task_status()`: ✅ implemented and tested
- Frontend `RemediationList.jsx`: ✅ shows tasks with status
- **Missing:** No `PUT /api/projects/{id}/tasks/{task_id}/status` endpoint
- **Missing:** No resolve/reopen UI controls in `RemediationList.jsx`

## Architecture

### New Endpoints

```
GET  /api/projects/{project_id}/events          → Polling fallback
GET  /api/projects/{project_id}/events/stream   → SSE real-time stream
PUT  /api/projects/{project_id}/tasks/{task_id}/status → Task status update
```

### Data Flow — Real-Time Monitoring

```
Agent runs analysis
  → _emit_factory() callback
    → storage.add_event() [persistence]
    → broadcaster.broadcast() [SSE delivery]
      → EventBroadcaster._subscribers[project_id] queues
        → SSE generator yields to connected clients
          → Frontend useAgentEvents.js receives events
```

### Data Flow — Task Resolution

```
Auditor clicks "Mark Resolved" in RemediationList.jsx
  → api.updateTaskStatus(projectId, taskId, "RESOLVED")
    → PUT /api/projects/{id}/tasks/{task_id}/status
      → storage.update_task_status()
      → record_audit_event(TASK_STATUS_UPDATED)
      → Response: { old_status: "OPEN", new_status: "RESOLVED" }
    → Frontend updates task state in-place
```

## Endpoints

### GET /api/projects/{project_id}/events

Returns all agent execution events for a project. Used as a polling fallback when SSE is unavailable.

- **Auth:** Required (Bearer token or session cookie)
- **RBAC:** Project membership required
- **Response:** `{ "events": [...] }`

### GET /api/projects/{project_id}/events/stream

Server-Sent Events stream for real-time agent execution monitoring.

- **Auth:** Required
- **RBAC:** Project membership required
- **Content-Type:** `text/event-stream`
- **Format:** `data: {JSON}\n\n`
- **Heartbeats:** Every 30 seconds to keep connection alive
- **Cleanup:** Automatic unsubscribe on client disconnect

### PUT /api/projects/{project_id}/tasks/{task_id}/status

Update a remediation task's status between OPEN and RESOLVED.

- **Auth:** Required
- **RBAC:** `remediation:manage` permission (ADMIN, AUDITOR roles)
- **Request body:** `{ "status": "OPEN" | "RESOLVED" }`
- **Response:** `{ "status": "updated", "task_id": "...", "old_status": "...", "new_status": "..." }`
- **Audit:** Emits immutable `TASK_STATUS_UPDATED` audit event with actor, old/new status, and metadata

## RBAC Enforcement

| Endpoint | Minimum Role | Permission |
|----------|-------------|------------|
| GET /events | Any project member | `project:view` (implicit via membership) |
| GET /events/stream | Any project member | `project:view` (implicit via membership) |
| PUT /tasks/{id}/status | ADMIN or AUDITOR | `remediation:manage` |

## Audit Behavior

Every task status transition produces an immutable audit event:

```json
{
  "event_type": "TASK_STATUS_UPDATED",
  "actor_type": "AUDITOR",
  "actor_id": "user_xxx",
  "task_id": "TASK-001",
  "requirement_id": "REQ-006",
  "summary": "Task 'TASK-001' status changed from OPEN to RESOLVED.",
  "metadata": {
    "task_id": "TASK-001",
    "old_status": "OPEN",
    "new_status": "RESOLVED",
    "task_title": "Upload General Liability Insurance"
  }
}
```

Audit events are append-only and cannot be modified or deleted.

## Frontend Behavior

### RemediationList.jsx
- Each task card now shows a "Mark Resolved" button (for OPEN tasks) or "Reopen" button (for RESOLVED tasks)
- Loading state shown while API call is in progress
- Success/error feedback banners
- Task status updates in-place without full page reload
- Existing filters, search, and severity metrics preserved

### useAgentEvents.js
- No changes needed — the hook already connects to the correct endpoints
- SSE path: `EventSource` → `/api/projects/{id}/events/stream`
- Polling fallback: `api.getEvents()` → `/api/projects/{id}/events`

## Tests

### P2 #5 Test Suite (26 tests)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestEventsListEndpoint` | 6 | Auth, membership, isolation, empty, 404 |
| `TestSSEStreamEndpoint` | 7 | Auth, membership, content-type, delivery, isolation, cleanup, 404 |
| `TestTaskStatusUpdateEndpoint` | 13 | OPEN→RESOLVED, RESOLVED→OPEN, invalid status, nonexistent task, cross-project, unauth, RBAC, audit, idempotent, 404, auditor, reviewer, metadata |

### Full Test Suite
- **358 passed, 0 failed** (P2 #5: 26 tests, pre-existing: 332 tests)

## Known Limitations

1. **SSE timeout:** The streaming endpoint sends a heartbeat every 30 seconds. Proxies/load balancers with shorter timeouts may drop the connection. The frontend has automatic reconnection with exponential backoff (3 attempts before falling back to polling).

2. **Task status values:** Only `OPEN` and `RESOLVED` are currently supported. Additional statuses (e.g., `IN_PROGRESS`, `BLOCKED`) could be added later by extending `VALID_TASK_STATUSES`.

3. **Concurrent SSE connections:** The `EventBroadcaster` uses in-memory `asyncio.Queue` per subscriber. In a multi-process deployment (e.g., multiple uvicorn workers), events are only broadcast to subscribers on the same worker. For single-process deployments this is not an issue.

## Deployment Considerations

- No database schema changes required
- No new dependencies
- No configuration changes
- Backward-compatible — existing API clients continue to work
- The new endpoints are additive only

## Files Changed

| File | Change |
|------|--------|
| `backend/app/api/routes.py` | +120 lines: 3 new endpoints |
| `backend/app/services/audit_service.py` | +1 line: `TASK_STATUS_UPDATED` event type |
| `frontend/src/api/client.js` | +5 lines: `updateTaskStatus()` method |
| `frontend/src/components/RemediationList.jsx` | +50 lines: resolve/reopen UI |
| `backend/test_realtime_remediation.py` | +625 lines: 26 comprehensive tests |
