"""
test_upgrade_scenario.py — Integration test for v1.0.0 database upgrade

Tests:
1. Create a realistic v1.0.0 database with existing data
2. Run migration framework
3. Verify all original data preserved
4. Verify migration 002 adds expected columns/indexes
5. Re-run migration (idempotency)
6. Verify nothing duplicated or corrupted
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile

import pytest

from app.services.migration_service import run_pending_migrations, get_migration_status


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _create_v1_database(db_path: str):
    """Create a realistic v1.0.0 database with representative data."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            status TEXT NOT NULL, compliance_score REAL, overall_status TEXT,
            requirements_count INTEGER DEFAULT 0, documents_count INTEGER DEFAULT 0,
            issues_count INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}'
        );
        CREATE TABLE requirements (
            project_id TEXT NOT NULL, requirement_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, required_evidence TEXT, priority TEXT, source_reference TEXT,
            data_json TEXT, PRIMARY KEY (project_id, requirement_id)
        );
        CREATE TABLE documents (
            project_id TEXT NOT NULL, doc_id TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL, text TEXT, data_json TEXT, PRIMARY KEY (project_id, doc_id)
        );
        CREATE TABLE matches (
            project_id TEXT NOT NULL, requirement_id TEXT NOT NULL, status TEXT NOT NULL,
            confidence REAL, reasoning TEXT, data_json TEXT, PRIMARY KEY (project_id, requirement_id)
        );
        CREATE TABLE issues (
            project_id TEXT NOT NULL, gap_id TEXT NOT NULL, gap_type TEXT, severity TEXT,
            description TEXT, data_json TEXT, PRIMARY KEY (project_id, gap_id)
        );
        CREATE TABLE tasks (
            project_id TEXT NOT NULL, task_id TEXT NOT NULL, title TEXT, severity TEXT,
            required_action TEXT, status TEXT NOT NULL, data_json TEXT,
            PRIMARY KEY (project_id, task_id)
        );
        CREATE TABLE agent_events (
            event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, type TEXT NOT NULL,
            tool TEXT, status TEXT NOT NULL, timestamp TEXT NOT NULL, summary TEXT, data_json TEXT
        );
        CREATE INDEX idx_events_proj ON agent_events (project_id, timestamp);
        CREATE TABLE verification_runs (
            project_id TEXT NOT NULL, run_id TEXT NOT NULL, run_number INTEGER NOT NULL DEFAULT 1,
            timestamp TEXT NOT NULL, data_json TEXT NOT NULL, PRIMARY KEY (project_id, run_id)
        );
        CREATE INDEX idx_vr_proj_num ON verification_runs (project_id, run_number);
        CREATE TABLE auditor_overrides (
            override_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
            original_ai_status TEXT NOT NULL, overridden_status TEXT NOT NULL,
            auditor_reason TEXT NOT NULL, auditor_note TEXT DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, data_json TEXT,
            UNIQUE(project_id, requirement_id)
        );
        CREATE INDEX idx_overrides_proj ON auditor_overrides (project_id, requirement_id);
        CREATE TABLE auditor_notes (
            note_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
            note_text TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, data_json TEXT
        );
        CREATE INDEX idx_notes_proj ON auditor_notes (project_id, requirement_id);
        CREATE TABLE remediation_uploads (
            upload_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_id TEXT NOT NULL,
            requirement_id TEXT NOT NULL, filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
            file_type TEXT NOT NULL, file_size INTEGER NOT NULL, uploaded_at TEXT NOT NULL,
            upload_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
            description TEXT DEFAULT '', data_json TEXT
        );
        CREATE INDEX idx_remed_uploads_proj_task ON remediation_uploads (project_id, task_id);
        CREATE INDEX idx_remed_uploads_proj_req ON remediation_uploads (project_id, requirement_id);
        CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT,
            requirement_id TEXT, run_id TEXT, task_id TEXT, document_id TEXT, upload_id TEXT,
            severity TEXT NOT NULL, summary TEXT NOT NULL, description TEXT,
            metadata_json TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX idx_audit_proj_time ON audit_events (project_id, timestamp);
        CREATE INDEX idx_audit_proj_type ON audit_events (project_id, event_type);
        CREATE INDEX idx_audit_proj_req ON audit_events (project_id, requirement_id);
        CREATE INDEX idx_audit_proj_run ON audit_events (project_id, run_id);
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            password_hash TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_users_email ON users (email);
        CREATE TABLE project_members (
            membership_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, user_id TEXT NOT NULL,
            role TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(project_id, user_id)
        );
        CREATE INDEX idx_members_proj ON project_members (project_id);
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            is_revoked BOOLEAN NOT NULL DEFAULT 0, revoked_at TEXT, last_active TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE INDEX idx_sessions_user ON sessions (user_id);
        CREATE INDEX idx_sessions_token_hash ON sessions (token_hash);
        CREATE TABLE frameworks (
            framework_id TEXT PRIMARY KEY, project_id TEXT, name TEXT NOT NULL,
            version TEXT NOT NULL, description TEXT, source TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE', requirement_count INTEGER DEFAULT 0,
            created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}', UNIQUE(name, version)
        );
        CREATE INDEX idx_frameworks_name_ver ON frameworks (name, version);
        CREATE INDEX idx_frameworks_proj ON frameworks (project_id);
        CREATE TABLE framework_requirements (
            framework_id TEXT NOT NULL, requirement_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT NOT NULL, category TEXT DEFAULT 'General',
            severity TEXT DEFAULT 'MEDIUM', priority TEXT DEFAULT 'MEDIUM',
            guidance TEXT DEFAULT '', source_reference TEXT DEFAULT '', data_json TEXT,
            PRIMARY KEY (framework_id, requirement_id),
            FOREIGN KEY(framework_id) REFERENCES frameworks(framework_id) ON DELETE CASCADE
        );
        CREATE INDEX idx_fw_reqs_id ON framework_requirements (framework_id, requirement_id);

        -- Seed realistic data
        INSERT INTO users VALUES ('demo-user', 'demo@complyflow.local', 'Compliance Auditor',
            'pbkdf2_sha256$100000$default$default', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
        INSERT INTO users VALUES ('user_admin_abc', 'admin@novatech.com', 'NovaTech Admin',
            'pbkdf2_sha256$100000$abc$def', 1, '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');
        INSERT INTO users VALUES ('user_auditor_xyz', 'auditor@novatech.com', 'External Auditor',
            'pbkdf2_sha256$100000$xyz$ghi', 1, '2026-08-05T00:00:00Z', '2026-08-05T00:00:00Z');

        INSERT INTO projects VALUES ('proj_novatech', 'user_admin_abc', 'NovaTech Solutions Vendor Assessment',
            'ACTION_REQUIRED', 75.0, 'ACTION_REQUIRED', 4, 3, 2,
            '2026-08-01T00:00:00Z', '2026-08-15T00:00:00Z', '{}');
        INSERT INTO projects VALUES ('proj_acme', 'user_admin_abc', 'Acme Corp Certification',
            'READY', 100.0, 'READY', 3, 3, 0,
            '2026-07-01T00:00:00Z', '2026-07-30T00:00:00Z', '{}');

        INSERT INTO project_members VALUES ('mem_001', 'proj_novatech', 'user_admin_abc', 'ADMIN',
            '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z');
        INSERT INTO project_members VALUES ('mem_002', 'proj_novatech', 'user_auditor_xyz', 'AUDITOR',
            '2026-08-05T00:00:00Z', '2026-08-05T00:00:00Z');
        INSERT INTO project_members VALUES ('mem_003', 'proj_acme', 'user_admin_abc', 'ADMIN',
            '2026-07-01T00:00:00Z', '2026-07-01T00:00:00Z');

        INSERT INTO requirements VALUES ('proj_novatech', 'REQ-001', 'Insurance Certificate',
            'Valid liability insurance coverage', 'Certificate document', 'HIGH', 'ISO 27001 A.5.1',
            '{"requirement_id": "REQ-001", "title": "Insurance Certificate"}');
        INSERT INTO requirements VALUES ('proj_novatech', 'REQ-002', 'Data Processing Agreement',
            'Signed DPA with GDPR compliance', 'Signed agreement', 'HIGH', 'GDPR Art. 28',
            '{"requirement_id": "REQ-002", "title": "Data Processing Agreement"}');
        INSERT INTO requirements VALUES ('proj_novatech', 'REQ-003', 'Company Profile',
            'Accurate company registration details', 'Profile document', 'MEDIUM', 'Corporate',
            '{"requirement_id": "REQ-003", "title": "Company Profile"}');
        INSERT INTO requirements VALUES ('proj_novatech', 'REQ-004', 'Bank Reference',
            'Bank reference letter', 'Reference letter', 'MEDIUM', 'Financial',
            '{"requirement_id": "REQ-004", "title": "Bank Reference"}');

        INSERT INTO tasks VALUES ('proj_novatech', 'TASK-001', 'Upload insurance certificate',
            'HIGH', 'Upload valid insurance certificate', 'OPEN',
            '{"task_id": "TASK-001", "title": "Upload insurance certificate"}');
        INSERT INTO tasks VALUES ('proj_novatech', 'TASK-002', 'Sign DPA agreement',
            'MEDIUM', 'Sign data processing agreement', 'RESOLVED',
            '{"task_id": "TASK-002", "title": "Sign DPA agreement"}');
        INSERT INTO tasks VALUES ('proj_novatech', 'TASK-003', 'Correct company address',
            'LOW', 'Fix address mismatch in profile', 'OPEN',
            '{"task_id": "TASK-003", "title": "Correct company address"}');

        INSERT INTO matches VALUES ('proj_novatech', 'REQ-001', 'MISSING', 0.0,
            'No insurance certificate found in evidence',
            '{"requirement_id": "REQ-001", "status": "MISSING"}');
        INSERT INTO matches VALUES ('proj_novatech', 'REQ-002', 'SATISFIED', 0.95,
            'DPA found and verified in evidence',
            '{"requirement_id": "REQ-002", "status": "SATISFIED"}');
        INSERT INTO matches VALUES ('proj_novatech', 'REQ-003', 'PARTIAL', 0.6,
            'Address mismatch detected',
            '{"requirement_id": "REQ-003", "status": "PARTIAL"}');
        INSERT INTO matches VALUES ('proj_novatech', 'REQ-004', 'SATISFIED', 0.88,
            'Bank reference found',
            '{"requirement_id": "REQ-004", "status": "SATISFIED"}');

        INSERT INTO issues VALUES ('proj_novatech', 'GAP-001', 'missing_evidence', 'HIGH',
            'No insurance certificate provided',
            '{"gap_id": "GAP-001", "severity": "HIGH"}');
        INSERT INTO issues VALUES ('proj_novatech', 'GAP-002', 'conflict', 'MEDIUM',
            'Address mismatch between documents',
            '{"gap_id": "GAP-002", "severity": "MEDIUM"}');

        INSERT INTO audit_events VALUES ('evt_001', 'proj_novatech', '2026-08-01T10:00:00Z',
            'PROJECT_CREATED', 'AUDITOR', 'user_admin_abc', NULL, NULL, NULL, NULL, NULL,
            'INFO', 'Project NovaTech created', NULL, '{}', '2026-08-01T10:00:00Z');
        INSERT INTO audit_events VALUES ('evt_002', 'proj_novatech', '2026-08-01T10:05:00Z',
            'ANALYSIS_COMPLETED', 'AI_AGENT', NULL, NULL, 'run_1', NULL, NULL, NULL,
            'INFO', 'Analysis completed. Score: 75%', NULL,
            '{"compliance_score": 75.0}', '2026-08-01T10:05:00Z');
        INSERT INTO audit_events VALUES ('evt_003', 'proj_novatech', '2026-08-05T14:00:00Z',
            'AUDITOR_OVERRIDE_CREATED', 'AUDITOR', 'user_auditor_xyz', 'REQ-003', NULL, NULL, NULL, NULL,
            'INFO', 'Override on REQ-003: status set to SATISFIED', NULL,
            '{"requirement_id": "REQ-003"}', '2026-08-05T14:00:00Z');
        INSERT INTO audit_events VALUES ('evt_004', 'proj_acme', '2026-07-30T09:00:00Z',
            'ANALYSIS_COMPLETED', 'AI_AGENT', NULL, NULL, 'run_1', NULL, NULL, NULL,
            'INFO', 'Acme analysis complete. Score: 100%', NULL,
            '{"compliance_score": 100.0}', '2026-07-30T09:00:00Z');
    """)
    conn.commit()
    conn.close()


class TestV1UpgradeScenario:
    """Integration test: upgrade a v1.0.0 database to v1.1.0 migration framework."""

    def test_full_upgrade_scenario(self):
        db_path = os.path.join(tempfile.mkdtemp(), "v1upgrade.db")
        try:
            # Step 1: Create v1.0.0 database with realistic data
            _create_v1_database(db_path)

            # Step 2: Verify pre-migration state
            conn = sqlite3.connect(db_path)
            proj = conn.execute(
                "SELECT name, compliance_score FROM projects WHERE project_id = ?",
                ("proj_novatech",)
            ).fetchone()
            assert proj[0] == "NovaTech Solutions Vendor Assessment"
            assert proj[1] == 75.0

            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            assert task_count == 3

            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            assert user_count == 3

            audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            assert audit_count == 4

            # Verify no migration table exists yet
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "schema_migrations" not in tables
            conn.close()

            # Step 3: Run migrations
            applied = _run(run_pending_migrations(db_path))
            assert "001" in applied
            assert "002" in applied

            # Step 4: Verify ALL data preserved
            conn = sqlite3.connect(db_path)

            # Projects
            projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            assert projects == 2
            proj = conn.execute(
                "SELECT name, compliance_score FROM projects WHERE project_id = ?",
                ("proj_novatech",)
            ).fetchone()
            assert proj[0] == "NovaTech Solutions Vendor Assessment"
            assert proj[1] == 75.0

            # Users
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            assert user_count == 3

            # Requirements
            req_count = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
            assert req_count == 4

            # Tasks - all preserved
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            assert task_count == 3

            # Verify individual task data
            task1 = conn.execute(
                "SELECT title, severity, status FROM tasks WHERE task_id = ?",
                ("TASK-001",)
            ).fetchone()
            assert task1[0] == "Upload insurance certificate"
            assert task1[1] == "HIGH"
            assert task1[2] == "OPEN"

            task2 = conn.execute(
                "SELECT title, severity, status FROM tasks WHERE task_id = ?",
                ("TASK-002",)
            ).fetchone()
            assert task2[0] == "Sign DPA agreement"
            assert task2[2] == "RESOLVED"

            # Matches
            match_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            assert match_count == 4

            # Issues
            issue_count = conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
            assert issue_count == 2

            # Audit events
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            assert audit_count == 4

            # Project members
            member_count = conn.execute("SELECT COUNT(*) FROM project_members").fetchone()[0]
            assert member_count == 3

            # Step 5: Verify migration 002 added expected columns
            columns = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            assert "assigned_to" in columns
            assert "assigned_at" in columns
            assert "assigned_by" in columns
            assert "due_date" in columns

            # Verify existing tasks have NULL for new columns
            assigned = conn.execute(
                "SELECT assigned_to, assigned_at, assigned_by, due_date FROM tasks WHERE task_id = ?",
                ("TASK-001",)
            ).fetchone()
            assert assigned[0] is None  # assigned_to
            assert assigned[1] is None  # assigned_at
            assert assigned[2] is None  # assigned_by
            assert assigned[3] is None  # due_date

            # Verify indexes
            indexes = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'"
            ).fetchall()}
            assert "idx_tasks_assigned" in indexes
            assert "idx_tasks_due_date" in indexes

            # Verify schema_migrations recorded
            mig_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            assert mig_count == 5  # Updated for migrations 004 (document_versions) and 005 (evidence_expiration)

            # Verify migration details
            migs = conn.execute(
                "SELECT migration_id, name FROM schema_migrations ORDER BY migration_id"
            ).fetchall()
            assert migs[0] == ("001", "initial_schema")
            assert migs[1] == ("002", "task_assignment")
            assert migs[2] == ("003", "notifications")

            conn.close()

            # Step 6: Run migrations again (idempotency)
            applied2 = _run(run_pending_migrations(db_path))
            assert len(applied2) == 0

            # Step 7: Verify status
            status = _run(get_migration_status(db_path))
            assert status["applied_count"] == 5  # Updated for migrations 004 and 005
            assert status["pending_count"] == 0

            # Step 8: Final data integrity check
            conn = sqlite3.connect(db_path)
            assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 3
            assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 4
            assert conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0] == 4
            conn.close()

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
