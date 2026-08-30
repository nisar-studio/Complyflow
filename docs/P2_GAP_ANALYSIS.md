# ComplyFlow — P2 #1 Gap Analysis & Production Readiness Review

> **Audit Date**: 2026-08-30  
> **Review Scope**: Complete Backend, Frontend, RBAC, Data Isolation, Auditability, and AI Safety  
> **Architecture Principle**: Local-First, Self-Hosted, Zero Cloud Dependencies

---

## 1. Executive Summary

A comprehensive architectural and operational inspection of ComplyFlow was performed across all 10 target categories. The platform's core architecture (FastAPI, SQLite in WAL mode, Google ADK + Gemini API, HttpOnly Cookie Auth, Double Submit CSRF, 4-tier RBAC, ReportLab PDF generation, and append-only audit logs) is sound and functioning with 232/232 passing backend tests.

This review identified high-value non-blocking enterprise gaps in **Audit Event Coverage on Access Mutations**, **Project Deletion Lifecycle Endpoint**, **Uniform Filesystem Sanitization**, and **Frontend Destructive Action UX**.

---

## 2. Comprehensive Findings & Gap Log

### Finding GAP-P2-01: Missing Audit Events on Project Member Management
- **Severity**: **P1 (Audit Integrity & Governance)**
- **Location**: `backend/app/api/auth_routes.py` (lines 277–380)
- **Problem**: When a project Admin adds a member (`add_member`), updates their role (`update_member_role`), or removes a member (`remove_member`), the membership table is modified, but no immutable audit event is emitted or recorded in `audit_events`.
- **Why It Matters**: Compliance auditors require a complete, immutable historical trail of who had access to review, override, or upload evidence on a project at any given point in time.
- **Recommended Fix**: Call `await record_audit_event(...)` on `add_member` (`MEMBER_ADDED`), `update_member_role` (`MEMBER_ROLE_UPDATED`), and `remove_member` (`MEMBER_REMOVED`).
- **Status**: **To Be Implemented in Phase 3**.

---

### Finding GAP-P2-02: Missing Project Deletion Endpoint
- **Severity**: **P2 (RBAC Completeness & Project Lifecycle)**
- **Location**: `backend/app/api/routes.py`
- **Problem**: `Role.ADMIN` has `"project:delete"` defined in `ROLE_PERMISSIONS`, but no `DELETE /api/projects/{project_id}` route existed in `routes.py`.
- **Why It Matters**: Project administrators could not decommission or delete compliance projects through the standard API, leaving orphaned data during workspace cleanups.
- **Recommended Fix**: Add `DELETE /api/projects/{project_id}` protected by `require_permission("project:delete")`, recording a `PROJECT_DELETED` audit event and safely cleaning up project files.
- **Status**: **To Be Implemented in Phase 3**.

---

### Finding GAP-P2-03: Uniform Filename Sanitization in DocumentService
- **Severity**: **P2 (File Storage & Defense-in-Depth)**
- **Location**: `backend/app/services/document_service.py` (line 33)
- **Problem**: `DocumentService.save_upload` used basic `Path(filename).name` while remediation upload routes used `file_utils.sanitize_filename`.
- **Why It Matters**: Defense-in-depth requires that all file writes apply the identical unicode-normalizing, traversal-stripping, and null-byte-clearing algorithm.
- **Recommended Fix**: Import and call `sanitize_filename` directly in `DocumentService.save_upload`.
- **Status**: **To Be Implemented in Phase 3**.

---

### Finding GAP-P2-04: Project Deletion & Deletion Confirmation UX in Frontend
- **Severity**: **P2 (Frontend UX Polish)**
- **Location**: `frontend/src/api/client.js` & `frontend/src/pages/Dashboard.jsx`
- **Problem**: The dashboard did not provide a delete project button or confirmation dialog for project Admins.
- **Why It Matters**: Completes the project lifecycle in the user interface with safety confirmation.
- **Recommended Fix**: Add `deleteProject` in `client.js` and delete button with confirmation modal in `Dashboard.jsx`.
- **Status**: **To Be Implemented in Phase 3**.

---

### Finding GAP-P2-05: Strict Data Isolation Verification
- **Severity**: **P3 (Verified / Defense-in-Depth)**
- **Location**: `backend/app/api/routes.py` & `backend/app/services/storage.py`
- **Problem**: Cross-project query isolation check across documents, tasks, runs, overrides, and audit events.
- **Evaluation**: All project endpoints use `get_project_member_context` or `require_permission`, which verify that the requesting user has valid membership in `project_id`.
- **Mitigation Status**: **Adequately Mitigated & Verified**.

---

## 3. Prioritized Implementation Plan

1. **Member Audit Logging**: Add `record_audit_event` to all member management operations in `auth_routes.py`.
2. **Project Deletion Endpoint**: Implement `DELETE /api/projects/{project_id}` with RBAC and audit trail in `routes.py` and `storage.py`.
3. **Document Service Sanitization**: Use `sanitize_filename` in `DocumentService.save_upload`.
4. **Frontend Client & UI**: Add `deleteProject` API call and UI action with confirmation dialog.
5. **Automated Test Suite**: Write comprehensive tests in `backend/test_p2_gap_closure.py` covering member audit events, project deletion RBAC, and file sanitization.
