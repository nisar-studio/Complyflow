"""
Migration 001: Initial Schema

Documents the complete v1.0.0 ComplyFlow schema as the migration baseline.
Uses CREATE TABLE IF NOT EXISTS so it is safe for:
  - Fresh databases (creates all tables)
  - Existing v1.0.0 databases (no-ops on existing tables)

This migration does NOT modify or destroy any existing data.
"""
from __future__ import annotations

import os

import aiosqlite

MIGRATION_ID = "001"
MIGRATION_NAME = "initial_schema"


async def up(db: aiosqlite.Connection) -> None:
    """Create all v1.0.0 tables if they don't exist."""

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
        )
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
        )
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
        )
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
        )
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
        )
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
        )
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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_proj ON agent_events (project_id, timestamp)"
    )

    # 8. Verification Runs (Immutable Point-in-Time Snapshots)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS verification_runs (
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            run_number INTEGER NOT NULL DEFAULT 1,
            timestamp TEXT NOT NULL,
            data_json TEXT NOT NULL,
            PRIMARY KEY (project_id, run_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_vr_proj_num ON verification_runs (project_id, run_number)"
    )

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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_overrides_proj ON auditor_overrides (project_id, requirement_id)"
    )

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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_notes_proj ON auditor_notes (project_id, requirement_id)"
    )

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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_remed_uploads_proj_task ON remediation_uploads (project_id, task_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_remed_uploads_proj_req ON remediation_uploads (project_id, requirement_id)"
    )

    # 12. Immutable Audit Log Table
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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_proj_time ON audit_events (project_id, timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_proj_type ON audit_events (project_id, event_type)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_proj_req ON audit_events (project_id, requirement_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_proj_run ON audit_events (project_id, run_id)"
    )

    # 13. Users (Authentication & Accounts)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")

    # 14. Project Members (Role-Based Access Control)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS project_members (
            membership_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, user_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_members_proj ON project_members (project_id)"
    )

    # 15. Sessions (Server-side Revocation & Tracking)
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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions (token_hash)"
    )

    # 16. Frameworks
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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_frameworks_name_ver ON frameworks (name, version)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_frameworks_proj ON frameworks (project_id)"
    )

    # 17. Framework Requirements
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
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_fw_reqs_id ON framework_requirements (framework_id, requirement_id)"
    )

    # Seed default demo user for development only
    app_env = os.environ.get("APP_ENV", "development").lower()
    if app_env != "production":
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, email, name, password_hash, is_active, created_at, updated_at)
            VALUES ('demo-user', 'demo@complyflow.local', 'Compliance Auditor',
                    'pbkdf2_sha256$100000$default$default', 1,
                    '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        """)

    await db.commit()
