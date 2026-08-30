"""
ComplyFlow — FastAPI Application Entry Point

Production-Hardened Local-First Architecture:
  - SQLite Database (Primary)
  - Google ADK + Gemini API (Reasoning Engine)
  - HttpOnly Cookie Authentication & RBAC
  - Automated Secret Redaction & Production Security Headers
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api.auth_routes import auth_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.storage import get_storage
from app.services.auth_service import verify_csrf

settings = get_settings()

# Initialize structured redacting logging
setup_logging(settings.log_level)
logger = logging.getLogger("complyflow.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    # 1. Validate production configuration
    if settings.is_production():
        validation_errors = settings.validate_production_settings()
        for err in validation_errors:
            logger.warning(f"Production Security Warning: {err}")

    # 2. Verify local storage initialization
    try:
        storage = get_storage()
        await storage.list_projects()
        logger.info("ComplyFlow storage initialized successfully (SQLite local-first).")
    except Exception as e:
        logger.error(f"Storage initialization warning: {e}")

    yield
    logger.info("ComplyFlow server shutting down.")


app = FastAPI(
    title="ComplyFlow API",
    description="Autonomous AI Compliance Agent — powered by Google ADK + Gemini (Local-First)",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — Strict allowed origins (no wildcards with credentials) ──────────
_cors_origins = [o.strip() for o in settings.cors_origins if o.strip() and o != "*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# ── HTTP Security Headers Middleware ─────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add defensive security headers to all responses."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


# ── CSRF Protection Middleware ───────────────────────────────────
@app.middleware("http")
async def csrf_protect_middleware(request: Request, call_next):
    """CSRF protection middleware for cookie-authenticated mutating requests."""
    try:
        verify_csrf(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "FORBIDDEN",
                    "message": exc.detail,
                    "recoverable": False,
                }
            },
        )
    return await call_next(request)


# ── Standardized Exception Handlers ──────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Standardized error responses for HTTPExceptions."""
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "UNPROCESSABLE_ENTITY",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": exc.detail,
                "recoverable": exc.status_code < 500,
            }
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Fallback handler preventing stack traces or internal secrets from leaking."""
    logger.error(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred while processing your request.",
                "recoverable": False,
            }
        },
    )


# ── Routers ──────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(router)


# ── Health & Readiness Probes ────────────────────────────────────

@app.get("/health")
async def health():
    """
    Health probe reporting application and database connectivity without exposing secrets.
    """
    model = os.environ.get("GEMINI_MODEL", settings.gemini_model)
    has_api_key = bool(os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key)
    
    db_connected = False
    try:
        storage = get_storage()
        projects = await storage.list_projects()
        db_connected = isinstance(projects, list)
    except Exception:
        db_connected = False

    return {
        "status": "ok" if db_connected else "degraded",
        "service": "complyflow-api",
        "environment": settings.app_env,
        "model": model,
        "database": "sqlite (primary)",
        "database_connected": db_connected,
        "gemini_configured": has_api_key,
    }


@app.get("/ready")
async def readiness():
    """
    Kubernetes / Docker readiness probe.
    Returns 200 when the service is fully ready to accept compliance requests.
    """
    try:
        storage = get_storage()
        await storage.list_projects()
        return {
            "status": "ready",
            "database_ready": True,
            "storage_ready": True,
        }
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "database_ready": False},
        )
