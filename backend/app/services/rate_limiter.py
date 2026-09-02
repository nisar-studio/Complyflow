"""
ComplyFlow — In-Memory Sliding-Window Login Rate Limiter

Tracks failed login attempts per client IP using a sliding time window.
Designed for single-process deployment (matches Docker/uvicorn single-worker model).

Usage:
    from app.services.rate_limiter import get_login_rate_limiter
    limiter = get_login_rate_limiter()
    if not await limiter.is_allowed(client_ip):
        # return 429
    # on successful login:
    limiter.record_success(client_ip)
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Dict, Optional


class LoginRateLimiter:
    """
    In-memory sliding-window rate limiter for login attempts.

    Thread-safe under asyncio's single-threaded event loop.
    Not safe under multi-process deployment (each process has its own state).
    Acceptable for the current single-worker architecture.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 900,
    ):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        # ip → deque of attempt timestamps (float, time.time())
        self._attempts: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        """
        Check whether a login attempt from *key* (typically client IP) is allowed.

        Returns True if under the limit, False if rate-limited.
        Does NOT record the attempt — call record_failure() separately.
        """
        now = time.time()
        cutoff = now - self._window_seconds

        async with self._lock:
            if key not in self._attempts:
                return True

            dq = self._attempts[key]
            # Prune expired entries
            while dq and dq[0] < cutoff:
                dq.popleft()

            if not dq:
                # All entries expired — key is clean
                return True

            return len(dq) < self._max_attempts

    async def record_failure(self, key: str) -> None:
        """Record a failed login attempt for the given key."""
        now = time.time()
        async with self._lock:
            if key not in self._attempts:
                self._attempts[key] = deque()
            self._attempts[key].append(now)

    def record_success(self, key: str) -> None:
        """
        Clear the failed-attempt history for *key* after a successful login.

        This is synchronous because it only removes state — no locking needed
        for correctness under asyncio (single-threaded), but we use the lock
        for consistency with the other methods.
        """
        self._attempts.pop(key, None)

    async def get_attempt_count(self, key: str) -> int:
        """Return the current number of failed attempts within the window."""
        now = time.time()
        cutoff = now - self._window_seconds
        async with self._lock:
            if key not in self._attempts:
                return 0
            dq = self._attempts[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            return len(dq)

    def reset(self) -> None:
        """Clear all tracked attempts. Intended for test isolation only."""
        self._attempts.clear()

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def window_seconds(self) -> int:
        return self._window_seconds


# ── Singleton ─────────────────────────────────────────────────

_login_rate_limiter: Optional[LoginRateLimiter] = None


def get_login_rate_limiter(
    max_attempts: Optional[int] = None,
    window_seconds: Optional[int] = None,
) -> LoginRateLimiter:
    """
    Get or create the global login rate limiter singleton.

    Parameters are only used on first initialization.
    Subsequent calls return the existing instance regardless of arguments.
    """
    global _login_rate_limiter
    if _login_rate_limiter is None:
        from app.core.config import get_settings
        settings = get_settings()
        _login_rate_limiter = LoginRateLimiter(
            max_attempts=max_attempts if max_attempts is not None else settings.login_rate_limit_max_attempts,
            window_seconds=window_seconds if window_seconds is not None else settings.login_rate_limit_window_seconds,
        )
    return _login_rate_limiter


def reset_login_rate_limiter() -> None:
    """Reset the global singleton. Intended for test teardown only."""
    global _login_rate_limiter
    if _login_rate_limiter is not None:
        _login_rate_limiter.reset()
    _login_rate_limiter = None
