# ComplyFlow Architecture Specification

## Overview

ComplyFlow is an autonomous AI compliance agent designed for multi-document compliance verification, gap detection, remediation planning, and re-verification.

```
+-------------------------------------------------------------------+
|                        React + Vite Frontend                      |
| (Landing, Dashboard, New Compliance Check, Live Agent Workspace)  |
+-------------------------------------------------------------------+
                                  |
                      HTTP API / SSE Live Stream
                                  v
+-------------------------------------------------------------------+
|                         FastAPI Backend                           |
|       (REST Endpoints, Document Processing, SSE Event Engine)      |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                      Google ADK 2.8.0 Agent                       |
|   (Autonomous Tool Selection, Reasoning Loop, Event Emitter)      |
+-------------------------------------------------------------------+
                                  |
                Google GenAI API (Gemini 3.5+ / Flash)
                                  v
+-------------------------------------------------------------------+
|                           ADK Agent Tools                         |
|  1. extract_requirements   - Structured requirements extraction   |
|  2. analyze_documents      - Fact & statement extraction          |
|  3. match_evidence         - Requirement <-> Document mapping     |
|  4. detect_gaps            - Missing, conflict & severity detection|
|  5. create_remediation_plan- Actionable task generation           |
|  6. verify_compliance      - Post-remediation 100% verification    |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                      Google Cloud Firestore                       |
|  (Projects, Requirements, Matches, Issues, Tasks, Agent Events)   |
+-------------------------------------------------------------------+
```

## Agent Design & Tool Orchestration

ComplyFlow utilizes the Google Agent Development Kit (**google-adk 2.8.0**) with `LlmAgent` and `Runner`.

1. **System Prompt & Persona**: The agent operates under strict instructions to inspect the requirements document first, analyze evidence documents, map evidence, detect gaps, generate a remediation plan, and perform re-verification.
2. **Tool Selection**: Tools return typed, validated Pydantic structures.
3. **Determinism Split**: File text extraction (PDF, DOCX, TXT) and database operations are executed deterministically using standard Python libraries (`pypdf`, `python-docx`, `google-cloud-firestore`), reserving Gemini for reasoning operations.
4. **SSE Event Streaming**: As ADK tools execute, events are emitted dual-channel (in-memory async queue for real-time Server-Sent Events, and Firestore `agent_events` sub-collection for persistent audit logs).

## Data Schema (Firestore)

- `projects/{projectId}`
- `projects/{projectId}/requirements/{reqId}`
- `projects/{projectId}/documents/{docId}`
- `projects/{projectId}/matches/{matchId}`
- `projects/{projectId}/issues/{gapId}`
- `projects/{projectId}/tasks/{taskId}`
- `projects/{projectId}/agent_events/{eventId}`
- `projects/{projectId}/verification_runs/{runId}`
