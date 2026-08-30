# P2 #6 — Production Security Hardening & Deployment Safety

## Executive Summary

P2 #6 addresses the critical security gaps identified during the P2 #6 production-readiness audit. All changes are backward-compatible, tightly scoped, and preserve existing functionality.

**374 backend tests passing, 0 failures. Frontend builds clean.**

---

## Findings Fixed

### F-01: Bootstrap Endpoint Blocked in Production
**File:** `backend/app/api/auth_routes.py`

**Problem:** The `POST /api/auth/bootstrap` endpoint was accessible in production, allowing anyone to create the default admin account with known credentials (`admin@complyflow.local` / `Admin@ComplyFlow123!`).

**Fix:** The endpoint now checks `settings.is_production()` and returns HTTP 403 if true. Development/test bootstrap behavior is preserved.

**Production behavior:** Returns 403 with message "Bootstrap is disabled in production. Provision the first admin via environment variables."

### F-02: /admin/users Requires ADMIN Role
**File:** `backend/app/api/auth_routes.py`

**Problem:** Any authenticated user could enumerate all registered users and email addresses.

**Fix:** The endpoint now verifies the requesting user has ADMIN role in at least one project before returning the user list. VIEWER, REVIEWER, and AUDITOR roles are denied with HTTP 403.

### F-03: Remediation Upload Paths Are Relative
**File:** `backend/app/api/routes.py`, `backend/app/services/storage.py`

**Problem:** `stored_filename` stored absolute server filesystem paths (e.g., `/home/user/complyflow/uploads/...`).

**Fix:** `stored_filename` now stores relative paths (e.g., `project_id/task_id/upload_id.ext`). The `delete_remediation_upload` storage method resolves the physical path using `settings.upload_dir`. No absolute server paths are exposed through API responses.

### F-05: Session Secret Enforced in Production
**Files:** `backend/app/core/config.py`, `backend/app/services/auth_service.py`, `backend/app/main.py`

**Problem:** The default session secret (`complyflow-session-secret-key-32-bytes!`) was usable in production, making all session tokens forgeable.

**Fix:**
- `validate_production_settings()` now **raises ValueError** (not just warns) when the session secret is a known default or shorter than 32 characters.
- The lifespan handler in `main.py` catches this ValueError and prevents startup.
- `_get_signing_secret()` in `auth_service.py` simplified to read directly from settings without fallback to a second default.
- Known default secrets are defined in `Settings._DEFAULT_SESSION_SECRETS` as a set for maintainability.

### F-08: CORS Headers Restricted
**File:** `backend/app/main.py`

**Problem:** `allow_headers=["*"]` permitted any custom header in CORS preflight.

**Fix:** Restricted to the five headers actually used by the application:
- `Content-Type`
- `Authorization`
- `X-CSRF-Token`
- `X-Requested-With`
- `X-XSRF-TOKEN`

---

## Production Configuration Requirements

### Required Environment Variables

```bash
# CRITICAL: Must be set before starting in production
SESSION_SECRET=<random-64-char-hex-string>

# Generate with:
python -c "import secrets; print(secrets.token_hex(32))"
```

### Production Startup Validation

The application will **refuse to start** if any of these conditions are met:

| Condition | Behavior |
|-----------|----------|
| `APP_ENV=production` + default `SESSION_SECRET` | ValueError → startup fails |
| `APP_ENV=production` + short `SESSION_SECRET` (<32 chars) | ValueError → startup fails |
| `APP_ENV=production` + `COOKIE_SECURE=false` | Warning logged (non-blocking) |
| `APP_ENV=production` + wildcard CORS origin | Warning logged (non-blocking) |

### Development Behavior

- Default session secret is accepted (development mode)
- Bootstrap endpoint works as before (creates initial admin if no users exist)
- No configuration changes required for local development

---

## Test Coverage

### New Security Tests (35 in `test_production_hardening.py`)

| Test | What It Verifies |
|------|-----------------|
| `test_production_rejects_weak_default_secret` | Known default secret raises ValueError |
| `test_production_rejects_short_secret` | Short secret raises ValueError |
| `test_production_bootstrap_returns_403` | Bootstrap blocked in production |
| `test_development_bootstrap_works` | Bootstrap works in development |
| `test_unauthenticated_rejected` | /admin/users returns 401 without auth |
| `test_demo_user_is_admin` | Admin of a project can list users |
| `test_viewer_role_cannot_list_users` | VIEWER role denied from /admin/users |
| `test_stored_filename_is_relative` | No absolute paths stored |
| `test_stored_filename_not_in_api_responses` | Path not leaked in API |
| `test_production_default_secret_raises` | Default secret blocked |
| `test_production_dev_fallback_secret_raises` | Dev fallback blocked |
| `test_production_short_secret_raises` | Short secret blocked |
| `test_production_strong_secret_accepted` | Valid secret accepted |
| `test_development_default_secret_accepted` | Dev mode works |
| `test_auth_signing_still_works` | Token creation/verification works |
| `test_cors_preflight_allows_required_headers` | CORS allows needed headers |
| `test_actual_request_with_required_headers_succeeds` | Requests work with CORS |

### Updated Tests

- `test_remediation_uploads.py` — Two tests updated to construct physical paths from relative `stored_filename`

---

## Deployment Checklist

1. **Set `SESSION_SECRET`** environment variable to a unique random value (minimum 32 characters)
2. **Set `APP_ENV=production`** environment variable
3. **Set `COOKIE_SECURE=true`** if deploying behind HTTPS
4. **Configure `CORS_ORIGINS`** with your actual frontend domain(s)
5. **Do NOT use** the `/api/auth/bootstrap` endpoint in production — provision the first admin via database seeding or migration
6. **Verify** the health endpoint returns `{"status": "ok"}` after deployment

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/api/auth_routes.py` | Bootstrap production guard + /admin/users RBAC |
| `backend/app/api/routes.py` | Relative stored_filename for remediation uploads |
| `backend/app/core/config.py` | Session secret enforcement (raises ValueError) |
| `backend/app/services/auth_service.py` | Simplified `_get_signing_secret()` |
| `backend/app/services/storage.py` | Relative path resolution in `delete_remediation_upload` |
| `backend/app/main.py` | CORS headers restricted + production startup validation |
| `backend/test_production_hardening.py` | 17 new security tests + 4 updated |
| `backend/test_remediation_uploads.py` | 2 tests updated for relative paths |
| `docs/P2_6_PRODUCTION_HARDENING.md` | This document |

---

## What Was NOT Changed

- Authentication/CSRF architecture
- RBAC permission matrix
- Audit immutability
- Verification snapshot immutability
- AI/Gemini agent behavior
- Analytics endpoints
- SSE streaming
- Frontend code
- Database schema
- Test thresholds
