"""
test_rate_limiting.py — Login Rate Limiting Tests (Epic A)

Tests:
  1. Requests below the limit are allowed
  2. The request exceeding the limit receives 429
  3. Attempts outside the sliding window expire
  4. Successful login clears the failed-attempt counter
  5. Different client IPs have independent limits
  6. Legitimate login behavior remains unchanged
  7. Rate limiter unit tests (sliding window, reset, etc.)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import hash_password, Role
from app.services.rate_limiter import (
    LoginRateLimiter,
    get_login_rate_limiter,
    reset_login_rate_limiter,
)
import app.services.rate_limiter as rate_limiter_module


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rl_ctx(tmp_path_factory):
    """Isolated database and TestClient for rate-limiting tests."""
    tmp = tmp_path_factory.mktemp("rate_limiting")
    db_path = str(tmp / "rl.db")
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

    # Reset the rate limiter singleton so tests start clean
    reset_login_rate_limiter()

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    # Seed test users
    _run(test_storage.create_user({
        "user_id": "rl_admin",
        "email": "rl_admin@test.com",
        "name": "RL Admin",
        "password_hash": hash_password("AdminPass123!"),
        "is_active": True,
    }))
    _run(test_storage.create_user({
        "user_id": "rl_inactive",
        "email": "rl_inactive@test.com",
        "name": "RL Inactive",
        "password_hash": hash_password("InactivePass123!"),
        "is_active": False,
    }))

    yield {
        "client": client,
        "storage": test_storage,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir
    reset_login_rate_limiter()


# ── Unit Tests ────────────────────────────────────────────────


class TestLoginRateLimiterUnit:
    """Unit tests for the LoginRateLimiter class."""

    def test_allows_attempts_under_limit(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        assert _run(limiter.is_allowed("192.168.1.1")) is True
        _run(limiter.record_failure("192.168.1.1"))
        assert _run(limiter.is_allowed("192.168.1.1")) is True
        _run(limiter.record_failure("192.168.1.1"))
        assert _run(limiter.is_allowed("192.168.1.1")) is True

    def test_blocks_at_limit(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
        _run(limiter.record_failure("10.0.0.1"))
        _run(limiter.record_failure("10.0.0.1"))
        assert _run(limiter.is_allowed("10.0.0.1")) is False

    def test_clears_on_success(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
        _run(limiter.record_failure("10.0.0.2"))
        _run(limiter.record_failure("10.0.0.2"))
        assert _run(limiter.is_allowed("10.0.0.2")) is False
        limiter.record_success("10.0.0.2")
        assert _run(limiter.is_allowed("10.0.0.2")) is True

    def test_different_ips_independent(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
        _run(limiter.record_failure("10.0.0.3"))
        assert _run(limiter.is_allowed("10.0.0.3")) is False
        assert _run(limiter.is_allowed("10.0.0.4")) is True

    def test_window_expiry(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=1)
        _run(limiter.record_failure("10.0.0.5"))
        assert _run(limiter.is_allowed("10.0.0.5")) is False
        # Wait for window to expire
        time.sleep(1.1)
        assert _run(limiter.is_allowed("10.0.0.5")) is True

    def test_reset_clears_all(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
        _run(limiter.record_failure("10.0.0.6"))
        _run(limiter.record_failure("10.0.0.7"))
        limiter.reset()
        assert _run(limiter.is_allowed("10.0.0.6")) is True
        assert _run(limiter.is_allowed("10.0.0.7")) is True

    def test_attempt_count(self):
        limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)
        assert _run(limiter.get_attempt_count("10.0.0.8")) == 0
        _run(limiter.record_failure("10.0.0.8"))
        assert _run(limiter.get_attempt_count("10.0.0.8")) == 1
        _run(limiter.record_failure("10.0.0.8"))
        assert _run(limiter.get_attempt_count("10.0.0.8")) == 2


# ── Integration Tests ─────────────────────────────────────────


class TestLoginRateLimitingIntegration:
    """Integration tests using the full FastAPI TestClient."""

    def _login(self, client, email="rl_admin@test.com", password="AdminPass123!"):
        """Helper: attempt login and return response."""
        return client.post("/api/auth/login", json={
            "email": email,
            "password": password,
        })

    def test_successful_login_works(self, rl_ctx):
        """Legitimate login succeeds normally."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()
        res = self._login(client)
        assert res.status_code == 200
        assert "user" in res.json()

    def test_failed_login_returns_401(self, rl_ctx):
        """Wrong password returns 401 without revealing account existence."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()
        res = self._login(client, password="WrongPassword")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "UNAUTHORIZED"

    def test_nonexistent_email_returns_401(self, rl_ctx):
        """Non-existent email returns same 401 as wrong password."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()
        res = self._login(client, email="nonexistent@test.com")
        assert res.status_code == 401

    def test_rate_limit_enforced(self, rl_ctx):
        """After max failed attempts, 429 is returned."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()
        limiter = get_login_rate_limiter()

        # Exhaust the limit (default 5 attempts)
        for _ in range(5):
            res = self._login(client, password="WrongPassword")
            assert res.status_code == 401

        # Next attempt should be rate-limited
        res = self._login(client, password="WrongPassword")
        assert res.status_code == 429
        assert "Too many" in res.json()["error"]["message"]

    def test_successful_login_clears_counter(self, rl_ctx):
        """After successful login, the rate-limit counter resets."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()

        # Make 4 failed attempts (below default limit of 5)
        for _ in range(4):
            self._login(client, password="WrongPassword")

        # Successful login clears the counter
        res = self._login(client)
        assert res.status_code == 200

        # Should be able to fail again without hitting rate limit
        for _ in range(4):
            res = self._login(client, password="WrongPassword")
            assert res.status_code == 401

    def test_different_ips_independent_limits(self, rl_ctx):
        """Different client IPs have independent rate limits."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()

        # Simulate requests from different IPs by mocking client.host
        # We use the rate limiter directly since TestClient doesn't easily
        # allow IP spoofing. The unit tests above cover IP independence.
        limiter = get_login_rate_limiter()
        _run(limiter.record_failure("fake-ip-1"))
        _run(limiter.record_failure("fake-ip-1"))
        _run(limiter.record_failure("fake-ip-1"))

        # Different IP should be unaffected
        assert _run(limiter.is_allowed("fake-ip-2")) is True

    def test_inactive_user_returns_403(self, rl_ctx):
        """Deactivated accounts are blocked with 403, not rate-limited."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()
        res = self._login(client, email="rl_inactive@test.com", password="InactivePass123!")
        assert res.status_code == 403
        assert "deactivated" in res.json()["error"]["message"].lower()

    def test_429_response_matches_error_conventions(self, rl_ctx):
        """429 response uses the application's error-response format."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()

        # Exhaust limit
        for _ in range(5):
            self._login(client, password="WrongPassword")

        res = self._login(client, password="WrongPassword")
        assert res.status_code == 429
        body = res.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "recoverable" in body["error"]

    def test_rate_limit_does_not_affect_other_endpoints(self, rl_ctx):
        """Rate limiting only applies to POST /api/auth/login."""
        client = rl_ctx["client"]
        reset_login_rate_limiter()

        # Exhaust login rate limit
        for _ in range(5):
            self._login(client, password="WrongPassword")

        # Other endpoints should still work
        res = client.get("/health")
        assert res.status_code == 200

        res = client.get("/ready")
        assert res.status_code == 200
