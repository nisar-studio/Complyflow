"""
ComplyFlow — Authentication & User Management API Routes

Provides:
  POST /api/auth/register
  POST /api/auth/login
  POST /api/auth/logout
  GET  /api/auth/me
  GET  /api/auth/bootstrap    (first-run dev bootstrap)

  POST /api/projects/{id}/members
  GET  /api/projects/{id}/members
  PUT  /api/projects/{id}/members/{user_id}
  DELETE /api/projects/{id}/members/{user_id}

  GET  /api/admin/users       (ADMIN only)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from app.services.auth_service import (
    Role,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    create_session_token,
    create_authenticated_session,
    verify_session_token,
    set_session_cookies,
    clear_session_cookies,
    _extract_token_from_request,
    ensure_bootstrap_admin,
    get_current_user,
    get_project_member_context,
    hash_password,
    has_permission,
    require_permission,
    require_role,
    verify_password,
)
from app.services.audit_service import record_audit_event
from app.services.storage import get_storage

auth_router = APIRouter(prefix="/api")


# ─────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AddMemberRequest(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: str


class UpdateMemberRoleRequest(BaseModel):
    role: str


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

PASSWORD_MIN_LEN = 8
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _safe_user(user: dict) -> dict:
    """Strip password hash before sending to client."""
    return {k: v for k, v in user.items() if k not in ("password_hash",)}


def _validate_password_strength(password: str) -> Optional[str]:
    if len(password) < PASSWORD_MIN_LEN:
        return f"Password must be at least {PASSWORD_MIN_LEN} characters."
    return None


# ─────────────────────────────────────────────────────────────
# POST /api/auth/register
# ─────────────────────────────────────────────────────────────

@auth_router.post("/auth/register", status_code=201)
async def register(payload: RegisterRequest):
    """
    Register a new user account.
    Returns the created user (without password) and sets HttpOnly session cookie.
    """
    storage = get_storage()

    email = payload.email.strip().lower()
    name = payload.name.strip()
    password = payload.password

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")

    pw_error = _validate_password_strength(password)
    if pw_error:
        raise HTTPException(status_code=400, detail=pw_error)

    # Check uniqueness — generic message
    existing = await storage.get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    pw_hash = hash_password(password)
    user_data = {
        "email": email,
        "name": name,
        "password_hash": pw_hash,
        "is_active": True,
    }
    user_id = await storage.create_user(user_data)
    user = await storage.get_user_by_id(user_id)

    token, session_id, csrf_token = await create_authenticated_session(
        user_id=user_id,
        email=email,
        storage=storage,
    )
    response = JSONResponse(
        status_code=201,
        content={"user": _safe_user(user), "message": "Account created successfully."},
    )
    set_session_cookies(response, token=token, csrf_token=csrf_token)
    return response


# ─────────────────────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────────────────────

@auth_router.post("/auth/login")
async def login(payload: LoginRequest):
    """
    Log in with email and password.
    Sets an HTTP-only session cookie and client-readable CSRF cookie.
    """
    storage = get_storage()
    email = payload.email.strip().lower()
    password = payload.password

    # Generic error — do not reveal whether email exists
    _CRED_ERROR = HTTPException(
        status_code=401,
        detail="Invalid credentials.",
    )

    user = await storage.get_user_by_email(email)
    if not user:
        # Constant-time resistance to timing side-channels
        hash_password("dummy-timing-resistance")
        raise _CRED_ERROR

    if not verify_password(password, user.get("password_hash", "")):
        raise _CRED_ERROR

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="This account is deactivated.")

    token, session_id, csrf_token = await create_authenticated_session(
        user_id=user["user_id"],
        email=user["email"],
        storage=storage,
    )
    response = JSONResponse(
        content={"user": _safe_user(user), "message": "Logged in successfully."}
    )
    set_session_cookies(response, token=token, csrf_token=csrf_token)
    return response


# ─────────────────────────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────────────────────────

@auth_router.post("/auth/logout")
async def logout(
    request: Request,
    token: Optional[str] = Depends(_extract_token_from_request),
):
    """Invalidate server-side session and clear the session cookie."""
    if token:
        payload = verify_session_token(token)
        if payload and payload.get("session_id"):
            storage = get_storage()
            try:
                await storage.revoke_session(payload["session_id"])
            except Exception:
                pass

    response = JSONResponse(content={"message": "Logged out successfully."})
    clear_session_cookies(response)
    return response



# ─────────────────────────────────────────────────────────────
# GET /api/auth/me
# ─────────────────────────────────────────────────────────────

@auth_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user profile."""
    return {"user": current_user}


# ─────────────────────────────────────────────────────────────
# GET /api/auth/bootstrap (First-run admin creation)
# ─────────────────────────────────────────────────────────────

@auth_router.post("/auth/bootstrap")
async def bootstrap_admin():
    """
    Development bootstrap: Creates the initial ADMIN account if no users exist.

    Default admin credentials:
      Email:    admin@complyflow.local
      Password: Admin@ComplyFlow123!

    This endpoint is only effective when the users table is empty.
    On a populated database it returns the existing admin safely (no mutation).
    """
    storage = get_storage()
    count = await storage.count_users()
    if count > 0:
        return {
            "message": "Bootstrap skipped — users already exist.",
            "users_count": count,
        }
    admin = await ensure_bootstrap_admin(storage)
    return {
        "message": "Bootstrap admin created.",
        "credentials_hint": "Email: admin@complyflow.local | Password: Admin@ComplyFlow123!",
        "admin": admin,
    }


# ─────────────────────────────────────────────────────────────
# Project Member Management  (ADMIN only)
# ─────────────────────────────────────────────────────────────

@auth_router.get("/projects/{project_id}/members")
async def list_members(
    project_id: str,
    ctx: dict = Depends(get_project_member_context),
):
    """List all members of a project. Requires project membership."""
    storage = get_storage()
    members = await storage.list_project_members(project_id)
    return {"members": members, "count": len(members)}


@auth_router.post("/projects/{project_id}/members", status_code=201)
async def add_member(
    project_id: str,
    payload: AddMemberRequest,
    ctx: dict = Depends(require_permission("project:manage_members")),
):
    """
    Add a user to the project with an assigned role.
    ADMIN only. Either user_id or email must be provided.
    """
    storage = get_storage()

    if not Role.is_valid(payload.role):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'. Valid roles: {Role.all_roles()}",
        )

    # Resolve user
    target_user = None
    if payload.user_id:
        target_user = await storage.get_user_by_id(payload.user_id)
    elif payload.email:
        target_user = await storage.get_user_by_email(payload.email.strip().lower())

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    target_uid = target_user["user_id"]

    membership_id = await storage.add_project_member(project_id, target_uid, payload.role.upper())
    member = await storage.get_project_member(project_id, target_uid)

    actor = ctx.get("user", {})
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="MEMBER_ADDED",
        actor_type="AUDITOR",
        actor_id=actor.get("user_id"),
        summary=f"User '{target_user.get('email')}' added to project with role '{payload.role.upper()}'.",
        metadata={"target_user_id": target_uid, "email": target_user.get("email"), "role": payload.role.upper()},
    )

    return {"message": "Member added.", "membership_id": membership_id, "member": member}


@auth_router.put("/projects/{project_id}/members/{target_user_id}")
async def update_member_role(
    project_id: str,
    target_user_id: str,
    payload: UpdateMemberRoleRequest,
    ctx: dict = Depends(require_permission("project:manage_members")),
):
    """
    Update a project member's role.
    Cannot remove the last ADMIN from the project.
    """
    storage = get_storage()

    if not Role.is_valid(payload.role):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{payload.role}'.",
        )

    existing_member = await storage.get_project_member(project_id, target_user_id)
    if not existing_member:
        raise HTTPException(status_code=404, detail="Member not found in this project.")

    # Guard: cannot remove last ADMIN by role-change
    if existing_member["role"] == Role.ADMIN.value and payload.role.upper() != Role.ADMIN.value:
        all_members = await storage.list_project_members(project_id)
        admin_count = sum(1 for m in all_members if m["role"] == Role.ADMIN.value)
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot change role of the last ADMIN in this project.",
            )

    updated = await storage.update_project_member_role(project_id, target_user_id, payload.role.upper())
    if not updated:
        raise HTTPException(status_code=400, detail="Role update failed.")

    member = await storage.get_project_member(project_id, target_user_id)

    actor = ctx.get("user", {})
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="MEMBER_ROLE_UPDATED",
        actor_type="AUDITOR",
        actor_id=actor.get("user_id"),
        summary=f"Member '{target_user_id}' role changed from '{existing_member.get('role')}' to '{payload.role.upper()}'.",
        metadata={"target_user_id": target_user_id, "previous_role": existing_member.get("role"), "new_role": payload.role.upper()},
    )

    return {"message": "Role updated.", "member": member}


@auth_router.delete("/projects/{project_id}/members/{target_user_id}", status_code=200)
async def remove_member(
    project_id: str,
    target_user_id: str,
    ctx: dict = Depends(require_permission("project:manage_members")),
):
    """Remove a user from the project. Cannot remove the last ADMIN."""
    storage = get_storage()
    current_user = ctx["user"]

    existing_member = await storage.get_project_member(project_id, target_user_id)
    if not existing_member:
        raise HTTPException(status_code=404, detail="Member not found.")

    if existing_member["role"] == Role.ADMIN.value:
        all_members = await storage.list_project_members(project_id)
        admin_count = sum(1 for m in all_members if m["role"] == Role.ADMIN.value)
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last ADMIN from this project.",
            )

    removed = await storage.remove_project_member(project_id, target_user_id)
    if not removed:
        raise HTTPException(status_code=400, detail="Removal failed.")

    actor = ctx.get("user", {})
    await record_audit_event(
        storage=storage,
        project_id=project_id,
        event_type="MEMBER_REMOVED",
        actor_type="AUDITOR",
        actor_id=actor.get("user_id"),
        summary=f"Member '{target_user_id}' removed from project.",
        metadata={"target_user_id": target_user_id, "previous_role": existing_member.get("role")},
    )

    return {"message": "Member removed.", "user_id": target_user_id}



# ─────────────────────────────────────────────────────────────
# Admin: Global User List
# ─────────────────────────────────────────────────────────────

@auth_router.get("/admin/users")
async def list_all_users(
    current_user: dict = Depends(get_current_user),
):
    """
    List all registered users (safe — no password hashes).
    Restricted to authenticated users only; ADMIN status not enforced globally
    since projects are the RBAC boundary.
    """
    storage = get_storage()
    users = await storage.list_users()
    return {"users": users, "count": len(users)}
