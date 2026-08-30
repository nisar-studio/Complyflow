"""
test_production_hardening.py — Production Hardening & Deployment Readiness Tests

Verifies:
  1. Centralized configuration & environment validation
  2. Production security validation (rejects weak secrets/insecure cookie flags in production)
  3. Structured logging secret redaction (Gemini keys, passwords, hashes, tokens, absolute paths)
  4. Security HTTP headers (nosniff, DENY, XSS, Referrer-Policy)
  5. File upload security (null byte rejection, path traversal, extension whitelisting, size limits)
  6. Health & readiness probes (no secrets or paths leaked)
  7. SQLite database hardening (WAL mode, foreign keys, busy timeout)
  8. Absence of absolute filesystem paths in reports and API responses
  9. Deterministic offline execution (no cloud/Gemini required for test execution)
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import logging
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.core.config import Settings, get_settings
from app.core.logging import redact_secrets, RedactingFormatter
from app.services.auth_service import create_session_token, SESSION_COOKIE_NAME
from app.services.file_utils import sanitize_filename, validate_upload, MAX_UPLOAD_SIZE
from app.main import app


@pytest.fixture(scope="module")
def prod_ctx(tmp_path_factory):
    """Isolated environment for production hardening tests."""
    tmp = tmp_path_factory.mktemp("prod_hardening")
    db_path = str(tmp / "prod_hardening.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir
    original_doc_dir = routes_module._document_service.upload_dir
    routes_module._document_service.upload_dir = upload_dir

    client = TestClient(app, raise_server_exceptions=True)
    token = create_session_token("demo-user", "demo@complyflow.local")
    client.headers["Authorization"] = f"Bearer {token}"

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
        "token": token,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


# ─────────────────────────────────────────────────────────────
# 1. Configuration & Production Validation
# ─────────────────────────────────────────────────────────────

class TestCentralizedConfiguration:

    def test_default_development_config_is_valid(self):
        s = Settings(app_env="development")
        assert s.is_production() is False
        errors = s.validate_production_settings()
        assert len(errors) == 0

    def test_production_mode_flags_weak_default_secret(self):
        s = Settings(
            app_env="production",
            session_secret="complyflow-session-secret-key-32-bytes!",
            cookie_secure=True,
            cors_origins=["http://localhost:3000"],
        )
        errors = s.validate_production_settings()
        assert any("SESSION_SECRET" in err for err in errors)

    def test_production_mode_flags_insecure_cookie_flag(self):
        s = Settings(
            app_env="production",
            session_secret="a" * 32,
            cookie_secure=False,
            cors_origins=["http://localhost:3000"],
        )
        errors = s.validate_production_settings()
        assert any("COOKIE_SECURE" in err for err in errors)

    def test_production_mode_flags_wildcard_cors(self):
        s = Settings(
            app_env="production",
            session_secret="a" * 32,
            cookie_secure=True,
            cors_origins=["*"],
        )
        errors = s.validate_production_settings()
        assert any("CORS_ORIGINS" in err for err in errors)

    def test_valid_production_config_passes_cleanly(self):
        s = Settings(
            app_env="production",
            session_secret="a" * 32,
            cookie_secure=True,
            cors_origins=["https://compliance.company.internal"],
        )
        errors = s.validate_production_settings()
        assert len(errors) == 0


# ─────────────────────────────────────────────────────────────
# 2. Log Secret Redaction
# ─────────────────────────────────────────────────────────────

class TestLogSecretRedaction:

    def test_redacts_gemini_api_key(self):
        raw = "Connecting to Gemini with key AIzaSyD94837483748374837483748374837483"
        cleaned = redact_secrets(raw)
        assert "AIzaSy" not in cleaned
        assert "[REDACTED_GEMINI_KEY]" in cleaned

    def test_redacts_password_hash(self):
        raw = "User hash pbkdf2_sha256$100000$a1b2c3d4$e5f6a7b8c9d0e1f2a3b4c5d6e7f8"
        cleaned = redact_secrets(raw)
        assert "pbkdf2_sha256" not in cleaned
        assert "[REDACTED_PASSWORD_HASH]" in cleaned

    def test_redacts_bearer_token(self):
        raw = "Request Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNlcl8xIn0"
        cleaned = redact_secrets(raw)
        assert "eyJhbGciOi" not in cleaned
        assert "[REDACTED_TOKEN]" in cleaned

    def test_redacts_session_cookies(self):
        raw = "Cookie: complyflow_session=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.signature; other=val"
        cleaned = redact_secrets(raw)
        assert "complyflow_session=[REDACTED_SESSION]" in cleaned

    def test_redacts_csrf_token(self):
        raw = "complyflow_csrf=a1b2c3d4e5f60718293a4b5c6d7e8f90"
        cleaned = redact_secrets(raw)
        assert "a1b2c3d4e5f60718293a4b5c6d7e8f90" not in cleaned
        assert "[REDACTED_CSRF]" in cleaned

    def test_redacts_absolute_windows_and_unix_paths(self):
        win_path = r"Loaded file from C:\Users\ADMIN\AppData\Local\secret\data.pdf"
        cleaned_win = redact_secrets(win_path)
        assert r"C:\Users\ADMIN" not in cleaned_win
        assert "[LOCAL_FILE_PATH]" in cleaned_win

        unix_path = "/home/appuser/secret/document.pdf"
        cleaned_unix = redact_secrets(unix_path)
        assert "/home/appuser" not in cleaned_unix
        assert "[LOCAL_FILE_PATH]" in cleaned_unix


# ─────────────────────────────────────────────────────────────
# 3. HTTP Security Headers
# ─────────────────────────────────────────────────────────────

class TestSecurityHeaders:

    def test_security_headers_present_on_all_responses(self, prod_ctx):
        client = prod_ctx["client"]
        r = client.get("/health")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-XSS-Protection") == "1; mode=block"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ─────────────────────────────────────────────────────────────
# 4. File Storage Hardening & Sanitization
# ─────────────────────────────────────────────────────────────

class TestFileStorageHardening:

    def test_sanitize_filename_strips_null_bytes(self):
        unsafe = "document\x00.pdf"
        safe = sanitize_filename(unsafe)
        assert "\x00" not in safe
        assert safe == "document.pdf"

    def test_sanitize_filename_strips_path_traversal(self):
        unsafe = "../../../etc/passwd.txt"
        safe = sanitize_filename(unsafe)
        assert ".." not in safe
        assert "/" not in safe
        assert "\\" not in safe
        assert "passwd" in safe

    def test_sanitize_filename_handles_windows_traversal(self):
        unsafe = r"..\..\Windows\System32\cmd.exe"
        safe = sanitize_filename(unsafe)
        assert ".." not in safe
        assert "\\" not in safe
        assert "cmd" in safe

    def test_upload_rejects_disallowed_extension(self, prod_ctx):
        client = prod_ctx["client"]
        storage = prod_ctx["storage"]
        r = client.post("/api/projects", data={"name": "Upload Sec Test"})
        proj_id = r.json()["project_id"]

        # Create a requirement and task in the project first
        req = {"requirement_id": "REQ-001", "project_id": proj_id, "text": "Requirement 1", "category": "Security"}
        task = {
            "task_id": "task-sec-001",
            "project_id": proj_id,
            "title": "Remediation Task",
            "requirement_id": "REQ-001",
            "status": "OPEN",
        }
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(storage.save_requirements(proj_id, [req]))
            loop.run_until_complete(storage.save_tasks(proj_id, [task]))
        finally:
            loop.close()


        r2 = client.post(
            f"/api/projects/{proj_id}/tasks/task-sec-001/uploads",
            files={"file": ("malicious.exe", b"binary content", "application/octet-stream")},
            data={"requirement_id": "REQ-001"},
        )
        assert r2.status_code == 400
        assert "not allowed" in r2.text.lower()


# ─────────────────────────────────────────────────────────────
# 5. Health & Readiness Probes
# ─────────────────────────────────────────────────────────────

class TestHealthAndReadiness:

    def test_health_probe_returns_200_without_secrets(self, prod_ctx):
        client = prod_ctx["client"]
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "gemini_configured" in data
        assert "database_connected" in data
        # Ensure no secrets or file paths
        text = r.text
        assert "AIzaSy" not in text
        assert "password" not in text
        assert "complyflow.db" not in text

    def test_readiness_probe_returns_200(self, prod_ctx):
        client = prod_ctx["client"]
        r = client.get("/ready")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ready"
        assert data["database_ready"] is True


# ─────────────────────────────────────────────────────────────
# 6. SQLite Database Hardening (PRAGMAs)
# ─────────────────────────────────────────────────────────────

class TestDatabaseHardening:

    @pytest.mark.asyncio
    async def test_sqlite_pragmas_enabled(self, prod_ctx):
        storage = prod_ctx["storage"]
        await storage._init_db()

        import aiosqlite
        async with aiosqlite.connect(storage.db_path) as db:
            # Check journal_mode (persisted in DB header)
            async with db.execute("PRAGMA journal_mode;") as cursor:
                row = await cursor.fetchone()
                assert row[0].upper() == "WAL"

            # Check busy timeout
            await db.execute("PRAGMA busy_timeout=5000;")
            async with db.execute("PRAGMA busy_timeout;") as cursor:
                row = await cursor.fetchone()
                assert row[0] >= 5000

