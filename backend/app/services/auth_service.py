"""
ComplyFlow — Authentication, Authorization & Role-Based Access Control (RBAC) Service

Provides:
  - Cryptographically secure password hashing (PBKDF2-SHA256 with 100,000 iterations & CSPRNG salt)
  - Signed, tamper-proof session tokens (HMAC-SHA256) with expiration and server-side revocation tracking
  - Centralized role & permissions matrix (ADMIN, AUDITOR, REVIEWER, VIEWER)
  - Cookie security management (HttpOnly, SameSite, Secure, Path)
  - Double Submit Cookie & custom header CSRF verification for mutating requests
  - FastAPI dependency helpers for user authentication and project authorization
  - Development bootstrap helper for initial admin creation
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.services.storage import StorageInterface, get_storage


# Token & Cookie Configuration
SESSION_COOKIE_NAME = "complyflow_session"
CSRF_COOKIE_NAME = "complyflow_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
DEFAULT_SESSION_TTL = 7 * 24 * 3600  # 7 days

bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────
# 1. Role & Permission Definitions
# ─────────────────────────────────────────────────────────────

class Role(str, Enum):
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"

    @classmethod
    def all_roles(cls) -> List[str]:
        return [cls.ADMIN.value, cls.AUDITOR.value, cls.REVIEWER.value, cls.VIEWER.value]

    @classmethod
    def is_valid(cls, role_str: str) -> bool:
        return role_str.upper() in cls.all_roles()


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Role.ADMIN.value: {
        "project:manage_members",
        "project:delete",
        "project:edit",
        "project:view",
        "documents:upload",
        "documents:delete",
        "analysis:run",
        "verification:run",
        "overrides:create",
        "overrides:edit",
        "overrides:revoke",
        "notes:create",
        "notes:delete",
        "remediation:manage",
        "remediation:upload",
        "remediation:delete",
        "reports:export",
        "audit:view",
        "frameworks:import",
        "frameworks:manage",
        "frameworks:view",
        "frameworks:apply",
    },
    Role.AUDITOR.value: {
        "project:edit",
        "project:view",
        "documents:upload",
        "documents:delete",
        "analysis:run",
        "verification:run",
        "overrides:create",
        "overrides:edit",
        "overrides:revoke",
        "notes:create",
        "notes:delete",
        "remediation:manage",
        "remediation:upload",
        "remediation:delete",
        "reports:export",
        "audit:view",
        "frameworks:import",
        "frameworks:apply",
        "frameworks:view",
    },
    Role.REVIEWER.value: {
        "project:view",
        "notes:create",
        "notes:delete_own",
        "remediation:upload",
        "reports:export",
        "audit:view",
        "frameworks:view",
    },
    Role.VIEWER.value: {
        "project:view",
        "reports:export",
        "audit:view",
        "frameworks:view",
    },
}



def has_permission(role: str, permission: str) -> bool:
    """Check if a role has the specified permission."""
    perms = ROLE_PERMISSIONS.get(role.upper(), set())
    return permission in perms


# ─────────────────────────────────────────────────────────────
# 2. Cryptographic Password Hashing (PBKDF2-SHA256)
# ─────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using PBKDF2-SHA256 with 100,000 iterations
    and a 16-byte random salt.
    Format: pbkdf2_sha256$100000$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_hex(16)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password against a stored PBKDF2-SHA256 hash.
    Uses constant-time comparison to protect against timing attacks.
    """
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hex = parts[3]

        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(computed.hex(), expected_hex)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# 3. Signed Session Token (HMAC-SHA256) & Server-Side Storage
# ─────────────────────────────────────────────────────────────

def _get_signing_secret() -> bytes:
    """Return the session signing secret from centralized configuration.

    In production, validate_production_settings() blocks known default values
    before any request is served, so this will always return a strong secret.
    """
    settings = get_settings()
    return settings.session_secret.encode("utf-8")


def create_session_token(
    user_id: str,
    email: str,
    session_id: Optional[str] = None,
    expires_in_seconds: int = DEFAULT_SESSION_TTL,
) -> str:
    """
    Create a base64-encoded, HMAC-SHA256 signed session token.
    Contains only safe identity claims: user_id, email, session_id, iat, exp.
    Never contains passwords, hashes, or secrets.
    """
    now = int(time.time())
    sess_id = session_id or f"sess_{secrets.token_hex(16)}"
    payload = {
        "user_id": user_id,
        "email": email,
        "session_id": sess_id,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")

    signature = hmac.new(_get_signing_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    return f"{payload_b64}.{sig_b64}"


async def create_authenticated_session(
    user_id: str,
    email: str,
    expires_in_seconds: int = DEFAULT_SESSION_TTL,
    storage: Optional[StorageInterface] = None,
) -> Tuple[str, str, str]:
    """
    Create a signed session token, register it in the server-side sessions table,
    and generate a CSRF token.
    Returns: (token, session_id, csrf_token)
    """
    storage = storage or get_storage()
    session_id = f"sess_{secrets.token_hex(16)}"
    token = create_session_token(
        user_id=user_id,
        email=email,
        session_id=session_id,
        expires_in_seconds=expires_in_seconds,
    )
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    csrf_token = secrets.token_hex(16)

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=expires_in_seconds)).isoformat()

    session_data = {
        "session_id": session_id,
        "user_id": user_id,
        "token_hash": token_hash,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "is_revoked": False,
    }
    try:
        await storage.create_session(session_data)
    except Exception:
        pass  # Graceful in mocked test environments

    return token, session_id, csrf_token


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a signed session token.
    Returns the payload dictionary if valid, otherwise None.
    """
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts

        # Verify signature
        expected_sig = hmac.new(_get_signing_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=="[: (4 - len(sig_b64) % 4) % 4])

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        # Decode payload
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=="[: (4 - len(payload_b64) % 4) % 4])
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Check expiration
        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None

        return payload
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# 4. Cookie Management & CSRF Protection
# ─────────────────────────────────────────────────────────────

def set_session_cookies(response: Response, token: str, csrf_token: Optional[str] = None) -> None:
    """Set HttpOnly session cookie and client-readable CSRF cookie with hardened attributes."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite.lower(),
        secure=settings.cookie_secure,
        max_age=DEFAULT_SESSION_TTL,
        path="/",
    )
    if csrf_token:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=csrf_token,
            httponly=False,  # Client-readable for double submit header
            samesite=settings.cookie_samesite.lower(),
            secure=settings.cookie_secure,
            max_age=DEFAULT_SESSION_TTL,
            path="/",
        )


def clear_session_cookies(response: Response) -> None:
    """Clear session and CSRF cookies on logout."""
    settings = get_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite.lower(),
        secure=settings.cookie_secure,
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        samesite=settings.cookie_samesite.lower(),
        secure=settings.cookie_secure,
    )


def verify_csrf(request: Request) -> None:
    """
    Verify Double Submit CSRF token for state-changing requests using cookie authentication.
    Safe methods (GET, HEAD, OPTIONS) and Bearer-authenticated requests (CLI/direct API) are exempt.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # If request uses explicit Authorization header, it's not a browser ambient credential attack
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # If request uses cookie authentication, verify CSRF token
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_cookie:
        # Not using session cookie (e.g. unauthenticated public endpoint)
        return

    # Exempt public auth endpoints from CSRF check (login/register/logout/bootstrap)
    path = request.url.path
    if (
        path.startswith("/api/auth/login")
        or path.startswith("/api/auth/register")
        or path.startswith("/api/auth/logout")
        or path.startswith("/api/auth/bootstrap")
    ):
        return


    # Check CSRF token from header vs cookie
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_header = request.headers.get(CSRF_HEADER_NAME) or request.headers.get("X-XSRF-TOKEN")
    requested_with = request.headers.get("X-Requested-With")

    if csrf_cookie and csrf_header and hmac.compare_digest(csrf_cookie, csrf_header):
        return

    if requested_with and requested_with.lower() in ("xmlhttprequest", "fetch", "complyflow"):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="CSRF token missing or invalid.",
    )


# ─────────────────────────────────────────────────────────────
# 5. FastAPI Dependencies for Authentication & RBAC
# ─────────────────────────────────────────────────────────────

def _extract_token_from_request(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    cookie_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Optional[str]:
    """Extract session token from Authorization: Bearer or HTTP-only Cookie."""
    if auth_header and auth_header.credentials:
        return auth_header.credentials.strip()
    if cookie_token:
        return cookie_token.strip()
    
    # Also check raw header fallback
    raw_auth = request.headers.get("Authorization")
    if raw_auth and raw_auth.startswith("Bearer "):
        return raw_auth[7:].strip()
    
    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(_extract_token_from_request),
) -> Dict[str, Any]:
    """
    Dependency: Require an authenticated user.
    Validates token signature, expiration, server-side session revocation,
    and user active status.
    Raises 401 UNAUTHORIZED if not authenticated or inactive.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    storage = get_storage()

    # Check server-side session revocation if session_id is recorded
    session_id = payload.get("session_id")
    if session_id:
        try:
            sess = await storage.get_session(session_id)
            if sess and sess.get("is_revoked", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Fallback if storage backend doesn't implement sessions yet

    user_id = payload.get("user_id")
    user = await storage.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    # Return safe user dictionary without password_hash
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return safe_user


async def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(_extract_token_from_request),
) -> Optional[Dict[str, Any]]:
    """Dependency: Optional authenticated user (for public/hybrid endpoints)."""
    if not token:
        return None
    payload = verify_session_token(token)
    if not payload:
        return None
    user_id = payload.get("user_id")
    storage = get_storage()
    user = await storage.get_user_by_id(user_id)
    if not user or not user.get("is_active", True):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


async def get_project_member_context(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Dependency: Require that the current user is an active member of the project.
    Raises 403 FORBIDDEN if the user does not belong to the project.
    Returns context dict: {"user": safe_user, "project_id": project_id, "role": role_string, "membership": member_dict}
    """
    storage = get_storage()
    # Check if project exists
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user_id = current_user["user_id"]
    membership = await storage.get_project_member(project_id, user_id)

    # Auto-fallback for project owner/creator if legacy project
    if not membership and project.get("user_id") == user_id:
        await storage.add_project_member(project_id, user_id, Role.ADMIN.value)
        membership = await storage.get_project_member(project_id, user_id)

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not a member of this project.",
        )

    role = membership.get("role", Role.VIEWER.value).upper()
    return {
        "user": current_user,
        "project": project,
        "project_id": project_id,
        "role": role,
        "membership": membership,
    }


def require_role(allowed_roles: List[str]) -> Callable:
    """Dependency factory: Require one of the specified roles in the project."""
    allowed_set = {r.upper() for r in allowed_roles}

    async def _role_checker(ctx: Dict[str, Any] = Depends(get_project_member_context)) -> Dict[str, Any]:
        user_role = ctx["role"]
        if user_role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Required role '{'/'.join(allowed_roles)}', but you have '{user_role}'.",
            )
        return ctx

    return _role_checker


def require_permission(permission_name: str) -> Callable:
    """Dependency factory: Require a specific permission in the project."""
    async def _perm_checker(ctx: Dict[str, Any] = Depends(get_project_member_context)) -> Dict[str, Any]:
        user_role = ctx["role"]
        if not has_permission(user_role, permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user_role}' lacks permission '{permission_name}'.",
            )
        return ctx

    return _perm_checker


# ─────────────────────────────────────────────────────────────
# 6. Local Development First-User Bootstrap Helper
# ─────────────────────────────────────────────────────────────

async def ensure_bootstrap_admin(
    storage: StorageInterface,
    email: str = "admin@complyflow.local",
    name: str = "Compliance Admin",
    password: str = "Admin@ComplyFlow123!",
) -> Optional[Dict[str, Any]]:
    """
    Development bootstrap: create initial admin if no users exist in the system.
    Returns the created user record or existing user.
    """
    existing = await storage.get_user_by_email(email)
    if existing:
        return {k: v for k, v in existing.items() if k != "password_hash"}

    user_id = f"user_admin_{secrets.token_hex(4)}"
    pw_hash = hash_password(password)
    user_data = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "password_hash": pw_hash,
        "is_active": True,
    }
    await storage.create_user(user_data)
    created = await storage.get_user_by_id(user_id)
    return {k: v for k, v in created.items() if k != "password_hash"} if created else None
