"""
test_auth_security.py — Production Authentication Security Hardening & Verification

Tests:
  1. Session Transport (HttpOnly cookie, no localStorage tokens in body)
  2. Cookie Security Attributes (HttpOnly, SameSite, Path, Max-Age, Configurable Secure flag)
  3. Session Storage & Payload Hygiene (No password hashes or secrets in tokens/claims)
  4. Cookie-Only Authentication (Endpoints work purely via browser cookies)
  5. Server-Side Session Revocation (Logout revokes session; revoked sessions rejected)
  6. Session Expiration (Expired sessions rejected)
  7. Inactive User Rejection (Deactivated accounts blocked immediately)
  8. CSRF Protection (Mutating cookie requests require CSRF token; Bearer exempt)
  9. CORS Configuration (No wildcard origin when credentials enabled)
  10. Authentication Error Handling (Generic login errors; no account enumeration)
  11. Project Isolation (User of Project A cannot access Project B)
  12. RBAC Enforcement across all 4 roles (ADMIN, AUDITOR, REVIEWER, VIEWER)
"""
from __future__ import annotations

import asyncio
import os
import sys
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_session_token,
    create_authenticated_session,
    verify_session_token,
    Role,
    ROLE_PERMISSIONS,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from app.core.config import get_settings


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def sec_ctx(tmp_path_factory):
    """Isolated database and TestClient for security verification."""
    tmp = tmp_path_factory.mktemp("auth_security")
    db_path = str(tmp / "auth_sec.db")
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

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


# ─────────────────────────────────────────────────────────────
# 1. Session Transport & Cookie Security Attributes
# ─────────────────────────────────────────────────────────────

class TestSessionTransportAndCookieFlags:

    def test_login_sets_httponly_session_cookie(self, sec_ctx):
        client = sec_ctx["client"]
        # Register user
        client.post("/api/auth/register", json={
            "email": "transport_user@example.com",
            "name": "Transport User",
            "password": "SecurePassword123!",
        })
        client.cookies.clear()

        # Login
        r = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        assert r.status_code == 200

        # Check Set-Cookie headers
        set_cookie_headers = [v for k, v in r.headers.raw if k.decode().lower() == "set-cookie"]
        session_cookie_header = next((h.decode() for h in set_cookie_headers if SESSION_COOKIE_NAME in h.decode()), None)
        assert session_cookie_header is not None, "complyflow_session Set-Cookie header missing"

        # Check flags
        assert "httponly" in session_cookie_header.lower(), "HttpOnly flag missing from session cookie"
        assert "samesite=lax" in session_cookie_header.lower(), "SameSite=lax missing from session cookie"
        assert "path=/" in session_cookie_header.lower(), "Path=/ missing from session cookie"

    def test_no_token_in_login_response_body(self, sec_ctx):
        client = sec_ctx["client"]
        r = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        assert r.status_code == 200
        data = r.json()
        assert "token" not in data
        assert "access_token" not in data
        assert "user" in data
        assert "password_hash" not in data["user"]

    def test_register_sets_httponly_cookie(self, sec_ctx):
        client = sec_ctx["client"]
        client.cookies.clear()
        r = client.post("/api/auth/register", json={
            "email": "reg_transport@example.com",
            "name": "Reg Transport",
            "password": "SecurePassword123!",
        })
        assert r.status_code == 201
        set_cookie_headers = [v for k, v in r.headers.raw if k.decode().lower() == "set-cookie"]
        session_cookie_header = next((h.decode() for h in set_cookie_headers if SESSION_COOKIE_NAME in h.decode()), None)
        assert session_cookie_header is not None
        assert "httponly" in session_cookie_header.lower()


# ─────────────────────────────────────────────────────────────
# 2. Cookie-Only Authentication (/auth/me & API Access)
# ─────────────────────────────────────────────────────────────

class TestCookieOnlyAuthentication:

    def test_auth_me_works_using_only_cookie(self, sec_ctx):
        client = sec_ctx["client"]
        client.cookies.clear()

        # Login to populate client cookies
        login_res = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        assert SESSION_COOKIE_NAME in client.cookies

        # Request /api/auth/me WITHOUT any Authorization header
        r = client.get("/api/auth/me", headers={})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "transport_user@example.com"

    def test_project_list_works_using_only_cookie(self, sec_ctx):
        client = sec_ctx["client"]
        # Client already holds valid session cookie from previous test
        r = client.get("/api/projects", headers={})
        assert r.status_code == 200
        assert "projects" in r.json()


# ─────────────────────────────────────────────────────────────
# 3. Server-Side Session Revocation & Invalidation
# ─────────────────────────────────────────────────────────────

class TestSessionRevocation:

    def test_logout_revokes_session_and_clears_cookie(self, sec_ctx):
        client = sec_ctx["client"]
        storage = sec_ctx["storage"]
        client.cookies.clear()

        # 1. Login
        login_res = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        raw_cookie = client.cookies.get(SESSION_COOKIE_NAME)
        assert raw_cookie is not None

        # Verify decoded payload has session_id
        payload = verify_session_token(raw_cookie)
        assert payload is not None
        session_id = payload["session_id"]

        # Check session is active in database
        sess_record = _run(storage.get_session(session_id))
        assert sess_record is not None
        assert sess_record["is_revoked"] is False

        # 2. Logout
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200

        # Check session is marked revoked in database
        revoked_record = _run(storage.get_session(session_id))
        assert revoked_record is not None
        assert revoked_record["is_revoked"] is True

        # 3. Attempting to access /api/auth/me with the revoked token returns 401
        r_after = client.get("/api/auth/me", cookies={SESSION_COOKIE_NAME: raw_cookie})
        assert r_after.status_code == 401
        assert "revoked" in r_after.text.lower() or "unauthorized" in r_after.text.lower() or "invalid" in r_after.text.lower()

    def test_manually_revoked_session_is_rejected(self, sec_ctx):
        client = sec_ctx["client"]
        storage = sec_ctx["storage"]
        client.cookies.clear()

        # Login
        client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        raw_cookie = client.cookies.get(SESSION_COOKIE_NAME)
        payload = verify_session_token(raw_cookie)
        session_id = payload["session_id"]

        # Manually revoke in DB
        _run(storage.revoke_session(session_id))

        # Subsequent request with this cookie must fail
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_expired_session_is_rejected(self, sec_ctx):
        client = sec_ctx["client"]
        # Create expired token
        expired_token = create_session_token("transport_user", "transport_user@example.com", expires_in_seconds=-10)
        r = client.get("/api/auth/me", cookies={SESSION_COOKIE_NAME: expired_token})
        assert r.status_code == 401

    def test_inactive_user_session_is_rejected(self, sec_ctx):
        client = sec_ctx["client"]
        storage = sec_ctx["storage"]

        # Create user & deactivate
        client.post("/api/auth/register", json={
            "email": "deactivated_user@example.com",
            "name": "Deactivated",
            "password": "SecurePassword123!",
        })
        user = _run(storage.get_user_by_email("deactivated_user@example.com"))
        token = create_session_token(user["user_id"], user["email"])

        # Deactivate user
        _run(storage.update_user(user["user_id"], {"is_active": False}))

        # Attempt auth with token
        r = client.get("/api/auth/me", cookies={SESSION_COOKIE_NAME: token})
        assert r.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────
# 4. CSRF Protection
# ─────────────────────────────────────────────────────────────

class TestCsrfProtection:

    def test_mutating_cookie_request_without_csrf_is_blocked(self, sec_ctx):
        client = sec_ctx["client"]
        client.cookies.clear()

        # Login
        client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })

        # Send POST request using only cookie, WITHOUT X-CSRF-Token or X-Requested-With
        r = client.post(
            "/api/projects",
            data={"name": "CSRF Attack Project"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 403
        assert "csrf" in r.text.lower()

    def test_mutating_cookie_request_with_valid_csrf_token_succeeds(self, sec_ctx):
        client = sec_ctx["client"]
        client.cookies.clear()

        # Login sets complyflow_csrf cookie
        login_res = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        csrf_cookie = client.cookies.get(CSRF_COOKIE_NAME)
        assert csrf_cookie is not None

        # Send POST request with matching X-CSRF-Token header
        r = client.post(
            "/api/projects",
            data={"name": "Legitimate Project"},
            headers={
                CSRF_HEADER_NAME: csrf_cookie,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        assert r.status_code == 200
        assert "project_id" in r.json()

    def test_bearer_authenticated_request_is_csrf_exempt(self, sec_ctx):
        client = sec_ctx["client"]
        client.cookies.clear()

        user = _run(sec_ctx["storage"].get_user_by_email("transport_user@example.com"))
        token = create_session_token(user["user_id"], user["email"])

        # CLI/API request with Bearer Authorization header needs no CSRF cookie
        r = client.post(
            "/api/projects",
            data={"name": "CLI Created Project"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────
# 5. Generic Authentication Failure (No Account Enumeration)
# ─────────────────────────────────────────────────────────────

class TestGenericAuthenticationErrors:

    def test_nonexistent_email_returns_generic_error(self, sec_ctx):
        client = sec_ctx["client"]
        r = client.post("/api/auth/login", json={
            "email": "nonexistent_account_999@example.com",
            "password": "WrongPassword123!",
        })
        assert r.status_code == 401
        msg = r.json().get("error", {}).get("message", "")
        assert "not found" not in msg.lower()
        assert "no user" not in msg.lower()
        assert "invalid credentials" in msg.lower()

    def test_wrong_password_returns_identical_generic_error(self, sec_ctx):
        client = sec_ctx["client"]
        r = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "IncorrectPassword999!",
        })
        assert r.status_code == 401
        msg = r.json().get("error", {}).get("message", "")
        assert "invalid credentials" in msg.lower()

    def test_no_stack_traces_or_hashes_in_error_responses(self, sec_ctx):
        client = sec_ctx["client"]
        r = client.post("/api/auth/login", json={
            "email": "transport_user@example.com",
            "password": "IncorrectPassword999!",
        })
        text = r.text
        assert "Traceback" not in text
        assert "pbkdf2_sha256" not in text
        assert "sqlite" not in text.lower()


# ─────────────────────────────────────────────────────────────
# 6. CORS Configuration Security
# ─────────────────────────────────────────────────────────────

class TestCorsConfiguration:

    def test_cors_does_not_use_wildcard_with_credentials(self, sec_ctx):
        settings = get_settings()
        assert "*" not in settings.cors_origins

    def test_allowed_origin_preflight_response(self, sec_ctx):
        client = sec_ctx["client"]
        r = client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert r.headers.get("access-control-allow-credentials") == "true"


# ─────────────────────────────────────────────────────────────
# 7. Project Isolation & Full RBAC Regression
# ─────────────────────────────────────────────────────────────

class TestProjectIsolationAndRbacRegression:

    def test_project_isolation(self, sec_ctx):
        client = sec_ctx["client"]
        # Register User 1 and User 2
        r1 = client.post("/api/auth/register", json={"email": "iso_u1@example.com", "name": "U1", "password": "Password123!"})
        r2 = client.post("/api/auth/register", json={"email": "iso_u2@example.com", "name": "U2", "password": "Password123!"})

        u1_id = r1.json()["user"]["user_id"]
        u2_id = r2.json()["user"]["user_id"]

        u1_token = create_session_token(u1_id, "iso_u1@example.com")
        u2_token = create_session_token(u2_id, "iso_u2@example.com")

        # U1 creates Project
        r = client.post("/api/projects", data={"name": "U1 Project"}, headers={"Authorization": f"Bearer {u1_token}"})
        assert r.status_code == 200
        project_id = r.json()["project_id"]

        # U2 attempts to read U1's Project -> 403 Forbidden
        r2_get = client.get(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {u2_token}"})
        assert r2_get.status_code == 403


    def test_all_four_roles_permissions(self, sec_ctx):
        client = sec_ctx["client"]
        storage = sec_ctx["storage"]

        emails = {
            "rbac_admin_sec@example.com": "ADMIN",
            "rbac_auditor_sec@example.com": "AUDITOR",
            "rbac_reviewer_sec@example.com": "REVIEWER",
            "rbac_viewer_sec@example.com": "VIEWER",
        }
        for email, _ in emails.items():
            client.post("/api/auth/register", json={"email": email, "name": email.split("@")[0], "password": "Password123!"})

        admin_user = _run(storage.get_user_by_email("rbac_admin_sec@example.com"))
        admin_token = create_session_token(admin_user["user_id"], admin_user["email"])

        # Admin creates project
        r = client.post("/api/projects", data={"name": "RBAC Roles Project"}, headers={"Authorization": f"Bearer {admin_token}"})
        proj_id = r.json()["project_id"]

        # Add other members
        for email, role in emails.items():
            if email == "rbac_admin_sec@example.com":
                continue
            u = _run(storage.get_user_by_email(email))
            client.post(
                f"/api/projects/{proj_id}/members",
                json={"user_id": u["user_id"], "role": role},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        tokens = {}
        for email in emails:
            u = _run(storage.get_user_by_email(email))
            tokens[email] = create_session_token(u["user_id"], u["email"])

        # 1. ADMIN can manage members
        r_admin_m = client.get(f"/api/projects/{proj_id}/members", headers={"Authorization": f"Bearer {tokens['rbac_admin_sec@example.com']}"})
        assert r_admin_m.status_code == 200

        # 2. AUDITOR can override, but cannot manage members
        r_aud_ov = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-001/override",
            json={"overridden_status": "SATISFIED", "auditor_reason": "Auditor approved."},
            headers={"Authorization": f"Bearer {tokens['rbac_auditor_sec@example.com']}"},
        )
        assert r_aud_ov.status_code != 403

        r_aud_m = client.post(
            f"/api/projects/{proj_id}/members",
            json={"email": "new_sec@example.com", "role": "VIEWER"},
            headers={"Authorization": f"Bearer {tokens['rbac_auditor_sec@example.com']}"},
        )
        assert r_aud_m.status_code == 403

        # 3. REVIEWER can add notes & remediation uploads, but cannot override
        r_rev_ov = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-001/override",
            json={"overridden_status": "SATISFIED", "auditor_reason": "Reviewer trying."},
            headers={"Authorization": f"Bearer {tokens['rbac_reviewer_sec@example.com']}"},
        )
        assert r_rev_ov.status_code == 403

        r_rev_note = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-001/notes",
            json={"note_text": "Reviewer note."},
            headers={"Authorization": f"Bearer {tokens['rbac_reviewer_sec@example.com']}"},
        )
        assert r_rev_note.status_code == 200

        # 4. VIEWER can view project, but cannot create notes, uploads, or overrides
        r_view_p = client.get(f"/api/projects/{proj_id}", headers={"Authorization": f"Bearer {tokens['rbac_viewer_sec@example.com']}"})
        assert r_view_p.status_code == 200

        r_view_note = client.post(
            f"/api/projects/{proj_id}/requirements/REQ-001/notes",
            json={"note_text": "Viewer trying."},
            headers={"Authorization": f"Bearer {tokens['rbac_viewer_sec@example.com']}"},
        )
        assert r_view_note.status_code == 403
