"""
ComplyFlow — Structured Production Logging & Secret Redaction

Provides:
  - Custom RedactingFormatter that automatically strips sensitive credentials
  - Redaction of Gemini API keys, passwords, hashes, session tokens, CSRF tokens, cookies, and local filesystem paths
  - Safe production logging without information disclosure
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Optional


# Regex patterns for sensitive data
SECRET_PATTERNS = [
    # Gemini / Google API Keys: AIzaSy...
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_GEMINI_KEY]"),
    # Password hashes: pbkdf2_sha256$100000$...
    (re.compile(r"pbkdf2_sha256\$\d+\$[a-f0-9]+\$[a-f0-9]+", re.IGNORECASE), "[REDACTED_PASSWORD_HASH]"),
    # Bearer tokens in Authorization headers: Bearer <token>
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Password fields in JSON / query: "password": "..."
    (re.compile(r'("password"\s*:\s*")[^"]+(")', re.IGNORECASE), r"\1[REDACTED_PASSWORD]\2"),
    # Session cookies: complyflow_session=...
    (re.compile(r"complyflow_session=[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE), "complyflow_session=[REDACTED_SESSION]"),
    # CSRF tokens: complyflow_csrf=... or X-CSRF-Token: ...
    (re.compile(r"complyflow_csrf=[a-f0-9]{16,}", re.IGNORECASE), "complyflow_csrf=[REDACTED_CSRF]"),
    (re.compile(r"(X-CSRF-Token\s*:\s*)[a-f0-9]{16,}", re.IGNORECASE), r"\1[REDACTED_CSRF]"),
    # Windows absolute local file paths (e.g. C:\Users\... or C:/Users/...)
    (re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|antigravity|scratch)[\\/][^\s\"'<>]+", re.IGNORECASE), "[LOCAL_FILE_PATH]"),
    # Unix absolute local paths (/home/... or /Users/...)
    (re.compile(r"/(?:home|Users|root)/[^\s\"'<>]+", re.IGNORECASE), "[LOCAL_FILE_PATH]"),
]


def redact_secrets(message: str) -> str:
    """Sanitize any sensitive credentials, tokens, hashes, or absolute paths in a log message."""
    if not isinstance(message, str):
        message = str(message)
    for pattern, replacement in SECRET_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class RedactingFormatter(logging.Formatter):
    """Logging formatter that automatically scrubs sensitive credentials from all output."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_secrets(original)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with the RedactingFormatter and appropriate log level."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Attach stdout stream handler with RedactingFormatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = RedactingFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Also apply to uvicorn & fastapi loggers
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        l = logging.getLogger(logger_name)
        l.handlers = [handler]
        l.propagate = False
