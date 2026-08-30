"""
ComplyFlow — Unified Storage Layer

Primary persistence: SQLiteStorageService (local-first, self-hosted).
FirestoreStorageService is a legacy stub and is never selected at runtime.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


class StorageInterface(ABC):
    """Abstract interface for all ComplyFlow persistence operations."""

    @abstractmethod
    async def create_project(self, project_data: Dict[str, Any]) -> str:
        """Create a project and return its project_id."""
        pass

    @abstractmethod
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a project by ID."""
        pass

    @abstractmethod
    async def update_project(self, project_id: str, updates: Dict[str, Any]) -> None:
        """Update fields on a project document."""
        pass

    @abstractmethod
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects for the current user."""
        pass

    @abstractmethod
    async def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its child records."""
        pass


    @abstractmethod
    async def save_requirements(self, project_id: str, requirements: List[Dict[str, Any]]) -> None:
        """Store extracted requirements for a project."""
        pass

    @abstractmethod
    async def get_requirements(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all requirements for a project."""
        pass

    @abstractmethod
    async def save_document_analysis(self, project_id: str, doc_id: str, analysis: Dict[str, Any]) -> None:
        """Store uploaded document metadata & analysis."""
        pass

    @abstractmethod
    async def get_document(self, project_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document's text/analysis."""
        pass

    @abstractmethod
    async def list_documents(self, project_id: str, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """List documents for a project, optionally filtered by role."""
        pass

    @abstractmethod
    async def delete_document(self, project_id: str, doc_id: str) -> bool:
        """Delete a document record for a project."""
        pass

    @abstractmethod
    async def create_framework(self, framework_data: Dict[str, Any], requirements: List[Dict[str, Any]]) -> str:
        """Create a versioned framework with its requirement definitions."""
        pass

    @abstractmethod
    async def get_framework(self, framework_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a framework by ID."""
        pass

    @abstractmethod
    async def list_frameworks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available frameworks."""
        pass

    @abstractmethod
    async def get_framework_requirements(self, framework_id: str) -> List[Dict[str, Any]]:
        """Retrieve all requirements for a specific framework."""
        pass

    @abstractmethod
    async def update_framework_status(self, framework_id: str, status: str) -> bool:
        """Update framework status (ACTIVE, INACTIVE, DRAFT)."""
        pass

    @abstractmethod
    async def delete_framework(self, framework_id: str) -> bool:
        """Delete a framework and its requirements."""
        pass

    @abstractmethod
    async def is_framework_referenced_in_runs(self, framework_id: str) -> bool:
        """Check if a framework is referenced in historical verification runs."""
        pass



    @abstractmethod
    async def save_issues(self, project_id: str, issues: List[Dict[str, Any]]) -> None:
        """Store detected compliance gaps/issues."""
        pass

    @abstractmethod
    async def get_issues(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all issues/gaps for a project."""
        pass

    @abstractmethod
    async def save_tasks(self, project_id: str, tasks: List[Dict[str, Any]]) -> None:
        """Store remediation tasks."""
        pass

    @abstractmethod
    async def get_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all remediation tasks for a project."""
        pass

    @abstractmethod
    async def update_task_status(self, project_id: str, task_id: str, status: str) -> None:
        """Update the status of a specific task."""
        pass

    @abstractmethod
    async def save_matches(self, project_id: str, matches: List[Dict[str, Any]]) -> None:
        """Store requirement-to-evidence matches."""
        pass

    @abstractmethod
    async def get_matches(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all matches for a project."""
        pass

    @abstractmethod
    async def add_event(self, project_id: str, event: Dict[str, Any]) -> str:
        """Append an agent execution event."""
        pass

    @abstractmethod
    async def get_events(self, project_id: str) -> List[Dict[str, Any]]:
        """Get chronological agent events for a project."""
        pass

    @abstractmethod
    async def save_verification_run(self, project_id: str, result: Dict[str, Any]) -> str:
        """Save an immutable point-in-time verification run snapshot."""
        pass

    @abstractmethod
    async def get_verification_run(self, project_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific historical verification run by run_id or run_number."""
        pass

    @abstractmethod
    async def list_verification_runs(self, project_id: str) -> List[Dict[str, Any]]:
        """List all historical verification runs in chronological order."""
        pass

    @abstractmethod
    async def get_latest_verification(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent verification run snapshot."""
        pass

    @abstractmethod
    async def get_results(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get consolidated project results."""
        pass

    # ── Auditor Overrides & Notes ────────────────────────────

    @abstractmethod
    async def save_auditor_override(self, project_id: str, requirement_id: str, override_data: Dict[str, Any]) -> str:
        """Save or update a human auditor override for a requirement."""
        pass

    @abstractmethod
    async def get_auditor_override(self, project_id: str, requirement_id: str) -> Optional[Dict[str, Any]]:
        """Get auditor override for a specific requirement."""
        pass

    @abstractmethod
    async def list_auditor_overrides(self, project_id: str) -> List[Dict[str, Any]]:
        """List all auditor overrides for a project."""
        pass

    @abstractmethod
    async def delete_auditor_override(self, project_id: str, requirement_id: str) -> bool:
        """Delete / revoke an auditor override, restoring AI baseline."""
        pass

    @abstractmethod
    async def save_auditor_note(self, project_id: str, requirement_id: str, note_data: Dict[str, Any]) -> str:
        """Save an auditor note for a requirement."""
        pass

    @abstractmethod
    async def list_auditor_notes(self, project_id: str, requirement_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List auditor notes for a project, optionally filtered by requirement_id."""
        pass

    @abstractmethod
    async def delete_auditor_note(self, project_id: str, note_id: str) -> bool:
        """Delete an auditor note."""
        pass

    # ── Remediation Uploads ──────────────────────────────────

    @abstractmethod
    async def save_remediation_upload(self, project_id: str, task_id: str, upload_data: Dict[str, Any]) -> str:
        """Save a remediation evidence upload linked to a specific task."""
        pass

    @abstractmethod
    async def get_remediation_upload(self, project_id: str, upload_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific remediation upload by ID."""
        pass

    @abstractmethod
    async def list_remediation_uploads(self, project_id: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List remediation uploads for a project, optionally filtered by task_id."""
        pass

    @abstractmethod
    async def delete_remediation_upload(self, project_id: str, upload_id: str) -> bool:
        """Delete a remediation upload record."""
        pass

    # ── Audit Events (Immutable / Append-Only) ───────────────

    @abstractmethod
    async def save_audit_event(self, project_id: str, event_data: Dict[str, Any]) -> str:
        """Append an immutable audit event for a project. Returns event_id."""
        pass

    @abstractmethod
    async def get_audit_event(self, project_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single audit event by ID."""
        pass

    @abstractmethod
    async def list_audit_events(
        self,
        project_id: str,
        event_type: Optional[str] = None,
        actor_type: Optional[str] = None,
        severity: Optional[str] = None,
        requirement_id: Optional[str] = None,
        run_id: Optional[str] = None,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List audit events for a project with optional filters, ordered by timestamp DESC."""
        pass

    @abstractmethod
    async def count_audit_events(
        self,
        project_id: str,
        event_type: Optional[str] = None,
        actor_type: Optional[str] = None,
        severity: Optional[str] = None,
        requirement_id: Optional[str] = None,
        run_id: Optional[str] = None,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
    ) -> int:
        """Count matching audit events for a project."""
        pass

    # ── Users & Project Members (Authentication & RBAC) ──────

    @abstractmethod
    async def create_user(self, user_data: Dict[str, Any]) -> str:
        """Create a new user. Returns user_id."""
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by ID."""
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by email (case-insensitive)."""
        pass

    @abstractmethod
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user fields."""
        pass

    @abstractmethod
    async def list_users(self) -> List[Dict[str, Any]]:
        """List all users (excluding password hashes in output)."""
        pass

    @abstractmethod
    async def count_users(self) -> int:
        """Count total registered users."""
        pass

    @abstractmethod
    async def add_project_member(self, project_id: str, user_id: str, role: str) -> str:
        """Add or update a project member role. Returns membership_id."""
        pass

    @abstractmethod
    async def get_project_member(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get membership details for a user in a project."""
        pass

    @abstractmethod
    async def list_project_members(self, project_id: str) -> List[Dict[str, Any]]:
        """List all members of a project with user details."""
        pass

    @abstractmethod
    async def update_project_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        """Update a member's role in a project."""
        pass

    @abstractmethod
    async def remove_project_member(self, project_id: str, user_id: str) -> bool:
        """Remove a member from a project."""
        pass

    @abstractmethod
    async def list_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """List all projects a user is a member of with their assigned role."""
        pass

    # ── Sessions (Server-side Revocation & Tracking) ─────────

    @abstractmethod
    async def create_session(self, session_data: Dict[str, Any]) -> str:
        """Create a new session record. Returns session_id."""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by its unique ID."""
        pass

    @abstractmethod
    async def revoke_session(self, session_id: str) -> bool:
        """Revoke a specific session."""
        pass

    @abstractmethod
    async def revoke_user_sessions(self, user_id: str) -> bool:
        """Revoke all active sessions for a user."""
        pass



# ─────────────────────────────────────────────────────────────

# SQLite Implementation (Local / Zero-Config)
# ─────────────────────────────────────────────────────────────

class SQLiteStorageService(StorageInterface):
    """
    High-performance async SQLite storage.
    Creates tables automatically and handles JSON serialization.
    """

    USER_ID = "demo-user"

    def __init__(self, db_path: str = "complyflow.db"):
        self.db_path = str(Path(db_path).resolve())
        self._initialized = False

    @asynccontextmanager
    async def _connect(self):
        """Open a SQLite connection with per-connection safety pragmas."""
        db = await aiosqlite.connect(self.db_path)
        try:
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("PRAGMA busy_timeout=5000;")
            yield db
        finally:
            await db.close()

    async def _migrate_verification_runs_pk(self, db) -> None:
        """
        Historical schema used run_id as a global PRIMARY KEY (values like 'run_1').
        That collides across projects. Composite PK (project_id, run_id) is required.
        """
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='verification_runs'"
        ) as cursor:
            row = await cursor.fetchone()
        if not row or not row[0]:
            return
        ddl = " ".join(row[0].split())
        if "PRIMARY KEY (project_id, run_id)" in ddl:
            return

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_runs_v2 (
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                run_number INTEGER NOT NULL DEFAULT 1,
                timestamp TEXT NOT NULL,
                data_json TEXT NOT NULL,
                PRIMARY KEY (project_id, run_id)
            );
            """
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO verification_runs_v2 (project_id, run_id, run_number, timestamp, data_json)
            SELECT project_id, run_id, run_number, timestamp, data_json FROM verification_runs
            """
        )
        await db.execute("DROP TABLE verification_runs")
        await db.execute("ALTER TABLE verification_runs_v2 RENAME TO verification_runs")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_vr_proj_num ON verification_runs (project_id, run_number)"
        )

    async def _init_db(self):
        if self._initialized:
            return

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as db:  # schema bootstrap only
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("PRAGMA busy_timeout=5000;")
            
            # 1. Projects

            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    compliance_score REAL,
                    overall_status TEXT,
                    requirements_count INTEGER DEFAULT 0,
                    documents_count INTEGER DEFAULT 0,
                    issues_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}'
                );
            """)

            # 2. Requirements
            await db.execute("""
                CREATE TABLE IF NOT EXISTS requirements (
                    project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    required_evidence TEXT,
                    priority TEXT,
                    source_reference TEXT,
                    data_json TEXT,
                    PRIMARY KEY (project_id, requirement_id)
                );
            """)

            # 3. Documents
            await db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    project_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT,
                    data_json TEXT,
                    PRIMARY KEY (project_id, doc_id)
                );
            """)

            # 4. Matches
            await db.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL,
                    reasoning TEXT,
                    data_json TEXT,
                    PRIMARY KEY (project_id, requirement_id)
                );
            """)

            # 5. Issues / Gaps
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    project_id TEXT NOT NULL,
                    gap_id TEXT NOT NULL,
                    gap_type TEXT,
                    severity TEXT,
                    description TEXT,
                    data_json TEXT,
                    PRIMARY KEY (project_id, gap_id)
                );
            """)

            # 6. Tasks
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    title TEXT,
                    severity TEXT,
                    required_action TEXT,
                    status TEXT NOT NULL,
                    data_json TEXT,
                    PRIMARY KEY (project_id, task_id)
                );
            """)

            # 7. Agent Events
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    tool TEXT,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    summary TEXT,
                    data_json TEXT
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_events_proj ON agent_events (project_id, timestamp);")

            # 8. Verification Runs (Immutable Point-in-Time Snapshots)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS verification_runs (
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    run_number INTEGER NOT NULL DEFAULT 1,
                    timestamp TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, run_id)
                );
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_vr_proj_num ON verification_runs (project_id, run_number)"
            )

            # Auto-migrate run_number column if table existed previously without it
            async with db.execute("PRAGMA table_info(verification_runs)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "run_number" not in columns:
                    await db.execute("ALTER TABLE verification_runs ADD COLUMN run_number INTEGER NOT NULL DEFAULT 1")

            await self._migrate_verification_runs_pk(db)

            # 9. Auditor Overrides (Human-in-the-loop Governance)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS auditor_overrides (
                    override_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    original_ai_status TEXT NOT NULL,
                    overridden_status TEXT NOT NULL,
                    auditor_reason TEXT NOT NULL,
                    auditor_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT,
                    UNIQUE(project_id, requirement_id)
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_overrides_proj ON auditor_overrides (project_id, requirement_id);")

            # 10. Auditor Notes
            await db.execute("""
                CREATE TABLE IF NOT EXISTS auditor_notes (
                    note_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_proj ON auditor_notes (project_id, requirement_id);")

            # 11. Remediation Uploads (Task-linked Evidence)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS remediation_uploads (
                    upload_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    upload_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
                    description TEXT DEFAULT '',
                    data_json TEXT
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_remed_uploads_proj_task ON remediation_uploads (project_id, task_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_remed_uploads_proj_req ON remediation_uploads (project_id, requirement_id);")

            # ── Immutable Audit Log Table ─────────────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    actor_id TEXT,
                    requirement_id TEXT,
                    run_id TEXT,
                    task_id TEXT,
                    document_id TEXT,
                    upload_id TEXT,
                    severity TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    description TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_proj_time ON audit_events (project_id, timestamp);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_proj_type ON audit_events (project_id, event_type);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_proj_req ON audit_events (project_id, requirement_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_proj_run ON audit_events (project_id, run_id);")

            # ── 12. Users (Authentication & Accounts) ────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")

            # ── 13. Project Members (Role-Based Access Control) ──────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS project_members (
                    membership_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, user_id)
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_members_proj ON project_members (project_id);")
            # ── 14. Sessions (Server-side Revocation & Tracking) ─────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_revoked BOOLEAN NOT NULL DEFAULT 0,
                    revoked_at TEXT,
                    last_active TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions (token_hash);")

            # ── 15. Frameworks ───────────────────────────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS frameworks (
                    framework_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT,
                    source TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    requirement_count INTEGER DEFAULT 0,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    UNIQUE(name, version)
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_frameworks_name_ver ON frameworks (name, version);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_frameworks_proj ON frameworks (project_id);")

            # ── 16. Framework Requirements ───────────────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS framework_requirements (
                    framework_id TEXT NOT NULL,
                    requirement_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT DEFAULT 'General',
                    severity TEXT DEFAULT 'MEDIUM',
                    priority TEXT DEFAULT 'MEDIUM',
                    guidance TEXT DEFAULT '',
                    source_reference TEXT DEFAULT '',
                    data_json TEXT,
                    PRIMARY KEY (framework_id, requirement_id),
                    FOREIGN KEY(framework_id) REFERENCES frameworks(framework_id) ON DELETE CASCADE
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_fw_reqs_id ON framework_requirements (framework_id, requirement_id);")

            # Seed default demo user for local-first testing / development only
            app_env = os.environ.get("APP_ENV", "development").lower()
            if app_env != "production":
                await db.execute("""
                    INSERT OR IGNORE INTO users (user_id, email, name, password_hash, is_active, created_at, updated_at)
                    VALUES ('demo-user', 'demo@complyflow.local', 'Compliance Auditor', 'pbkdf2_sha256$100000$default$default', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """)

            await db.commit()

        self._initialized = True




    # ── Project CRUD ─────────────────────────────────────────

    async def create_project(self, project_data: Dict[str, Any]) -> str:
        await self._init_db()
        project_id = project_data.get("project_id") or str(uuid.uuid4())
        now = self._now()
        project_data["project_id"] = project_id
        project_data["user_id"] = self.USER_ID
        project_data["created_at"] = now
        project_data["updated_at"] = now

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO projects (
                    project_id, user_id, name, status, compliance_score,
                    overall_status, requirements_count, documents_count,
                    issues_count, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    self.USER_ID,
                    project_data.get("name", "Untitled Project"),
                    project_data.get("status", "PENDING"),
                    project_data.get("compliance_score"),
                    project_data.get("overall_status"),
                    project_data.get("requirements_count", 0),
                    project_data.get("documents_count", 0),
                    project_data.get("issues_count", 0),
                    now,
                    now,
                    json.dumps(project_data),
                ),
            )
            await db.commit()
        return project_id

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                data["project_id"] = row["project_id"]
                data["user_id"] = row["user_id"]
                data["name"] = row["name"]
                data["status"] = row["status"]
                data["compliance_score"] = row["compliance_score"]
                data["overall_status"] = row["overall_status"]
                data["requirements_count"] = row["requirements_count"]
                data["documents_count"] = row["documents_count"]
                data["issues_count"] = row["issues_count"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
                return data

    async def update_project(self, project_id: str, updates: Dict[str, Any]) -> None:
        await self._init_db()
        current = await self.get_project(project_id)
        if not current:
            return
        current.update(updates)
        now = self._now()
        current["updated_at"] = now

        async with self._connect() as db:
            await db.execute(
                """
                UPDATE projects SET
                    name = ?,
                    status = ?,
                    compliance_score = ?,
                    overall_status = ?,
                    requirements_count = ?,
                    documents_count = ?,
                    issues_count = ?,
                    updated_at = ?,
                    metadata_json = ?
                WHERE project_id = ?
                """,
                (
                    current.get("name"),
                    current.get("status"),
                    current.get("compliance_score"),
                    current.get("overall_status"),
                    current.get("requirements_count", 0),
                    current.get("documents_count", 0),
                    current.get("issues_count", 0),
                    now,
                    json.dumps(current),
                    project_id,
                ),
            )
            await db.commit()

    async def list_projects(self) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (self.USER_ID,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    data = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                    data["project_id"] = row["project_id"]
                    data["user_id"] = row["user_id"]
                    data["name"] = row["name"]
                    data["status"] = row["status"]
                    data["compliance_score"] = row["compliance_score"]
                    data["overall_status"] = row["overall_status"]
                    data["requirements_count"] = row["requirements_count"]
                    data["documents_count"] = row["documents_count"]
                    data["issues_count"] = row["issues_count"]
                    data["created_at"] = row["created_at"]
                    data["updated_at"] = row["updated_at"]
                    results.append(data)
                return results

    async def delete_project(self, project_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            tables = [
                "projects", "project_members", "requirements", "documents",
                "matches", "issues", "tasks", "agent_events",
                "remediation_uploads", "verification_runs",
                "auditor_overrides", "auditor_notes", "audit_events"
            ]
            for table in tables:
                await db.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
            await db.commit()
        return True

    # ── Requirements ─────────────────────────────────────────


    async def save_requirements(self, project_id: str, requirements: List[Dict[str, Any]]) -> None:
        await self._init_db()
        async with self._connect() as db:
            for req in requirements:
                req_id = req["requirement_id"]
                await db.execute(
                    """
                    INSERT INTO requirements (
                        project_id, requirement_id, title, description,
                        required_evidence, priority, source_reference, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, requirement_id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        required_evidence = excluded.required_evidence,
                        priority = excluded.priority,
                        source_reference = excluded.source_reference,
                        data_json = excluded.data_json
                    """,
                    (
                        project_id,
                        req_id,
                        req.get("title", ""),
                        req.get("description", ""),
                        req.get("required_evidence", ""),
                        req.get("priority", "MEDIUM"),
                        req.get("source_reference", ""),
                        json.dumps(req),
                    ),
                )
            await db.commit()

    async def get_requirements(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM requirements WHERE project_id = ? ORDER BY requirement_id ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    # ── Documents ────────────────────────────────────────────

    async def save_document_analysis(self, project_id: str, doc_id: str, analysis: Dict[str, Any]) -> None:
        await self._init_db()
        name = analysis.get("name", doc_id)
        role = analysis.get("role", "evidence")
        text = analysis.get("text", "")
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO documents (project_id, doc_id, name, role, text, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, doc_id) DO UPDATE SET
                    name = excluded.name,
                    role = excluded.role,
                    text = excluded.text,
                    data_json = excluded.data_json
                """,
                (project_id, doc_id, name, role, text, json.dumps(analysis)),
            )
            await db.commit()

    async def get_document(self, project_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM documents WHERE project_id = ? AND doc_id = ?",
                (project_id, doc_id),
            ) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data_json"]) if row and row["data_json"] else None

    async def list_documents(self, project_id: str, role: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if role:
                query = "SELECT data_json FROM documents WHERE project_id = ? AND role = ?"
                params = (project_id, role)
            else:
                query = "SELECT data_json FROM documents WHERE project_id = ?"
                params = (project_id,)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def delete_document(self, project_id: str, doc_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            res = await db.execute(
                "DELETE FROM documents WHERE project_id = ? AND (doc_id = ? OR name = ?)",
                (project_id, doc_id, doc_id),
            )
            await db.commit()
            return res.rowcount > 0

    # ── Matches ──────────────────────────────────────────────


    async def save_matches(self, project_id: str, matches: List[Dict[str, Any]]) -> None:
        await self._init_db()
        async with self._connect() as db:
            for match in matches:
                req_id = match["requirement_id"]
                await db.execute(
                    """
                    INSERT INTO matches (project_id, requirement_id, status, confidence, reasoning, data_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, requirement_id) DO UPDATE SET
                        status = excluded.status,
                        confidence = excluded.confidence,
                        reasoning = excluded.reasoning,
                        data_json = excluded.data_json
                    """,
                    (
                        project_id,
                        req_id,
                        match.get("status", "UNKNOWN"),
                        match.get("confidence", 0.0),
                        match.get("reasoning", ""),
                        json.dumps(match),
                    ),
                )
            await db.commit()

    async def get_matches(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM matches WHERE project_id = ? ORDER BY requirement_id ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    # ── Issues / Gaps ────────────────────────────────────────

    async def save_issues(self, project_id: str, issues: List[Dict[str, Any]]) -> None:
        await self._init_db()
        async with self._connect() as db:
            for issue in issues:
                gap_id = issue["gap_id"]
                await db.execute(
                    """
                    INSERT INTO issues (project_id, gap_id, gap_type, severity, description, data_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, gap_id) DO UPDATE SET
                        gap_type = excluded.gap_type,
                        severity = excluded.severity,
                        description = excluded.description,
                        data_json = excluded.data_json
                    """,
                    (
                        project_id,
                        gap_id,
                        issue.get("gap_type", "missing_evidence"),
                        issue.get("severity", "MEDIUM"),
                        issue.get("description", ""),
                        json.dumps(issue),
                    ),
                )
            await db.commit()

    async def get_issues(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM issues WHERE project_id = ? ORDER BY gap_id ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    # ── Tasks ────────────────────────────────────────────────

    async def save_tasks(self, project_id: str, tasks: List[Dict[str, Any]]) -> None:
        await self._init_db()
        async with self._connect() as db:
            for task in tasks:
                task_id = task["task_id"]
                await db.execute(
                    """
                    INSERT INTO tasks (project_id, task_id, title, severity, required_action, status, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, task_id) DO UPDATE SET
                        title = excluded.title,
                        severity = excluded.severity,
                        required_action = excluded.required_action,
                        status = excluded.status,
                        data_json = excluded.data_json
                    """,
                    (
                        project_id,
                        task_id,
                        task.get("title", ""),
                        task.get("severity", "MEDIUM"),
                        task.get("required_action", ""),
                        task.get("status", "OPEN"),
                        json.dumps(task),
                    ),
                )
            await db.commit()

    async def get_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM tasks WHERE project_id = ? ORDER BY task_id ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def update_task_status(self, project_id: str, task_id: str, status: str) -> None:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM tasks WHERE project_id = ? AND task_id = ?",
                (project_id, task_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row["data_json"]:
                    task_data = json.loads(row["data_json"])
                    task_data["status"] = status
                    await db.execute(
                        "UPDATE tasks SET status = ?, data_json = ? WHERE project_id = ? AND task_id = ?",
                        (status, json.dumps(task_data), project_id, task_id),
                    )
                    await db.commit()

    # ── Agent Events ─────────────────────────────────────────

    async def add_event(self, project_id: str, event: Dict[str, Any]) -> str:
        await self._init_db()
        event_id = event.get("event_id") or str(uuid.uuid4())
        event["event_id"] = event_id
        timestamp = event.get("timestamp") or self._now()
        event["timestamp"] = timestamp

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO agent_events (event_id, project_id, type, tool, status, timestamp, summary, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    project_id,
                    event.get("type", "AGENT_EVENT"),
                    event.get("tool"),
                    event.get("status", "completed"),
                    timestamp,
                    event.get("summary", ""),
                    json.dumps(event),
                ),
            )
            await db.commit()
        return event_id

    async def get_events(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM agent_events WHERE project_id = ? ORDER BY timestamp ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    # ── Verification Runs (Immutable Historical Snapshots) ───

    async def save_verification_run(self, project_id: str, result: Dict[str, Any]) -> str:
        await self._init_db()
        timestamp = result.get("timestamp") or self._now()
        result["timestamp"] = timestamp

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT MAX(run_number) as max_num FROM verification_runs WHERE project_id = ?",
                (project_id,),
            ) as cursor:
                row = await cursor.fetchone()
                max_num = row["max_num"] if row and row["max_num"] is not None else 0
                next_run_number = max_num + 1

            run_number = result.get("run_number") or next_run_number
            run_id = result.get("run_id") or f"run_{run_number}"
            result["run_id"] = run_id
            result["run_number"] = run_number
            result["project_id"] = project_id

            try:
                await db.execute(
                    """
                    INSERT INTO verification_runs (project_id, run_id, run_number, timestamp, data_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (project_id, run_id, run_number, timestamp, json.dumps(result)),
                )
                await db.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Cannot overwrite immutable verification snapshot '{run_id}' "
                    f"for project '{project_id}'."
                ) from exc
        return run_id

    async def get_verification_run(self, project_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            run_num = int(run_id) if run_id.isdigit() else (int(run_id.replace("run_", "")) if run_id.startswith("run_") and run_id.replace("run_", "").isdigit() else None)
            if run_num is not None:
                query = "SELECT data_json FROM verification_runs WHERE project_id = ? AND (run_id = ? OR run_number = ?)"
                params = (project_id, run_id, run_num)
            else:
                query = "SELECT data_json FROM verification_runs WHERE project_id = ? AND run_id = ?"
                params = (project_id, run_id)

            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data_json"]) if row and row["data_json"] else None

    async def list_verification_runs(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM verification_runs WHERE project_id = ? ORDER BY run_number ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def get_latest_verification(self, project_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM verification_runs WHERE project_id = ? ORDER BY run_number DESC, timestamp DESC LIMIT 1",
                (project_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data_json"]) if row and row["data_json"] else None

    # ── Combined Results ─────────────────────────────────────

    async def get_results(self, project_id: str) -> Optional[Dict[str, Any]]:
        project = await self.get_project(project_id)
        if not project:
            return None
        matches = await self.get_matches(project_id)
        issues = await self.get_issues(project_id)
        tasks = await self.get_tasks(project_id)
        requirements = await self.get_requirements(project_id)
        verification = await self.get_latest_verification(project_id)
        overrides = await self.list_auditor_overrides(project_id)
        return {
            "project": project,
            "requirements": requirements,
            "matches": matches,
            "issues": issues,
            "tasks": tasks,
            "latest_verification": verification,
            "auditor_overrides": overrides,
        }

    # ── Auditor Overrides & Notes ────────────────────────────

    async def save_auditor_override(self, project_id: str, requirement_id: str, override_data: Dict[str, Any]) -> str:
        await self._init_db()
        override_id = override_data.get("override_id") or str(uuid.uuid4())
        now = self._now()
        override_data["override_id"] = override_id
        override_data["project_id"] = project_id
        override_data["requirement_id"] = requirement_id
        if "created_at" not in override_data:
            override_data["created_at"] = now
        override_data["updated_at"] = now

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO auditor_overrides (
                    override_id, project_id, requirement_id, original_ai_status,
                    overridden_status, auditor_reason, auditor_note, created_at, updated_at, data_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, requirement_id) DO UPDATE SET
                    overridden_status = excluded.overridden_status,
                    auditor_reason = excluded.auditor_reason,
                    auditor_note = excluded.auditor_note,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json
                """,
                (
                    override_id,
                    project_id,
                    requirement_id,
                    override_data.get("original_ai_status", "UNKNOWN"),
                    override_data.get("overridden_status", "SATISFIED"),
                    override_data.get("auditor_reason", ""),
                    override_data.get("auditor_note", ""),
                    override_data["created_at"],
                    override_data["updated_at"],
                    json.dumps(override_data),
                ),
            )
            await db.commit()
        return override_id

    async def get_auditor_override(self, project_id: str, requirement_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM auditor_overrides WHERE project_id = ? AND requirement_id = ?",
                (project_id, requirement_id),
            ) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data_json"]) if row and row["data_json"] else None

    async def list_auditor_overrides(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM auditor_overrides WHERE project_id = ? ORDER BY requirement_id ASC",
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def delete_auditor_override(self, project_id: str, requirement_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM auditor_overrides WHERE project_id = ? AND requirement_id = ?",
                (project_id, requirement_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def save_auditor_note(self, project_id: str, requirement_id: str, note_data: Dict[str, Any]) -> str:
        await self._init_db()
        note_id = note_data.get("note_id") or str(uuid.uuid4())
        now = self._now()
        note_data["note_id"] = note_id
        note_data["project_id"] = project_id
        note_data["requirement_id"] = requirement_id
        if "created_at" not in note_data:
            note_data["created_at"] = now
        note_data["updated_at"] = now

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO auditor_notes (note_id, project_id, requirement_id, note_text, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    note_text = excluded.note_text,
                    updated_at = excluded.updated_at,
                    data_json = excluded.data_json
                """,
                (
                    note_id,
                    project_id,
                    requirement_id,
                    note_data.get("note_text", ""),
                    note_data["created_at"],
                    note_data["updated_at"],
                    json.dumps(note_data),
                ),
            )
            await db.commit()
        return note_id

    async def list_auditor_notes(self, project_id: str, requirement_id: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if requirement_id:
                query = "SELECT data_json FROM auditor_notes WHERE project_id = ? AND requirement_id = ? ORDER BY created_at DESC"
                params = (project_id, requirement_id)
            else:
                query = "SELECT data_json FROM auditor_notes WHERE project_id = ? ORDER BY created_at DESC"
                params = (project_id,)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def delete_auditor_note(self, project_id: str, note_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM auditor_notes WHERE project_id = ? AND note_id = ?",
                (project_id, note_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # ── Remediation Uploads ──────────────────────────────────

    async def save_remediation_upload(self, project_id: str, task_id: str, upload_data: Dict[str, Any]) -> str:
        await self._init_db()
        upload_id = upload_data.get("upload_id") or str(uuid.uuid4())
        now = self._now()
        upload_data["upload_id"] = upload_id
        upload_data["project_id"] = project_id
        upload_data["task_id"] = task_id
        if "uploaded_at" not in upload_data:
            upload_data["uploaded_at"] = now
        if "upload_status" not in upload_data:
            upload_data["upload_status"] = "PENDING_VERIFICATION"

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO remediation_uploads (
                    upload_id, project_id, task_id, requirement_id,
                    filename, stored_filename, file_type, file_size,
                    uploaded_at, upload_status, description, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(upload_id) DO UPDATE SET
                    upload_status = excluded.upload_status,
                    description = excluded.description,
                    data_json = excluded.data_json
                """,
                (
                    upload_id,
                    project_id,
                    task_id,
                    upload_data.get("requirement_id", ""),
                    upload_data.get("filename", ""),
                    upload_data.get("stored_filename", ""),
                    upload_data.get("file_type", ""),
                    upload_data.get("file_size", 0),
                    upload_data["uploaded_at"],
                    upload_data["upload_status"],
                    upload_data.get("description", ""),
                    json.dumps(upload_data),
                ),
            )
            await db.commit()
        return upload_id

    async def get_remediation_upload(self, project_id: str, upload_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT data_json FROM remediation_uploads WHERE project_id = ? AND upload_id = ?",
                (project_id, upload_id),
            ) as cursor:
                row = await cursor.fetchone()
                return json.loads(row["data_json"]) if row and row["data_json"] else None

    async def list_remediation_uploads(self, project_id: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if task_id:
                query = "SELECT data_json FROM remediation_uploads WHERE project_id = ? AND task_id = ? ORDER BY uploaded_at DESC"
                params = (project_id, task_id)
            else:
                query = "SELECT data_json FROM remediation_uploads WHERE project_id = ? ORDER BY uploaded_at DESC"
                params = (project_id,)
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [json.loads(r["data_json"]) for r in rows if r["data_json"]]

    async def delete_remediation_upload(self, project_id: str, upload_id: str) -> bool:
        await self._init_db()
        # Fetch stored_filename so we can delete the physical file
        record = await self.get_remediation_upload(project_id, upload_id)
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM remediation_uploads WHERE project_id = ? AND upload_id = ?",
                (project_id, upload_id),
            )
            await db.commit()
            deleted = cursor.rowcount > 0

        # Remove physical file if the record existed
        if deleted and record:
            stored = record.get("stored_filename", "")
            if stored and os.path.isfile(stored):
                try:
                    os.remove(stored)
                except OSError:
                    pass  # Log but don't raise; DB row is already gone

        return deleted

    # ── Audit Events (Immutable / Append-Only) ───────────────

    async def save_audit_event(self, project_id: str, event_data: Dict[str, Any]) -> str:
        await self._init_db()
        event_id = event_data.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"
        now = self._now()
        ts = event_data.get("timestamp") or now
        created_at = event_data.get("created_at") or now

        actor_type = event_data.get("actor_type", "SYSTEM").upper()
        severity = event_data.get("severity", "INFO").upper()
        event_type = event_data.get("event_type", "UNKNOWN").upper()
        summary = event_data.get("summary", "")
        description = event_data.get("description", "")
        actor_id = event_data.get("actor_id")
        req_id = event_data.get("requirement_id")
        run_id = event_data.get("run_id")
        task_id = event_data.get("task_id")
        doc_id = event_data.get("document_id")
        upload_id = event_data.get("upload_id")

        meta = event_data.get("metadata") or {}
        meta_json = json.dumps(meta) if isinstance(meta, dict) else (meta or "{}")

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO audit_events (
                    event_id, project_id, timestamp, event_type,
                    actor_type, actor_id, requirement_id, run_id,
                    task_id, document_id, upload_id, severity,
                    summary, description, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, project_id, ts, event_type,
                    actor_type, actor_id, req_id, run_id,
                    task_id, doc_id, upload_id, severity,
                    summary, description, meta_json, created_at
                )
            )
            await db.commit()

        return event_id

    async def get_audit_event(self, project_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM audit_events WHERE project_id = ? AND event_id = ?",
                (project_id, event_id),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._format_audit_row(dict(row))

    async def list_audit_events(
        self,
        project_id: str,
        event_type: Optional[str] = None,
        actor_type: Optional[str] = None,
        severity: Optional[str] = None,
        requirement_id: Optional[str] = None,
        run_id: Optional[str] = None,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        await self._init_db()
        conditions = ["project_id = ?"]
        params: List[Any] = [project_id]

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.upper())
        if actor_type:
            conditions.append("actor_type = ?")
            params.append(actor_type.upper())
        if severity:
            conditions.append("severity = ?")
            params.append(severity.upper())
        if requirement_id:
            conditions.append("requirement_id = ?")
            params.append(requirement_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if from_timestamp:
            conditions.append("timestamp >= ?")
            params.append(from_timestamp)
        if to_timestamp:
            conditions.append("timestamp <= ?")
            params.append(to_timestamp)

        query = f"""
            SELECT * FROM audit_events
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC, rowid DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [self._format_audit_row(dict(r)) for r in rows]

    async def count_audit_events(
        self,
        project_id: str,
        event_type: Optional[str] = None,
        actor_type: Optional[str] = None,
        severity: Optional[str] = None,
        requirement_id: Optional[str] = None,
        run_id: Optional[str] = None,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
    ) -> int:
        await self._init_db()
        conditions = ["project_id = ?"]
        params: List[Any] = [project_id]

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.upper())
        if actor_type:
            conditions.append("actor_type = ?")
            params.append(actor_type.upper())
        if severity:
            conditions.append("severity = ?")
            params.append(severity.upper())
        if requirement_id:
            conditions.append("requirement_id = ?")
            params.append(requirement_id)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if from_timestamp:
            conditions.append("timestamp >= ?")
            params.append(from_timestamp)
        if to_timestamp:
            conditions.append("timestamp <= ?")
            params.append(to_timestamp)

        query = f"""
            SELECT COUNT(*) AS total FROM audit_events
            WHERE {' AND '.join(conditions)}
        """
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                return row["total"] if row else 0

    @staticmethod
    def _format_audit_row(row: Dict[str, Any]) -> Dict[str, Any]:
        meta_json = row.pop("metadata_json", "{}")
        try:
            row["metadata"] = json.loads(meta_json) if meta_json else {}
        except Exception:
            row["metadata"] = {}
        return row

    # ── Users & Authentication ───────────────────────────────

    async def create_user(self, user_data: Dict[str, Any]) -> str:
        await self._init_db()
        user_id = user_data.get("user_id") or f"user_{uuid.uuid4().hex[:12]}"
        now = self._now()
        email = user_data["email"].strip().lower()
        name = user_data.get("name", "").strip()
        password_hash = user_data["password_hash"]
        is_active = 1 if user_data.get("is_active", True) else 0

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO users (user_id, email, name, password_hash, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, name, password_hash, is_active, now, now),
            )
            await db.commit()
        return user_id

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, email, name, password_hash, is_active, created_at, updated_at FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                data["is_active"] = bool(data["is_active"])
                return data

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, email, name, password_hash, is_active, created_at, updated_at FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                data["is_active"] = bool(data["is_active"])
                return data

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self._init_db()
        allowed = {}
        if "name" in updates:
            allowed["name"] = updates["name"].strip()
        if "password_hash" in updates:
            allowed["password_hash"] = updates["password_hash"]
        if "is_active" in updates:
            allowed["is_active"] = 1 if updates["is_active"] else 0
        if not allowed:
            return await self.get_user_by_id(user_id)

        allowed["updated_at"] = self._now()
        set_clauses = [f"{k} = ?" for k in allowed.keys()]
        params = list(allowed.values())
        params.append(user_id)

        async with self._connect() as db:
            await db.execute(
                f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = ?",
                tuple(params),
            )
            await db.commit()
        return await self.get_user_by_id(user_id)

    async def list_users(self) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, email, name, is_active, created_at, updated_at FROM users ORDER BY created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    d["is_active"] = bool(d["is_active"])
                    results.append(d)
                return results

    async def count_users(self) -> int:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) AS total FROM users") as cursor:
                row = await cursor.fetchone()
                return row["total"] if row else 0

    # ── Project Members (RBAC) ───────────────────────────────

    async def add_project_member(self, project_id: str, user_id: str, role: str) -> str:
        await self._init_db()
        membership_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = self._now()
        role = role.upper()

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO project_members (membership_id, project_id, user_id, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, user_id) DO UPDATE SET
                    role = excluded.role,
                    updated_at = excluded.updated_at
                """,
                (membership_id, project_id, user_id, role, now, now),
            )
            await db.commit()
        return membership_id

    async def get_project_member(self, project_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT m.membership_id, m.project_id, m.user_id, m.role, m.created_at, m.updated_at,
                       u.email, u.name, u.is_active
                FROM project_members m
                LEFT JOIN users u ON m.user_id = u.user_id
                WHERE m.project_id = ? AND m.user_id = ?
                """,
                (project_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                if "is_active" in data and data["is_active"] is not None:
                    data["is_active"] = bool(data["is_active"])
                return data

    async def list_project_members(self, project_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT m.membership_id, m.project_id, m.user_id, m.role, m.created_at, m.updated_at,
                       u.email, u.name, u.is_active
                FROM project_members m
                LEFT JOIN users u ON m.user_id = u.user_id
                WHERE m.project_id = ?
                ORDER BY m.created_at ASC
                """,
                (project_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    if "is_active" in d and d["is_active"] is not None:
                        d["is_active"] = bool(d["is_active"])
                    results.append(d)
                return results

    async def update_project_member_role(self, project_id: str, user_id: str, role: str) -> bool:
        await self._init_db()
        now = self._now()
        async with self._connect() as db:
            cursor = await db.execute(
                "UPDATE project_members SET role = ?, updated_at = ? WHERE project_id = ? AND user_id = ?",
                (role.upper(), now, project_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def remove_project_member(self, project_id: str, user_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM project_members WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT p.*, m.role, m.created_at AS joined_at
                FROM projects p
                JOIN project_members m ON p.project_id = m.project_id
                WHERE m.user_id = ?
                ORDER BY p.created_at DESC
                """,
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    row_dict = dict(r)
                    meta = json.loads(row_dict.get("metadata_json") or "{}") if row_dict.get("metadata_json") else {}
                    row_dict["metadata"] = meta
                    results.append(row_dict)
                return results

    # ── Sessions (Server-side Revocation & Tracking) ─────────

    async def create_session(self, session_data: Dict[str, Any]) -> str:
        await self._init_db()
        session_id = session_data.get("session_id") or str(uuid.uuid4())
        now = self._now()
        session_data["session_id"] = session_id
        session_data.setdefault("created_at", now)
        session_data.setdefault("last_active", now)
        session_data.setdefault("is_revoked", False)
        async with self._connect() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, user_id, token_hash, created_at, expires_at, is_revoked, revoked_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session_data["user_id"],
                    session_data["token_hash"],
                    session_data["created_at"],
                    session_data["expires_at"],
                    1 if session_data["is_revoked"] else 0,
                    session_data.get("revoked_at"),
                    session_data["last_active"],
                ),
            )
            await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                d["is_revoked"] = bool(d["is_revoked"])
                return d

    async def revoke_session(self, session_id: str) -> bool:
        await self._init_db()
        now = self._now()
        async with self._connect() as db:
            res = await db.execute(
                "UPDATE sessions SET is_revoked = 1, revoked_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            await db.commit()
            return res.rowcount > 0

    async def revoke_user_sessions(self, user_id: str) -> bool:
        await self._init_db()
        now = self._now()
        async with self._connect() as db:
            res = await db.execute(
                "UPDATE sessions SET is_revoked = 1, revoked_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            await db.commit()
            return res.rowcount > 0

    # ── Frameworks & Framework Requirements ──────────────────

    async def create_framework(self, framework_data: Dict[str, Any], requirements: List[Dict[str, Any]]) -> str:
        await self._init_db()
        fw_id = framework_data.get("framework_id") or str(uuid.uuid4())
        now = self._now()
        framework_data["framework_id"] = fw_id
        framework_data["created_at"] = framework_data.get("created_at") or now
        framework_data["updated_at"] = now
        framework_data["requirement_count"] = len(requirements)

        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO frameworks (
                    framework_id, project_id, name, version, description,
                    source, status, requirement_count, created_by,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE SET
                    description = excluded.description,
                    source = excluded.source,
                    status = excluded.status,
                    requirement_count = excluded.requirement_count,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    fw_id,
                    framework_data.get("project_id"),
                    framework_data["name"],
                    framework_data.get("version", "1.0"),
                    framework_data.get("description", ""),
                    framework_data.get("source", ""),
                    framework_data.get("status", "ACTIVE"),
                    len(requirements),
                    framework_data.get("created_by", "system"),
                    framework_data["created_at"],
                    now,
                    json.dumps(framework_data),
                ),
            )

            # Insert requirements
            for req in requirements:
                req_id = req.get("requirement_id") or req.get("external_id")
                await db.execute(
                    """
                    INSERT INTO framework_requirements (
                        framework_id, requirement_id, title, description,
                        category, severity, priority, guidance,
                        source_reference, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(framework_id, requirement_id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        category = excluded.category,
                        severity = excluded.severity,
                        priority = excluded.priority,
                        guidance = excluded.guidance,
                        source_reference = excluded.source_reference,
                        data_json = excluded.data_json
                    """,
                    (
                        fw_id,
                        req_id,
                        req["title"],
                        req["description"],
                        req.get("category", "General"),
                        req.get("severity", "MEDIUM"),
                        req.get("priority", "MEDIUM"),
                        req.get("guidance", ""),
                        req.get("source_reference", ""),
                        json.dumps(req),
                    ),
                )

            await db.commit()
        return fw_id

    async def get_framework(self, framework_id: str) -> Optional[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM frameworks WHERE framework_id = ?", (framework_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                meta = json.loads(d.get("metadata_json") or "{}")
                return {**meta, **d}

    async def list_frameworks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if project_id:
                query = "SELECT * FROM frameworks WHERE project_id IS NULL OR project_id = ? ORDER BY created_at DESC"
                params = (project_id,)
            else:
                query = "SELECT * FROM frameworks ORDER BY created_at DESC"
                params = ()

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    meta = json.loads(d.get("metadata_json") or "{}")
                    results.append({**meta, **d})
                return results

    async def get_framework_requirements(self, framework_id: str) -> List[Dict[str, Any]]:
        await self._init_db()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM framework_requirements WHERE framework_id = ? ORDER BY requirement_id ASC",
                (framework_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    meta = json.loads(d.get("data_json") or "{}")
                    results.append({**meta, **d})
                return results

    async def update_framework_status(self, framework_id: str, status: str) -> bool:
        await self._init_db()
        now = self._now()
        async with self._connect() as db:
            res = await db.execute(
                "UPDATE frameworks SET status = ?, updated_at = ? WHERE framework_id = ?",
                (status, now, framework_id),
            )
            await db.commit()
            return res.rowcount > 0

    async def delete_framework(self, framework_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            await db.execute("DELETE FROM framework_requirements WHERE framework_id = ?", (framework_id,))
            res = await db.execute("DELETE FROM frameworks WHERE framework_id = ?", (framework_id,))
            await db.commit()
            return res.rowcount > 0

    async def is_framework_referenced_in_runs(self, framework_id: str) -> bool:
        await self._init_db()
        async with self._connect() as db:
            async with db.execute(
                "SELECT COUNT(*) FROM verification_runs WHERE data_json LIKE ?",
                (f"%{framework_id}%",),
            ) as cursor:
                row = await cursor.fetchone()
                return (row[0] if row else 0) > 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()



# Firestore Implementation (Cloud / Optional)
# ─────────────────────────────────────────────────────────────

class FirestoreStorageService(StorageInterface):
    """Firestore implementation for Google Cloud production deployment."""

    USER_ID = "demo-user"

    def __init__(self, project_id: Optional[str] = None):
        from google.cloud import firestore
        self._db = firestore.AsyncClient(project=project_id or os.environ.get("GOOGLE_CLOUD_PROJECT"))

    async def create_project(self, project_data: Dict[str, Any]) -> str:
        ref = self._db.collection("projects").document()
        project_data["project_id"] = ref.id
        project_data["user_id"] = self.USER_ID
        now = datetime.now(timezone.utc).isoformat()
        project_data["created_at"] = now
        project_data["updated_at"] = now
        await ref.set(project_data)
        return ref.id

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        ref = self._db.collection("projects").document(project_id)
        doc = await ref.get()
        return doc.to_dict() if doc.exists else None

    async def update_project(self, project_id: str, updates: Dict[str, Any]) -> None:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._db.collection("projects").document(project_id).update(updates)

    async def list_projects(self) -> List[Dict[str, Any]]:
        from google.cloud import firestore
        query = (
            self._db.collection("projects")
            .where("user_id", "==", self.USER_ID)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(50)
        )
        docs = await query.get()
        return [doc.to_dict() for doc in docs]

    async def delete_project(self, project_id: str) -> bool:
        ref = self._db.collection("projects").document(project_id)
        await ref.delete()
        return True

    async def save_requirements(self, project_id: str, requirements: List[Dict[str, Any]]) -> None:

        batch = self._db.batch()
        col = self._db.collection("projects").document(project_id).collection("requirements")
        for req in requirements:
            ref = col.document(req["requirement_id"])
            batch.set(ref, req)
        await batch.commit()

    async def get_requirements(self, project_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("requirements")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def save_document_analysis(self, project_id: str, doc_id: str, analysis: Dict[str, Any]) -> None:
        ref = (
            self._db.collection("projects")
            .document(project_id)
            .collection("documents")
            .document(doc_id)
        )
        await ref.set(analysis)

    async def get_document(self, project_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("documents")
        doc = await col.document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    async def list_documents(self, project_id: str, role: Optional[str] = None) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("documents")
        if role:
            docs = await col.where("role", "==", role).get()
        else:
            docs = await col.get()
        return [d.to_dict() for d in docs]

    async def delete_document(self, project_id: str, doc_id: str) -> bool:
        col = self._db.collection("projects").document(project_id).collection("documents")
        await col.document(doc_id).delete()
        return True

    async def save_issues(self, project_id: str, issues: List[Dict[str, Any]]) -> None:

        batch = self._db.batch()
        col = self._db.collection("projects").document(project_id).collection("issues")
        for issue in issues:
            ref = col.document(issue["gap_id"])
            batch.set(ref, issue)
        await batch.commit()

    async def get_issues(self, project_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("issues")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def save_tasks(self, project_id: str, tasks: List[Dict[str, Any]]) -> None:
        batch = self._db.batch()
        col = self._db.collection("projects").document(project_id).collection("tasks")
        for task in tasks:
            ref = col.document(task["task_id"])
            batch.set(ref, task)
        await batch.commit()

    async def get_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("tasks")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def update_task_status(self, project_id: str, task_id: str, status: str) -> None:
        ref = (
            self._db.collection("projects")
            .document(project_id)
            .collection("tasks")
            .document(task_id)
        )
        await ref.update({"status": status})

    async def save_matches(self, project_id: str, matches: List[Dict[str, Any]]) -> None:
        batch = self._db.batch()
        col = self._db.collection("projects").document(project_id).collection("matches")
        for match in matches:
            ref = col.document(match["requirement_id"])
            batch.set(ref, match)
        await batch.commit()

    async def get_matches(self, project_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("matches")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def add_event(self, project_id: str, event: Dict[str, Any]) -> str:
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("agent_events")
        )
        ref = col.document()
        event["event_id"] = ref.id
        await ref.set(event)
        return ref.id

    async def get_events(self, project_id: str) -> List[Dict[str, Any]]:
        from google.cloud import firestore
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("agent_events")
        )
        query = col.order_by("timestamp", direction=firestore.Query.ASCENDING)
        docs = await query.get()
        return [d.to_dict() for d in docs]

    async def save_verification_run(self, project_id: str, result: Dict[str, Any]) -> str:
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("verification_runs")
        )
        ref = col.document()
        result["run_id"] = ref.id
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        await ref.set(result)
        return ref.id

    async def get_verification_run(self, project_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("verification_runs")
        )
        doc = await col.document(run_id).get()
        return doc.to_dict() if doc.exists else None

    async def list_verification_runs(self, project_id: str) -> List[Dict[str, Any]]:
        from google.cloud import firestore
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("verification_runs")
        )
        query = col.order_by("run_number", direction=firestore.Query.ASCENDING)
        docs = await query.get()
        return [d.to_dict() for d in docs]

    async def get_latest_verification(self, project_id: str) -> Optional[Dict[str, Any]]:
        from google.cloud import firestore
        col = (
            self._db.collection("projects")
            .document(project_id)
            .collection("verification_runs")
        )
        query = col.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1)
        docs = await query.get()
        if docs:
            return docs[0].to_dict()
        return None

    async def get_results(self, project_id: str) -> Optional[Dict[str, Any]]:
        project = await self.get_project(project_id)
        if not project:
            return None
        matches = await self.get_matches(project_id)
        issues = await self.get_issues(project_id)
        tasks = await self.get_tasks(project_id)
        requirements = await self.get_requirements(project_id)
        verification = await self.get_latest_verification(project_id)
        overrides = await self.list_auditor_overrides(project_id)
        return {
            "project": project,
            "requirements": requirements,
            "matches": matches,
            "issues": issues,
            "tasks": tasks,
            "latest_verification": verification,
            "auditor_overrides": overrides,
        }

    async def save_auditor_override(self, project_id: str, requirement_id: str, override_data: Dict[str, Any]) -> str:
        override_id = override_data.get("override_id") or str(uuid.uuid4())
        ref = self._db.collection("projects").document(project_id).collection("overrides").document(requirement_id)
        override_data["override_id"] = override_id
        override_data["project_id"] = project_id
        override_data["requirement_id"] = requirement_id
        now = datetime.now(timezone.utc).isoformat()
        if "created_at" not in override_data:
            override_data["created_at"] = now
        override_data["updated_at"] = now
        await ref.set(override_data)
        return override_id

    async def get_auditor_override(self, project_id: str, requirement_id: str) -> Optional[Dict[str, Any]]:
        ref = self._db.collection("projects").document(project_id).collection("overrides").document(requirement_id)
        doc = await ref.get()
        return doc.to_dict() if doc.exists else None

    async def list_auditor_overrides(self, project_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("overrides")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def delete_auditor_override(self, project_id: str, requirement_id: str) -> bool:
        ref = self._db.collection("projects").document(project_id).collection("overrides").document(requirement_id)
        doc = await ref.get()
        if doc.exists:
            await ref.delete()
            return True
        return False

    async def save_auditor_note(self, project_id: str, requirement_id: str, note_data: Dict[str, Any]) -> str:
        note_id = note_data.get("note_id") or str(uuid.uuid4())
        ref = self._db.collection("projects").document(project_id).collection("notes").document(note_id)
        note_data["note_id"] = note_id
        note_data["project_id"] = project_id
        note_data["requirement_id"] = requirement_id
        now = datetime.now(timezone.utc).isoformat()
        if "created_at" not in note_data:
            note_data["created_at"] = now
        note_data["updated_at"] = now
        await ref.set(note_data)
        return note_id

    async def list_auditor_notes(self, project_id: str, requirement_id: Optional[str] = None) -> List[Dict[str, Any]]:
        col = self._db.collection("projects").document(project_id).collection("notes")
        if requirement_id:
            docs = await col.where("requirement_id", "==", requirement_id).get()
        else:
            docs = await col.get()
        return [d.to_dict() for d in docs]

    async def delete_auditor_note(self, project_id: str, note_id: str) -> bool:
        ref = self._db.collection("projects").document(project_id).collection("notes").document(note_id)
        doc = await ref.get()
        if doc.exists:
            await ref.delete()
            return True
        return False

    # ── Sessions (Cloud stubs) ───────────────────────────────
    async def create_session(self, session_data: Dict[str, Any]) -> str:
        session_id = session_data.get("session_id") or str(uuid.uuid4())
        session_data["session_id"] = session_id
        ref = self._db.collection("sessions").document(session_id)
        await ref.set(session_data)
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        ref = self._db.collection("sessions").document(session_id)
        doc = await ref.get()
        return doc.to_dict() if doc.exists else None

    async def revoke_session(self, session_id: str) -> bool:
        ref = self._db.collection("sessions").document(session_id)
        doc = await ref.get()
        if doc.exists:
            await ref.update({"is_revoked": True})
            return True
        return False

    async def revoke_user_sessions(self, user_id: str) -> bool:
        return True

    # ── Frameworks (Cloud stubs) ─────────────────────────────
    async def create_framework(self, framework_data: Dict[str, Any], requirements: List[Dict[str, Any]]) -> str:
        fw_id = framework_data.get("framework_id") or str(uuid.uuid4())
        framework_data["framework_id"] = fw_id
        ref = self._db.collection("frameworks").document(fw_id)
        await ref.set(framework_data)
        return fw_id

    async def get_framework(self, framework_id: str) -> Optional[Dict[str, Any]]:
        ref = self._db.collection("frameworks").document(framework_id)
        doc = await ref.get()
        return doc.to_dict() if doc.exists else None

    async def list_frameworks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        col = self._db.collection("frameworks")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def get_framework_requirements(self, framework_id: str) -> List[Dict[str, Any]]:
        col = self._db.collection("frameworks").document(framework_id).collection("requirements")
        docs = await col.get()
        return [d.to_dict() for d in docs]

    async def update_framework_status(self, framework_id: str, status: str) -> bool:
        ref = self._db.collection("frameworks").document(framework_id)
        await ref.update({"status": status})
        return True

    async def delete_framework(self, framework_id: str) -> bool:
        ref = self._db.collection("frameworks").document(framework_id)
        await ref.delete()
        return True

    async def is_framework_referenced_in_runs(self, framework_id: str) -> bool:
        return False




# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

_storage_instance: Optional[StorageInterface] = None


def get_storage(db_path: str = "complyflow.db") -> StorageInterface:
    """
    Get the configured storage service.
    Defaults to SQLite for local development.
    Uses Firestore when USE_FIRESTORE is explicitly set to true.
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    use_firestore = os.environ.get("USE_FIRESTORE", "false").lower() == "true"
    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if use_firestore and gcp_project:
        try:
            _storage_instance = FirestoreStorageService(project_id=gcp_project)
            return _storage_instance
        except Exception as e:
            # Graceful fallback to SQLite
            _storage_instance = SQLiteStorageService(db_path=db_path)
            return _storage_instance
    else:
        _storage_instance = SQLiteStorageService(db_path=db_path)
        return _storage_instance
