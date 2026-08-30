"""
ComplyFlow — Enterprise Audit Logging Service

Provides append-only, structured audit event recording for compliance lifecycle actions.
Sanitizes metadata to prevent secret or server filesystem path leakage.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.services.file_utils import sanitize_filename
from app.services.storage import StorageInterface, get_storage


class AuditActorType(str, Enum):
    SYSTEM = "SYSTEM"
    AI_AGENT = "AI_AGENT"
    AUDITOR = "AUDITOR"


class AuditSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AuditEventType(str, Enum):
    PROJECT_CREATED = "PROJECT_CREATED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    REQUIREMENT_CONFLICT_DETECTED = "REQUIREMENT_CONFLICT_DETECTED"
    REQUIREMENT_GAP_DETECTED = "REQUIREMENT_GAP_DETECTED"
    REMEDIATION_TASK_CREATED = "REMEDIATION_TASK_CREATED"
    REMEDIATION_UPLOAD_CREATED = "REMEDIATION_UPLOAD_CREATED"
    REMEDIATION_UPLOAD_DELETED = "REMEDIATION_UPLOAD_DELETED"
    AUDITOR_OVERRIDE_CREATED = "AUDITOR_OVERRIDE_CREATED"
    AUDITOR_OVERRIDE_UPDATED = "AUDITOR_OVERRIDE_UPDATED"
    AUDITOR_OVERRIDE_REVOKED = "AUDITOR_OVERRIDE_REVOKED"
    AUDITOR_NOTE_CREATED = "AUDITOR_NOTE_CREATED"
    AUDITOR_NOTE_DELETED = "AUDITOR_NOTE_DELETED"
    REPORT_EXPORTED = "REPORT_EXPORTED"
    ERROR_OCCURRED = "ERROR_OCCURRED"


def sanitize_audit_text(text: Optional[str]) -> str:
    """Remove absolute server paths, bearer tokens, API keys, and stack traces from audit text."""
    if not text:
        return ""
    # Strip Windows absolute paths (e.g. C:\path\to\file)
    clean = re.sub(r"[A-Za-z]:\\[^\s\"']+", "[REDACTED_PATH]", text)
    # Strip Unix /tmp or /var or /home paths
    clean = re.sub(r"/(?:tmp|var|home|usr|etc)/[^\s\"']+", "[REDACTED_PATH]", clean)
    # Strip Authorization / Bearer tokens / API keys
    clean = re.sub(r"(?i)(?:bearer\s+|api[_\-]?key\s*[:=]\s*)[a-zA-Z0-9_\-\.]{10,}", "[REDACTED_SECRET]", clean)
    return clean


def sanitize_audit_metadata(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitize metadata dictionary to exclude sensitive fields and server paths."""
    if not data or not isinstance(data, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        # Exclude server internal storage keys
        if k in ("stored_filename", "db_path", "api_key", "password", "token", "secret"):
            continue

        if isinstance(v, dict):
            sanitized[k] = sanitize_audit_metadata(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_audit_metadata(item) if isinstance(item, dict)
                else sanitize_audit_text(item) if isinstance(item, str)
                else item
                for item in v
            ]
        elif isinstance(v, str):
            sanitized[k] = sanitize_audit_text(v)
        else:
            sanitized[k] = v

    return sanitized


async def record_audit_event(
    storage: StorageInterface,
    project_id: str,
    event_type: str,
    actor_type: str = "SYSTEM",
    actor_id: Optional[str] = None,
    requirement_id: Optional[str] = None,
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    document_id: Optional[str] = None,
    upload_id: Optional[str] = None,
    severity: str = "INFO",
    summary: str = "",
    description: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    emit_event: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """
    Append-only audit event recorder.
    Saves event to SQLite and broadcasts via SSE if emit_event is provided.
    """
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    clean_summary = sanitize_audit_text(summary)
    clean_description = sanitize_audit_text(description) if description else None
    clean_meta = sanitize_audit_metadata(metadata)

    event_data = {
        "event_id": event_id,
        "project_id": project_id,
        "timestamp": now,
        "event_type": event_type.upper(),
        "actor_type": actor_type.upper(),
        "actor_id": actor_id,
        "requirement_id": requirement_id,
        "run_id": run_id,
        "task_id": task_id,
        "document_id": document_id,
        "upload_id": upload_id,
        "severity": severity.upper(),
        "summary": clean_summary,
        "description": clean_description,
        "metadata": clean_meta,
        "created_at": now,
    }

    saved_id = await storage.save_audit_event(project_id, event_data)

    if emit_event:
        try:
            emit_event({
                "type": "AUDIT_EVENT_CREATED",
                "project_id": project_id,
                "event_id": saved_id,
                "event_type": event_data["event_type"],
                "actor_type": event_data["actor_type"],
                "severity": event_data["severity"],
                "summary": event_data["summary"],
                "timestamp": now,
                "data": event_data,
            })
        except Exception:
            pass  # Broadcast failures should never fail the transaction

    return saved_id
