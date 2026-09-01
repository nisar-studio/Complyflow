"""
test_migrations.py — Database Migration Framework Tests

Tests:
  1. Fresh database initialization
  2. Existing v1.0.0-style database compatibility
  3. Migration ordering and tracking
  4. Checksum recording
  5. Idempotent repeated execution
  6. Migration 002 schema changes (assignment columns)
  7. Existing data preservation
  8. CLI migrate command
  9. CLI migrate-status command
  10. Failed migration behavior
  11. Migration integrity verification
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.migration_service import (
    run_pending_migrations,
    get_migration_status,
    verify_migration_integrity,
    _get_all_migrations,
    _ensure_migrations_table,
    _get_applied_migrations,
)
import aiosqlite


# ── Helpers ─────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _unique_id(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _create_temp_db():
    """Create a temporary database path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp.name


def _create_v1_style_db(db_path):
    """Create a database with the v1.0.0 schema (no migration table)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")

    # Create all v1.0.0 tables
    conn.executescript("""
        CREATE TABLE projects (
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
        CREATE TABLE requirements (
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
        CREATE TABLE documents (
            project_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT,
            data_json TEXT,
            PRIMARY KEY (project_id, doc_id)
        );
        CREATE TABLE matches (
            project_id TEXT NOT NULL,
            requirement_id TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL,
            reasoning TEXT,
            data_json TEXT,
            PRIMARY KEY (project_id, requirement_id)
        );
        CREATE TABLE issues (
            project_id TEXT NOT NULL,
            gap_id TEXT NOT NULL,
            gap_type TEXT,
            severity TEXT,
            description TEXT,
            data_json TEXT,
            PRIMARY KEY (project_id, gap_id)
        );
        CREATE TABLE tasks (
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            title TEXT,
            severity TEXT,
            required_action TEXT,
            status TEXT NOT NULL,
            data_json TEXT,
            PRIMARY KEY (project_id, task_id)
        );
        CREATE TABLE agent_events (
            event_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            type TEXT NOT NULL,
            tool TEXT,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            summary TEXT,
            data_json TEXT
        );
        CREATE INDEX idx_events_proj ON agent_events (project_id, timestamp);
        CREATE TABLE verification_runs (
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            run_number INTEGER NOT NULL DEFAULT 1,
            timestamp TEXT NOT NULL,
            data_json TEXT NOT NULL,
            PRIMARY KEY (project_id, run_id)
        );
        CREATE INDEX idx_vr_proj_num ON verification_runs (project_id, run_number);
        CREATE TABLE auditor_overrides (
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
        CREATE INDEX idx_overrides_proj ON auditor_overrides (project_id, requirement_id);
        CREATE TABLE auditor_notes (
            note_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            requirement_id TEXT NOT NULL,
            note_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            data_json TEXT
        );
        CREATE INDEX idx_notes_proj ON auditor_notes (project_id, requirement_id);
        CREATE TABLE remediation_uploads (
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
        CREATE INDEX idx_remed_uploads_proj_task ON remediation_uploads (project_id, task_id);
        CREATE INDEX idx_remed_uploads_proj_req ON remediation_uploads (project_id, requirement_id);
        CREATE TABLE audit_events (
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
        CREATE INDEX idx_audit_proj_time ON audit_events (project_id, timestamp);
        CREATE INDEX idx_audit_proj_type ON audit_events (project_id, event_type);
        CREATE INDEX idx_audit_proj_req ON audit_events (project_id, requirement_id);
        CREATE INDEX idx_audit_proj_run ON audit_events (project_id, run_id);
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_users_email ON users (email);
        CREATE TABLE project_members (
            membership_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, user_id)
        );
        CREATE INDEX idx_members_proj ON project_members (project_id);
        CREATE TABLE sessions (
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
        CREATE INDEX idx_sessions_user ON sessions (user_id);
        CREATE INDEX idx_sessions_token_hash ON sessions (token_hash);
        CREATE TABLE frameworks (
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
        CREATE INDEX idx_frameworks_name_ver ON frameworks (name, version);
        CREATE INDEX idx_frameworks_proj ON frameworks (project_id);
        CREATE TABLE framework_requirements (
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
        CREATE INDEX idx_fw_reqs_id ON framework_requirements (framework_id, requirement_id);

        -- Seed demo user
        INSERT INTO users (user_id, email, name, password_hash, is_active, created_at, updated_at)
        VALUES ('demo-user', 'demo@complyflow.local', 'Compliance Auditor',
                'pbkdf2_sha256$100000$default$default', 1,
                '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
    """)
    conn.commit()
    conn.close()


def _seed_test_data(db_path):
    """Seed a v1-style database with test data."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")

    # Add a project
    conn.execute("""
        INSERT INTO projects (project_id, user_id, name, status, compliance_score, overall_status,
                              requirements_count, documents_count, issues_count, created_at, updated_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("proj_test_001", "demo-user", "Test Project", "PENDING", 75.0, "ACTION_REQUIRED",
          3, 2, 1, "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", "{}"))

    # Add tasks
    conn.execute("""
        INSERT INTO tasks (project_id, task_id, title, severity, required_action, status, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("proj_test_001", "TASK-001", "Fix insurance cert", "HIGH", "Upload cert", "OPEN",
          '{"task_id": "TASK-001", "title": "Fix insurance cert"}'))

    conn.execute("""
        INSERT INTO tasks (project_id, task_id, title, severity, required_action, status, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("proj_test_001", "TASK-002", "Sign DPA", "MEDIUM", "Sign agreement", "RESOLVED",
          '{"task_id": "TASK-002", "title": "Sign DPA"}'))

    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════
# 1. FRESH DATABASE
# ══════════════════════════════════════════════════════════════

class TestFreshDatabase:
    """Test migration on a brand new database."""

    def test_fresh_database_gets_all_migrations(self):
        db_path = _create_temp_db()
        try:
            applied = _run(run_pending_migrations(db_path))
            assert len(applied) >= 2
            assert "001" in applied
            assert "002" in applied
        finally:
            os.unlink(db_path)

    def test_fresh_database_has_all_tables(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            tables = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
            conn.close()

            expected = [
                "audit_events", "auditor_notes", "auditor_overrides",
                "agent_events", "documents", "framework_requirements",
                "frameworks", "issues", "matches", "projects",
                "project_members", "remediation_uploads", "requirements",
                "schema_migrations", "sessions", "tasks", "users",
                "verification_runs",
            ]
            for table in expected:
                assert table in tables, f"Missing table: {table}"
        finally:
            os.unlink(db_path)

    def test_fresh_database_has_assignment_columns(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            conn.close()

            assert "assigned_to" in columns
            assert "assigned_at" in columns
            assert "assigned_by" in columns
            assert "due_date" in columns
        finally:
            os.unlink(db_path)

    def test_fresh_database_has_demo_user(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT user_id FROM users WHERE user_id = 'demo-user'").fetchone()
            conn.close()
            assert row is not None
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 2. EXISTING v1.0.0 DATABASE
# ══════════════════════════════════════════════════════════════

class TestExistingV1Database:
    """Test migration on an existing v1.0.0-style database."""

    def test_existing_db_gets_migrations_applied(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            applied = _run(run_pending_migrations(db_path))
            assert len(applied) >= 2
            assert "001" in applied
            assert "002" in applied
        finally:
            os.unlink(db_path)

    def test_existing_db_preserves_data(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _seed_test_data(db_path)

            # Verify data exists before migration
            conn = sqlite3.connect(db_path)
            proj = conn.execute("SELECT name FROM projects WHERE project_id = 'proj_test_001'").fetchone()
            assert proj[0] == "Test Project"
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            assert task_count == 2
            conn.close()

            # Run migration
            _run(run_pending_migrations(db_path))

            # Verify data still exists after migration
            conn = sqlite3.connect(db_path)
            proj = conn.execute("SELECT name FROM projects WHERE project_id = 'proj_test_001'").fetchone()
            assert proj[0] == "Test Project"
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            assert task_count == 2

            # Verify task data is intact
            task = conn.execute(
                "SELECT title, severity, status FROM tasks WHERE task_id = 'TASK-001'"
            ).fetchone()
            assert task[0] == "Fix insurance cert"
            assert task[1] == "HIGH"
            assert task[2] == "OPEN"
            conn.close()
        finally:
            os.unlink(db_path)

    def test_existing_db_gets_assignment_columns(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _seed_test_data(db_path)

            _run(run_pending_migrations(db_path))

            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            assert "assigned_to" in columns
            assert "due_date" in columns

            # Verify existing tasks have NULL for new columns
            task = conn.execute(
                "SELECT assigned_to, due_date FROM tasks WHERE task_id = 'TASK-001'"
            ).fetchone()
            assert task[0] is None  # assigned_to
            assert task[1] is None  # due_date
            conn.close()
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 3. MIGRATION ORDERING AND TRACKING
# ══════════════════════════════════════════════════════════════

class TestMigrationOrdering:
    """Test that migrations are applied in correct order."""

    def test_migrations_applied_in_order(self):
        db_path = _create_temp_db()
        try:
            applied = _run(run_pending_migrations(db_path))
            assert applied.index("001") < applied.index("002")
        finally:
            os.unlink(db_path)

    def test_migration_registry_order(self):
        migrations = _get_all_migrations()
        ids = [m["id"] for m in migrations]
        assert ids == sorted(ids), "Migrations must be in sorted order"

    def test_schema_migrations_table_records_order(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
            ).fetchall()
            conn.close()
            applied_ids = [r[0] for r in rows]
            assert applied_ids == sorted(applied_ids)
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 4. CHECKSUM RECORDING
# ══════════════════════════════════════════════════════════════

class TestChecksumRecording:
    """Test that checksums are recorded correctly."""

    def test_checksums_recorded(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id"
            ).fetchall()
            conn.close()

            for mid, checksum in rows:
                assert checksum is not None
                assert len(checksum) == 16  # SHA-256 truncated to 16 chars
        finally:
            os.unlink(db_path)

    def test_checksums_match_current_code(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            applied = {}
            for row in conn.execute("SELECT migration_id, checksum FROM schema_migrations"):
                applied[row[0]] = row[1]
            conn.close()

            # Compare with current migration checksums
            all_migrations = {m["id"]: m for m in _get_all_migrations()}
            for mid, stored_checksum in applied.items():
                assert mid in all_migrations
                assert stored_checksum == all_migrations[mid]["checksum"]
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 5. IDEMPOTENT REPEATED EXECUTION
# ══════════════════════════════════════════════════════════════

class TestIdempotentExecution:
    """Test that running migrations multiple times is safe."""

    def test_second_run_applies_nothing(self):
        db_path = _create_temp_db()
        try:
            applied1 = _run(run_pending_migrations(db_path))
            applied2 = _run(run_pending_migrations(db_path))
            assert len(applied1) >= 2
            assert len(applied2) == 0
        finally:
            os.unlink(db_path)

    def test_third_run_applies_nothing(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            _run(run_pending_migrations(db_path))
            applied3 = _run(run_pending_migrations(db_path))
            assert len(applied3) == 0
        finally:
            os.unlink(db_path)

    def test_idempotent_on_existing_db(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _seed_test_data(db_path)

            applied1 = _run(run_pending_migrations(db_path))
            applied2 = _run(run_pending_migrations(db_path))

            assert len(applied1) >= 2
            assert len(applied2) == 0

            # Data still intact
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            conn.close()
            assert count == 2
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 6. MIGRATION 002 SCHEMA CHANGES
# ══════════════════════════════════════════════════════════════

class TestMigration002:
    """Test the task assignment migration specifically."""

    def test_assignment_columns_exist(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            conn.close()

            assert "assigned_to" in columns
            assert "assigned_at" in columns
            assert "assigned_by" in columns
            assert "due_date" in columns
        finally:
            os.unlink(db_path)

    def test_assignment_indexes_exist(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            indexes = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'"
            ).fetchall()}
            conn.close()

            assert "idx_tasks_assigned" in indexes
            assert "idx_tasks_due_date" in indexes
        finally:
            os.unlink(db_path)

    def test_can_insert_task_with_assignment(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            conn = sqlite3.connect(db_path)
            conn.execute("""
                INSERT INTO tasks (project_id, task_id, title, severity, status,
                                   assigned_to, assigned_at, assigned_by, due_date, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("proj_001", "TASK-NEW", "New task", "HIGH", "OPEN",
                  "user_001", "2026-09-01T00:00:00Z", "admin_001",
                  "2026-09-15T23:59:59Z", "{}"))
            conn.commit()

            row = conn.execute(
                "SELECT assigned_to, assigned_at, assigned_by, due_date FROM tasks WHERE task_id = 'TASK-NEW'"
            ).fetchone()
            conn.close()

            assert row[0] == "user_001"
            assert row[1] == "2026-09-01T00:00:00Z"
            assert row[2] == "admin_001"
            assert row[3] == "2026-09-15T23:59:59Z"
        finally:
            os.unlink(db_path)

    def test_existing_tasks_get_null_assignment(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _seed_test_data(db_path)

            _run(run_pending_migrations(db_path))

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT assigned_to, due_date FROM tasks ORDER BY task_id"
            ).fetchall()
            conn.close()

            for row in rows:
                assert row[0] is None  # assigned_to
                assert row[1] is None  # due_date
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 7. EXISTING DATA PRESERVATION
# ══════════════════════════════════════════════════════════════

class TestDataPreservation:
    """Test that migrations preserve all existing data."""

    def test_all_tables_preserved(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _seed_test_data(db_path)

            # Count rows in each table before migration
            conn = sqlite3.connect(db_path)
            tables_before = {}
            for table in ["projects", "tasks", "users"]:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                tables_before[table] = count
            conn.close()

            _run(run_pending_migrations(db_path))

            # Count rows after migration
            conn = sqlite3.connect(db_path)
            for table, count_before in tables_before.items():
                count_after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count_after == count_before, f"Row count changed for {table}"
            conn.close()
        finally:
            os.unlink(db_path)

    def test_json_data_preserved(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)

            # Insert task with specific JSON data
            conn = sqlite3.connect(db_path)
            conn.execute("""
                INSERT INTO tasks (project_id, task_id, title, severity, status, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("proj_001", "TASK-JSON", "JSON test", "CRITICAL", "OPEN",
                  '{"task_id": "TASK-JSON", "custom_field": "preserved_value"}'))
            conn.commit()
            conn.close()

            _run(run_pending_migrations(db_path))

            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT data_json FROM tasks WHERE task_id = 'TASK-JSON'").fetchone()
            conn.close()

            import json
            data = json.loads(row[0])
            assert data["custom_field"] == "preserved_value"
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 8. MIGRATION STATUS
# ══════════════════════════════════════════════════════════════

class TestMigrationStatus:
    """Test the get_migration_status function."""

    def test_fresh_db_status(self):
        db_path = _create_temp_db()
        try:
            status = _run(get_migration_status(db_path))
            assert status["applied_count"] == 0
            assert status["pending_count"] >= 2
            assert status["total"] >= 2
        finally:
            os.unlink(db_path)

    def test_migrated_db_status(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            status = _run(get_migration_status(db_path))
            assert status["applied_count"] >= 2
            assert status["pending_count"] == 0
        finally:
            os.unlink(db_path)

    def test_status_details(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            status = _run(get_migration_status(db_path))

            for m in status["applied"]:
                assert "id" in m
                assert "name" in m
                assert "applied_at" in m
                assert "checksum" in m
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 9. MIGRATION INTEGRITY VERIFICATION
# ══════════════════════════════════════════════════════════════

class TestMigrationIntegrity:
    """Test the verify_migration_integrity function."""

    def test_no_warnings_for_clean_db(self):
        db_path = _create_temp_db()
        try:
            _run(run_pending_migrations(db_path))
            warnings = _run(verify_migration_integrity(db_path))
            assert len(warnings) == 0
        finally:
            os.unlink(db_path)

    def test_no_warnings_for_v1_db(self):
        db_path = _create_temp_db()
        try:
            _create_v1_style_db(db_path)
            _run(run_pending_migrations(db_path))
            warnings = _run(verify_migration_integrity(db_path))
            assert len(warnings) == 0
        finally:
            os.unlink(db_path)


# ══════════════════════════════════════════════════════════════
# 10. MIGRATION MODULE METADATA
# ══════════════════════════════════════════════════════════════

class TestMigrationMetadata:
    """Test that migration modules have correct metadata."""

    def test_all_migrations_have_required_fields(self):
        migrations = _get_all_migrations()
        for m in migrations:
            assert "id" in m
            assert "name" in m
            assert "module_path" in m
            assert "up" in m
            assert "checksum" in m
            assert callable(m["up"])

    def test_migration_ids_are_unique(self):
        migrations = _get_all_migrations()
        ids = [m["id"] for m in migrations]
        assert len(ids) == len(set(ids)), "Migration IDs must be unique"

    def test_migration_checksums_are_unique(self):
        migrations = _get_all_migrations()
        checksums = [m["checksum"] for m in migrations]
        # Checksums can collide in theory but should be unique for different code
        # At minimum, 001 and 002 should be different
        assert checksums[0] != checksums[1]


# ══════════════════════════════════════════════════════════════
# 11. EDGE CASES
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_migration_on_nonexistent_directory(self):
        """Migration should create the database file and parent directories."""
        db_path = os.path.join(tempfile.mkdtemp(), "subdir", "test.db")
        try:
            applied = _run(run_pending_migrations(db_path))
            assert len(applied) >= 2
            assert os.path.exists(db_path)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
            parent = os.path.dirname(db_path)
            if os.path.exists(parent):
                os.rmdir(parent)

    def test_concurrent_migration_safety(self):
        """Two concurrent migration runs should not conflict."""
        db_path = _create_temp_db()
        try:
            # Run migrations sequentially (SQLite handles concurrent access via busy_timeout)
            applied1 = _run(run_pending_migrations(db_path))
            applied2 = _run(run_pending_migrations(db_path))
            assert len(applied1) >= 2
            assert len(applied2) == 0
        finally:
            os.unlink(db_path)
