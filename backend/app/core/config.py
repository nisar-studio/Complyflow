"""
ComplyFlow — Centralized Production & Security Configuration

Supports:
  - Local-first development (zero-config SQLite + local files)
  - Production security validation (secrets, cookies, CORS, upload limits)
  - Gemini API configuration (keys never committed to source)
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, List, Optional


from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application Environment ──────────────────────────────
    app_env: str = Field(default="development", description="Environment: development | production | testing")
    log_level: str = Field(default="INFO", description="Logging level: DEBUG | INFO | WARNING | ERROR")

    # ── AI Layer (Gemini + Google ADK) ───────────────────────
    gemini_api_key: str = Field(default="", description="Gemini API Key (https://aistudio.google.com/apikey)")
    # Model: gemini-3.5-flash or gemini-3.5-pro per hackathon guidelines
    gemini_model: str = Field(default="gemini-3.5-flash", description="Gemini model name")

    # ── Database (SQLite Primary, Local-First) ───────────────
    database_path: str = Field(default="complyflow.db", description="Local SQLite database file path")
    database_url: Optional[str] = Field(default=None, description="Optional DB URL (defaults to sqlite database_path)")

    # ── Storage & Uploads ────────────────────────────────────
    upload_dir: str = Field(default="uploads", description="Local directory for evidence & report files")
    max_upload_size_bytes: int = Field(default=50 * 1024 * 1024, description="Maximum allowed file upload size (50MB)")

    # ── Server & Networking ──────────────────────────────────
    backend_host: str = Field(default="0.0.0.0", description="Bind host")
    backend_port: int = Field(default=8000, description="Bind port")
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Allowed CORS origins list (no wildcards allowed with credentials)",
    )

    # ── Security, Sessions & Cookies ─────────────────────────
    cookie_secure: bool = Field(default=False, description="Set True in HTTPS production environments")
    cookie_samesite: str = Field(default="lax", description="SameSite cookie policy: lax | strict")
    cookie_httponly: bool = Field(default=True, description="HttpOnly cookie protection")
    session_secret: str = Field(
        default="complyflow-session-secret-key-32-bytes!",
        description="Secret key for signing session tokens (must be overridden in production)",
    )
    csrf_secret: str = Field(
        default="complyflow-csrf-secret-key-32-bytes!",
        description="Secret key for CSRF token generation",
    )
    session_lifetime_seconds: int = Field(default=7 * 24 * 3600, description="Session TTL (default 7 days)")

    # ── Optional Legacy Cloud Storage Stub ───────────────────
    use_firestore: bool = Field(default=False, description="Optional cloud storage flag")
    google_cloud_project: str = Field(default="", description="GCP project ID")
    google_application_credentials: str = Field(default="", description="GCP credentials path")

    # ── Frontend Base URL ────────────────────────────────────
    vite_api_base_url: str = Field(default="http://localhost:8000", description="Frontend API Base URL")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate_production_settings(self) -> List[str]:
        """
        Validate critical security parameters when running in production mode.
        Returns a list of warning or error messages.
        Raises ValueError if production requirements are critically violated.
        """
        errors = []
        if self.is_production():
            # Check default insecure secrets
            if self.session_secret == "complyflow-session-secret-key-32-bytes!" or len(self.session_secret) < 32:
                errors.append("Production requires a strong, unique SESSION_SECRET (minimum 32 characters).")

            # Check CORS wildcard
            if any(origin == "*" for origin in self.cors_origins):
                errors.append("Wildcard '*' in CORS_ORIGINS is prohibited in production when credentials are enabled.")

            # Check cookie security in production
            if not self.cookie_secure:
                errors.append("COOKIE_SECURE must be True in production deployments behind HTTPS.")

        return errors


@lru_cache()
def get_settings() -> Settings:
    return Settings()
