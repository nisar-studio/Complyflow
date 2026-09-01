"""
ComplyFlow — FastAPI Routes (Aggregator)

This module includes all domain route modules and preserves backward-compatible
exports (router, settings, _document_service, _get_storage, _emit_factory)
for main.py and existing test infrastructure.

Route modules:
  project_routes     — Project CRUD, details, results
  document_routes    — Document upload, list, view, bulk delete
  analysis_routes    — AI analysis, verification, runs, delta, reports
  override_routes    — Auditor overrides, notes, bulk operations
  remediation_routes — Task management, uploads, bulk tasks
  event_routes       — Events, SSE streaming
  notification_routes — In-app notifications
  audit_routes       — Audit event timeline
  analytics_routes   — Project and portfolio analytics
  framework_routes   — Compliance framework management
"""
from __future__ import annotations

from fastapi import APIRouter

# ── Backward-compatible re-exports ─────────────────────────────────
# These are accessed by main.py and test files via:
#   import app.api.routes as routes_module
#   routes_module.settings.upload_dir
#   routes_module._document_service
from app.api._shared import settings, _get_storage, _emit_factory  # noqa: F401
from app.api.document_routes import _document_service  # noqa: F401

# ── Main router ────────────────────────────────────────────────────
router = APIRouter(prefix="/api")

# ── Include all domain routers ─────────────────────────────────────
from app.api.project_routes import router as _project_router
from app.api.document_routes import router as _document_router
from app.api.analysis_routes import router as _analysis_router
from app.api.override_routes import router as _override_router
from app.api.remediation_routes import router as _remediation_router
from app.api.event_routes import router as _event_router
from app.api.notification_routes import router as _notification_router
from app.api.audit_routes import router as _audit_router
from app.api.analytics_routes import router as _analytics_router
from app.api.framework_routes import router as _framework_router

router.include_router(_project_router)
router.include_router(_document_router)
router.include_router(_analysis_router)
router.include_router(_override_router)
router.include_router(_remediation_router)
router.include_router(_event_router)
router.include_router(_notification_router)
router.include_router(_audit_router)
router.include_router(_analytics_router)
router.include_router(_framework_router)
