"""
test_auth_rbac.py — Comprehensive Authentication & RBAC Tests for ComplyFlow

Tests:
  - Registration, login, logout, /me
  - Invalid credentials, inactive accounts, no PW exposure
  - Unauthenticated project access rejected (401)
  - Project isolation (cross-project access blocked)
  - ADMIN, AUDITOR, REVIEWER, VIEWER permissions
  - Auditor override governance per role
  - Remediation upload governance per role
  - Report export governance
  - Audit events contain authenticated actor identity
  - Project membership management (add/update/remove, last-admin guard)
  - Secrets (passwords, hashes, tokens) never appear in audit events
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
    verify_session_token,
    has_permission,
    Role,
    ROLE_PERMISSIONS,
    SESSION_COOKIE_NAME,
)


@pytest.fixture(scope="module")
def auth_ctx(tmp_path_factory):
    """Full API client with an isolated DB and upload dir."""
    tmp = tmp_path_factory.mktemp("auth_rbac")
    db_path = str(tmp / "auth_rbac.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir
    document_service = routes_module._document_service
    document_service.upload_dir = upload_dir

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
    }

    routes_module.settings.upload_dir = original_upload_dir
    document_service.upload_dir = original_upload_dir
    storage_module._storage_instance = original_instance


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, email, name, password) -> dict:
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    client.cookies.clear()
    return r


def _login(client, email, password) -> str:
    """Login and return Bearer token from response cookie."""
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    cookie = r.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        data = r.json()
        uid = data["user"]["user_id"]
        email_resp = data["user"]["email"]
        cookie = create_session_token(uid, email_resp)
    client.cookies.clear()
    return cookie


# ─────────────────────────────────────────────────────────────
# 1. Unit Tests — Password Hashing
# ─────────────────────────────────────────────────────────────

class TestPasswordHashing:

    def test_hash_is_not_plaintext(self):
        pw = "SecurePassword123!"
        h = hash_password(pw)
        assert pw not in h
        assert h.startswith("pbkdf2_sha256$")

    def test_verify_correct_password(self):
        pw = "CorrectHorseBattery"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_wrong_password(self):
        pw = "CorrectHorseBattery"
        h = hash_password(pw)
        assert verify_password("WrongPassword", h) is False

    def test_empty_password_rejected(self):
        with pytest.raises((ValueError, Exception)):
            hash_password("")

    def test_different_salts_produce_different_hashes(self):
        pw = "SamePassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2

    def test_both_hashes_verify_correctly(self):
        pw = "SamePassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert verify_password(pw, h1) is True
        assert verify_password(pw, h2) is True


# ─────────────────────────────────────────────────────────────
# 2. Unit Tests — Session Tokens
# ─────────────────────────────────────────────────────────────

class TestSessionTokens:

    def test_token_verifies_correctly(self):
        token = create_session_token("user_1", "test@example.com")
        payload = verify_session_token(token)
        assert payload is not None
        assert payload["user_id"] == "user_1"
        assert payload["email"] == "test@example.com"

    def test_tampered_token_rejected(self):
        token = create_session_token("user_1", "test@example.com")
        bad_token = token[:-5] + "XXXXX"
        assert verify_session_token(bad_token) is None

    def test_expired_token_rejected(self):
        token = create_session_token("user_1", "test@example.com", expires_in_seconds=-1)
        assert verify_session_token(token) is None

    def test_empty_token_rejected(self):
        assert verify_session_token("") is None
        assert verify_session_token("   ") is None


# ─────────────────────────────────────────────────────────────
# 3. Unit Tests — RBAC Permission Matrix
# ─────────────────────────────────────────────────────────────

class TestPermissionMatrix:

    def test_admin_has_all_permissions(self):
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN.value]
        assert "project:manage_members" in admin_perms
        assert "overrides:create" in admin_perms
        assert "overrides:revoke" in admin_perms
        assert "documents:delete" in admin_perms
        assert "remediation:delete" in admin_perms

    def test_viewer_cannot_mutate(self):
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER.value]
        assert "overrides:create" not in viewer_perms
        assert "documents:upload" not in viewer_perms
        assert "analysis:run" not in viewer_perms
        assert "verification:run" not in viewer_perms
        assert "notes:create" not in viewer_perms

    def test_reviewer_cannot_override(self):
        assert not has_permission("REVIEWER", "overrides:create")
        assert not has_permission("REVIEWER", "overrides:revoke")

    def test_reviewer_can_add_notes(self):
        assert has_permission("REVIEWER", "notes:create")

    def test_reviewer_can_upload_remediation(self):
        assert has_permission("REVIEWER", "remediation:upload")

    def test_auditor_can_override(self):
        assert has_permission("AUDITOR", "overrides:create")
        assert has_permission("AUDITOR", "overrides:revoke")

    def test_invalid_role_has_no_permissions(self):
        assert not has_permission("UNKNOWN_ROLE", "project:view")

    def test_viewer_can_view_audit(self):
        assert has_permission("VIEWER", "audit:view")


# ─────────────────────────────────────────────────────────────
# 4. API Tests — Authentication
# ─────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_register_new_user(self, auth_ctx):
        client = auth_ctx["client"]
        r = _register(client, "alice@example.com", "Alice", "SecurePass123!")
        assert r.status_code == 201
        data = r.json()
        assert "user" in data
        assert data["user"]["email"] == "alice@example.com"
        assert "password_hash" not in data["user"]
        assert "password" not in data["user"]

    def test_register_invalid_email(self, auth_ctx):
        client = auth_ctx["client"]
        r = _register(client, "not-an-email", "Bob", "SecurePass123!")
        assert r.status_code == 400

    def test_register_weak_password(self, auth_ctx):
        client = auth_ctx["client"]
        r = _register(client, "weak@example.com", "Weak", "abc")
        assert r.status_code == 400

    def test_register_duplicate_email(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "dup@example.com", "Dup", "SecurePass123!")
        r = _register(client, "dup@example.com", "Dup2", "SecurePass123!")
        assert r.status_code == 409

    def test_login_valid_credentials(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "login_test@example.com", "Login Test", "SecurePass123!")
        r = client.post("/api/auth/login", json={"email": "login_test@example.com", "password": "SecurePass123!"})
        assert r.status_code == 200
        data = r.json()
        assert "user" in data
        assert "password_hash" not in data["user"]

    def test_login_wrong_password_generic_error(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "wrongpw@example.com", "WrongPW", "SecurePass123!")
        r = client.post("/api/auth/login", json={"email": "wrongpw@example.com", "password": "WrongPassword!"})
        assert r.status_code == 401
        msg = r.json().get("error", {}).get("message", r.text)
        assert "password" not in msg.lower() or "invalid credentials" in msg.lower()

    def test_login_nonexistent_email_generic_error(self, auth_ctx):
        client = auth_ctx["client"]
        r = client.post("/api/auth/login", json={"email": "nobody@nowhere.com", "password": "SomePass123!"})
        assert r.status_code == 401

    def test_inactive_account_cannot_login(self, auth_ctx):
        client = auth_ctx["client"]
        storage = auth_ctx["storage"]
        _register(client, "inactive@example.com", "Inactive", "SecurePass123!")
        user = _run(storage.get_user_by_email("inactive@example.com"))
        _run(storage.update_user(user["user_id"], {"is_active": False}))
        r = client.post("/api/auth/login", json={"email": "inactive@example.com", "password": "SecurePass123!"})
        assert r.status_code in (401, 403)

    def test_get_me_authenticated(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "me_test@example.com", "Me Test", "SecurePass123!")
        token = _login(client, "me_test@example.com", "SecurePass123!")
        r = client.get("/api/auth/me", headers=_auth_header(token))
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "me_test@example.com"

    def test_get_me_unauthenticated(self, auth_ctx):
        client = auth_ctx["client"]
        client.cookies.clear()
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_logout_clears_cookie(self, auth_ctx):
        client = auth_ctx["client"]
        r = client.post("/api/auth/logout")
        assert r.status_code == 200

    def test_password_hash_never_in_response(self, auth_ctx):
        client = auth_ctx["client"]
        r = _register(client, "nohash@example.com", "NoHash", "SecurePass123!")
        text = r.text
        assert "pbkdf2_sha256" not in text
        assert "password_hash" not in text

        token = _login(client, "nohash@example.com", "SecurePass123!")
        r2 = client.get("/api/auth/me", headers=_auth_header(token))
        assert "pbkdf2_sha256" not in r2.text
        assert "password_hash" not in r2.text


# ─────────────────────────────────────────────────────────────
# 5. API Tests — Project Authorization & Isolation
# ─────────────────────────────────────────────────────────────

class TestProjectAuthorization:

    def test_unauthenticated_project_list_rejected(self, auth_ctx):
        client = auth_ctx["client"]
        client.cookies.clear()
        r = client.get("/api/projects")
        assert r.status_code == 401

    def test_unauthenticated_project_detail_rejected(self, auth_ctx):
        client = auth_ctx["client"]
        client.cookies.clear()
        r = client.get("/api/projects/any-project-id")
        assert r.status_code == 401

    def test_create_project_requires_auth(self, auth_ctx):
        client = auth_ctx["client"]
        client.cookies.clear()
        r = client.post("/api/projects", data={"name": "Test"})
        assert r.status_code == 401

    def test_authenticated_user_can_create_project(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "proj_owner@example.com", "Proj Owner", "SecurePass123!")
        token = _login(client, "proj_owner@example.com", "SecurePass123!")
        r = client.post("/api/projects", data={"name": "My Project"}, headers=_auth_header(token))
        assert r.status_code == 200
        assert "project_id" in r.json()

    def test_creator_is_auto_admin(self, auth_ctx):
        client = auth_ctx["client"]
        storage = auth_ctx["storage"]
        _register(client, "auto_admin@example.com", "Auto Admin", "SecurePass123!")
        token = _login(client, "auto_admin@example.com", "SecurePass123!")
        r = client.post("/api/projects", data={"name": "Auto Admin Project"}, headers=_auth_header(token))
        project_id = r.json()["project_id"]

        user = _run(storage.get_user_by_email("auto_admin@example.com"))
        membership = _run(storage.get_project_member(project_id, user["user_id"]))
        assert membership is not None
        assert membership["role"] == "ADMIN"

    def test_non_member_cannot_access_project(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "owner_iso@example.com", "Owner Iso", "SecurePass123!")
        owner_token = _login(client, "owner_iso@example.com", "SecurePass123!")
        r = client.post("/api/projects", data={"name": "Isolated Project"}, headers=_auth_header(owner_token))
        project_id = r.json()["project_id"]

        _register(client, "outsider_iso@example.com", "Outsider", "SecurePass123!")
        outsider_token = _login(client, "outsider_iso@example.com", "SecurePass123!")
        r2 = client.get(f"/api/projects/{project_id}", headers=_auth_header(outsider_token))
        assert r2.status_code == 403

    def test_project_isolation_project_b_user_cannot_access_project_a(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "user_a_iso@example.com", "User A", "SecurePass123!")
        _register(client, "user_b_iso@example.com", "User B", "SecurePass123!")

        token_a = _login(client, "user_a_iso@example.com", "SecurePass123!")
        token_b = _login(client, "user_b_iso@example.com", "SecurePass123!")

        r = client.post("/api/projects", data={"name": "Project A"}, headers=_auth_header(token_a))
        project_a_id = r.json()["project_id"]

        r2 = client.post("/api/projects", data={"name": "Project B"}, headers=_auth_header(token_b))
        project_b_id = r2.json()["project_id"]

        r3 = client.get(f"/api/projects/{project_b_id}", headers=_auth_header(token_a))
        assert r3.status_code == 403

        r4 = client.get(f"/api/projects/{project_a_id}", headers=_auth_header(token_b))
        assert r4.status_code == 403


# ─────────────────────────────────────────────────────────────
# 6. API Tests — Role-Based Permission Enforcement
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rbac_project(auth_ctx):
    client = auth_ctx["client"]
    storage = auth_ctx["storage"]

    roles_map = {
        "rbac_admin@example.com": "ADMIN",
        "rbac_auditor@example.com": "AUDITOR",
        "rbac_reviewer@example.com": "REVIEWER",
        "rbac_viewer@example.com": "VIEWER",
    }

    tokens = {}
    for email, _ in roles_map.items():
        _register(client, email, email.split("@")[0], "SecurePass123!")
        tokens[email] = _login(client, email, "SecurePass123!")

    admin_token = tokens["rbac_admin@example.com"]
    r = client.post("/api/projects", data={"name": "RBAC Test Project"}, headers=_auth_header(admin_token))
    assert r.status_code == 200, r.text
    project_id = r.json()["project_id"]

    for email, role in roles_map.items():
        if email == "rbac_admin@example.com":
            continue
        user = _run(storage.get_user_by_email(email))
        r2 = client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": user["user_id"], "role": role},
            headers=_auth_header(admin_token),
        )
        assert r2.status_code == 201, f"Adding {role} failed: {r2.text}"

    return {"project_id": project_id, "tokens": tokens, "storage": storage, "client": client}


class TestRolePermissions:

    def test_viewer_can_view_project(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_viewer@example.com"]
        r = client.get(f"/api/projects/{rbac_project['project_id']}", headers=_auth_header(token))
        assert r.status_code == 200

    def test_viewer_cannot_run_analysis(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_viewer@example.com"]
        r = client.post(f"/api/projects/{rbac_project['project_id']}/analyze", headers=_auth_header(token))
        assert r.status_code == 403

    def test_viewer_cannot_run_verification(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_viewer@example.com"]
        r = client.post(f"/api/projects/{rbac_project['project_id']}/verify", headers=_auth_header(token))
        assert r.status_code == 403

    def test_viewer_cannot_upload_documents(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_viewer@example.com"]
        r = client.post(
            f"/api/projects/{rbac_project['project_id']}/documents",
            files={"evidence_files": ("test.txt", b"content", "text/plain")},
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_reviewer_can_view_project(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_reviewer@example.com"]
        r = client.get(f"/api/projects/{rbac_project['project_id']}", headers=_auth_header(token))
        assert r.status_code == 200

    def test_reviewer_cannot_run_analysis(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_reviewer@example.com"]
        r = client.post(f"/api/projects/{rbac_project['project_id']}/analyze", headers=_auth_header(token))
        assert r.status_code == 403

    def test_auditor_can_run_analysis(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_auditor@example.com"]
        r = client.post(f"/api/projects/{rbac_project['project_id']}/analyze", headers=_auth_header(token))
        assert r.status_code in (400, 404, 422, 503)

    def test_admin_can_manage_members(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_admin@example.com"]
        r = client.get(f"/api/projects/{rbac_project['project_id']}/members", headers=_auth_header(token))
        assert r.status_code == 200
        assert "members" in r.json()

    def test_viewer_cannot_manage_members(self, rbac_project):
        client = rbac_project["client"]
        token = rbac_project["tokens"]["rbac_viewer@example.com"]
        r2 = client.post(
            f"/api/projects/{rbac_project['project_id']}/members",
            json={"email": "newuser@example.com", "role": "VIEWER"},
            headers=_auth_header(token),
        )
        assert r2.status_code == 403


# ─────────────────────────────────────────────────────────────
# 7. API Tests — Auditor Override Governance
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def override_project(auth_ctx):
    client = auth_ctx["client"]
    storage = auth_ctx["storage"]

    emails = {
        "ov_admin@example.com": "ADMIN",
        "ov_auditor@example.com": "AUDITOR",
        "ov_reviewer@example.com": "REVIEWER",
        "ov_viewer@example.com": "VIEWER",
    }
    tokens = {}
    for email, _ in emails.items():
        _register(client, email, email.split("@")[0], "SecurePass123!")
        tokens[email] = _login(client, email, "SecurePass123!")

    admin_token = tokens["ov_admin@example.com"]
    r = client.post("/api/projects", data={"name": "Override Governance Project"}, headers=_auth_header(admin_token))
    project_id = r.json()["project_id"]

    for email, role in emails.items():
        if email == "ov_admin@example.com":
            continue
        user = _run(storage.get_user_by_email(email))
        client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": user["user_id"], "role": role},
            headers=_auth_header(admin_token),
        )

    return {"project_id": project_id, "tokens": tokens, "client": client}


class TestOverrideGovernance:

    def test_auditor_can_create_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_auditor@example.com"]
        r = client.post(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            json={
                "overridden_status": "SATISFIED",
                "auditor_reason": "Manual review confirms compliance.",
            },
            headers=_auth_header(token),
        )
        assert r.status_code != 403

    def test_reviewer_cannot_create_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_reviewer@example.com"]
        r = client.post(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            json={
                "overridden_status": "SATISFIED",
                "auditor_reason": "Reviewer trying to override.",
            },
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_create_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_viewer@example.com"]
        r = client.post(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            json={
                "overridden_status": "SATISFIED",
                "auditor_reason": "Viewer trying to override.",
            },
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_auditor_can_revoke_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_auditor@example.com"]
        r = client.delete(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            headers=_auth_header(token),
        )
        assert r.status_code != 403

    def test_reviewer_cannot_revoke_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_reviewer@example.com"]
        r = client.delete(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_revoke_override(self, override_project):
        client = override_project["client"]
        token = override_project["tokens"]["ov_viewer@example.com"]
        r = client.delete(
            f"/api/projects/{override_project['project_id']}/requirements/REQ-001/override",
            headers=_auth_header(token),
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# 8. API Tests — Remediation Upload Governance
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def remed_project(auth_ctx):
    client = auth_ctx["client"]
    storage = auth_ctx["storage"]

    emails = {
        "rem_admin@example.com": "ADMIN",
        "rem_auditor@example.com": "AUDITOR",
        "rem_reviewer@example.com": "REVIEWER",
        "rem_viewer@example.com": "VIEWER",
    }
    tokens = {}
    for email, _ in emails.items():
        _register(client, email, email.split("@")[0], "SecurePass123!")
        tokens[email] = _login(client, email, "SecurePass123!")

    admin_token = tokens["rem_admin@example.com"]
    r = client.post("/api/projects", data={"name": "Remediation RBAC Project"}, headers=_auth_header(admin_token))
    project_id = r.json()["project_id"]

    for email, role in emails.items():
        if email == "rem_admin@example.com":
            continue
        user = _run(storage.get_user_by_email(email))
        client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": user["user_id"], "role": role},
            headers=_auth_header(admin_token),
        )

    return {"project_id": project_id, "tokens": tokens, "client": client}


class TestRemediationUploadGovernance:

    def test_auditor_can_upload_remediation(self, remed_project):
        client = remed_project["client"]
        token = remed_project["tokens"]["rem_auditor@example.com"]
        r = client.post(
            f"/api/projects/{remed_project['project_id']}/tasks/task-001/uploads",
            files={"file": ("evidence.txt", b"evidence content", "text/plain")},
            data={"requirement_id": "REQ-001", "description": "Evidence for REQ-001"},
            headers=_auth_header(token),
        )
        assert r.status_code != 403

    def test_reviewer_can_upload_remediation(self, remed_project):
        client = remed_project["client"]
        token = remed_project["tokens"]["rem_reviewer@example.com"]
        r = client.post(
            f"/api/projects/{remed_project['project_id']}/tasks/task-001/uploads",
            files={"file": ("reviewer_evidence.txt", b"reviewer evidence", "text/plain")},
            data={"requirement_id": "REQ-001"},
            headers=_auth_header(token),
        )
        assert r.status_code != 403

    def test_viewer_cannot_upload_remediation(self, remed_project):
        client = remed_project["client"]
        token = remed_project["tokens"]["rem_viewer@example.com"]
        r = client.post(
            f"/api/projects/{remed_project['project_id']}/tasks/task-001/uploads",
            files={"file": ("viewer_evidence.txt", b"viewer evidence", "text/plain")},
            data={"requirement_id": "REQ-001"},
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_viewer_cannot_delete_upload(self, remed_project):
        client = remed_project["client"]
        token = remed_project["tokens"]["rem_viewer@example.com"]
        r = client.delete(
            f"/api/projects/{remed_project['project_id']}/uploads/any-upload-id",
            headers=_auth_header(token),
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# 9. API Tests — Report Export Governance
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def report_project(auth_ctx):
    client = auth_ctx["client"]
    _register(client, "rep_admin@example.com", "Rep Admin", "SecurePass123!")
    _register(client, "rep_nonmember@example.com", "Rep NonMember", "SecurePass123!")

    admin_token = _login(client, "rep_admin@example.com", "SecurePass123!")
    nonmember_token = _login(client, "rep_nonmember@example.com", "SecurePass123!")

    r = client.post("/api/projects", data={"name": "Report RBAC Project"}, headers=_auth_header(admin_token))
    project_id = r.json()["project_id"]

    return {"project_id": project_id, "admin_token": admin_token, "nonmember_token": nonmember_token, "client": client}


class TestReportExportGovernance:

    def test_non_member_cannot_export_report(self, report_project):
        client = report_project["client"]
        token = report_project["nonmember_token"]
        r = client.get(
            f"/api/projects/{report_project['project_id']}/verification-runs/any-run-id/report.pdf",
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_admin_can_request_report(self, report_project):
        client = report_project["client"]
        token = report_project["admin_token"]
        r = client.get(
            f"/api/projects/{report_project['project_id']}/verification-runs/any-run-id/report.pdf",
            headers=_auth_header(token),
        )
        assert r.status_code not in (401, 403)


# ─────────────────────────────────────────────────────────────
# 10. API Tests — Audit Log Security
# ─────────────────────────────────────────────────────────────

class TestAuditLogSecurity:

    def test_human_actions_contain_actor_id(self, auth_ctx):
        client = auth_ctx["client"]
        storage = auth_ctx["storage"]

        _register(client, "audit_actor@example.com", "Audit Actor", "SecurePass123!")
        token = _login(client, "audit_actor@example.com", "SecurePass123!")
        r = client.post("/api/projects", data={"name": "Audit Actor Project"}, headers=_auth_header(token))
        project_id = r.json()["project_id"]

        user = _run(storage.get_user_by_email("audit_actor@example.com"))
        events = _run(storage.list_audit_events(project_id))
        created_events = [e for e in events if e.get("event_type") == "PROJECT_CREATED"]
        assert len(created_events) > 0
        assert created_events[0].get("actor_id") == user["user_id"]

    def test_secrets_not_in_audit_events(self, auth_ctx):
        client = auth_ctx["client"]
        storage = auth_ctx["storage"]

        _register(client, "nosecrets@example.com", "No Secrets", "MySecretPassword99!")
        token = _login(client, "nosecrets@example.com", "MySecretPassword99!")
        r = client.post("/api/projects", data={"name": "No Secrets Project"}, headers=_auth_header(token))
        project_id = r.json()["project_id"]

        events = _run(storage.list_audit_events(project_id))
        for evt in events:
            evt_str = str(evt)
            assert "pbkdf2_sha256" not in evt_str
            assert "password_hash" not in evt_str
            assert "MySecretPassword99!" not in evt_str

    def test_audit_events_require_project_membership(self, auth_ctx):
        client = auth_ctx["client"]
        _register(client, "audit_nonmember@example.com", "Audit NonMember", "SecurePass123!")
        _register(client, "audit_owner@example.com", "Audit Owner", "SecurePass123!")

        owner_token = _login(client, "audit_owner@example.com", "SecurePass123!")
        r = client.post("/api/projects", data={"name": "Audit Restricted Project"}, headers=_auth_header(owner_token))
        project_id = r.json()["project_id"]

        nonmember_token = _login(client, "audit_nonmember@example.com", "SecurePass123!")
        r2 = client.get(f"/api/projects/{project_id}/audit-events", headers=_auth_header(nonmember_token))
        assert r2.status_code == 403


# ─────────────────────────────────────────────────────────────
# 11. API Tests — Member Management Governance
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def member_mgmt_project(auth_ctx):
    client = auth_ctx["client"]
    storage = auth_ctx["storage"]

    _register(client, "mgmt_admin@example.com", "Mgmt Admin", "SecurePass123!")
    _register(client, "mgmt_member@example.com", "Mgmt Member", "SecurePass123!")

    admin_token = _login(client, "mgmt_admin@example.com", "SecurePass123!")
    r = client.post("/api/projects", data={"name": "Member Mgmt Project"}, headers=_auth_header(admin_token))
    project_id = r.json()["project_id"]

    member_user = _run(storage.get_user_by_email("mgmt_member@example.com"))
    r2 = client.post(
        f"/api/projects/{project_id}/members",
        json={"user_id": member_user["user_id"], "role": "REVIEWER"},
        headers=_auth_header(admin_token),
    )
    assert r2.status_code == 201

    member_token = _login(client, "mgmt_member@example.com", "SecurePass123!")

    return {
        "project_id": project_id,
        "admin_token": admin_token,
        "member_token": member_token,
        "member_user": member_user,
        "storage": storage,
        "client": client,
    }


class TestMemberManagement:

    def test_admin_can_list_members(self, member_mgmt_project):
        client = member_mgmt_project["client"]
        token = member_mgmt_project["admin_token"]
        r = client.get(
            f"/api/projects/{member_mgmt_project['project_id']}/members",
            headers=_auth_header(token),
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["members"]) >= 2

    def test_non_admin_cannot_add_member(self, member_mgmt_project):
        client = member_mgmt_project["client"]
        token = member_mgmt_project["member_token"]
        r = client.post(
            f"/api/projects/{member_mgmt_project['project_id']}/members",
            json={"email": "new@example.com", "role": "VIEWER"},
            headers=_auth_header(token),
        )
        assert r.status_code == 403

    def test_admin_can_change_member_role(self, member_mgmt_project):
        client = member_mgmt_project["client"]
        token = member_mgmt_project["admin_token"]
        member_user = member_mgmt_project["member_user"]
        r = client.put(
            f"/api/projects/{member_mgmt_project['project_id']}/members/{member_user['user_id']}",
            json={"role": "AUDITOR"},
            headers=_auth_header(token),
        )
        assert r.status_code == 200
        assert r.json()["member"]["role"] == "AUDITOR"

    def test_cannot_remove_last_admin(self, member_mgmt_project):
        client = member_mgmt_project["client"]
        token = member_mgmt_project["admin_token"]
        storage = member_mgmt_project["storage"]

        admin_user = _run(storage.get_user_by_email("mgmt_admin@example.com"))
        r = client.delete(
            f"/api/projects/{member_mgmt_project['project_id']}/members/{admin_user['user_id']}",
            headers=_auth_header(token),
        )
        assert r.status_code == 400
        assert "last" in r.json().get("error", {}).get("message", "").lower() or "admin" in r.json().get("error", {}).get("message", "").lower()

    def test_invalid_role_rejected(self, member_mgmt_project):
        client = member_mgmt_project["client"]
        token = member_mgmt_project["admin_token"]
        member_user = member_mgmt_project["member_user"]
        r = client.put(
            f"/api/projects/{member_mgmt_project['project_id']}/members/{member_user['user_id']}",
            json={"role": "SUPERUSER"},
            headers=_auth_header(token),
        )
        assert r.status_code == 400
