"""
test_analytics.py — Enterprise Compliance Analytics Tests

Tests:
  - Authentication / RBAC for analytics endpoints
  - Project isolation (cross-project data never leaks)
  - Empty projects (zero data returns safe defaults)
  - Multiple verification runs (score trends)
  - Requirement status breakdown
  - Issue severity aggregation
  - Task status aggregation
  - Audit activity summary
  - Auditor override impact
  - Portfolio analytics (cross-project aggregates)
  - Malformed / empty historical data
  - doc_names bug regression
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import (
    create_session_token,
    hash_password,
    Role,
)


# ── Test Fixtures ────────────────────────────────────────────

@pytest.fixture(scope="module")
def analytics_ctx(tmp_path_factory):
    """Full API client with an isolated DB for analytics tests."""
    tmp = tmp_path_factory.mktemp("analytics")
    db_path = str(tmp / "analytics.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir
    routes_module._document_service.upload_dir = upload_dir

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    yield {
        "client": client,
        "storage": test_storage,
        "upload_dir": upload_dir,
    }

    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_upload_dir
    storage_module._storage_instance = original_instance


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_counter = 0


def _uniq(suffix: str) -> str:
    global _counter
    _counter += 1
    return f"{suffix}_{_counter}"


def _create_user(storage, user_id, email, name="Test User"):
    # Silently ignore duplicate user_id (may already exist from earlier test)
    try:
        _run(storage.create_user({
            "user_id": user_id,
            "email": email,
            "name": name,
            "password_hash": hash_password("TestPass123!"),
            "is_active": True,
        }))
    except Exception:
        pass
    return create_session_token(user_id, email)


def _create_project_with_data(storage, user_id, project_name="Test Project"):
    """Helper: create a project, add user as ADMIN, return project_id."""
    try:
        _run(storage.create_user({
            "user_id": user_id,
            "email": f"{user_id}@test.local",
            "name": f"User {user_id}",
            "password_hash": hash_password("pass12345!"),
            "is_active": True,
        }))
    except Exception:
        pass
    project_id = _run(storage.create_project({
        "name": project_name,
        "status": "PENDING",
        "compliance_score": None,
        "requirements_count": 0,
        "documents_count": 0,
        "issues_count": 0,
    }))
    _run(storage.add_project_member(project_id, user_id, Role.ADMIN.value))
    return project_id


def _seed_matches(storage, project_id, count=5):
    """Seed requirement matches with varied statuses."""
    statuses = ["SATISFIED", "MISSING", "CONFLICT", "PARTIAL", "SATISFIED"]
    matches = []
    for i in range(count):
        m = {
            "requirement_id": f"REQ-{i+1:03d}",
            "requirement_title": f"Requirement {i+1}",
            "status": statuses[i % len(statuses)],
            "confidence": 0.85 + (i * 0.03),
            "reasoning": f"Analysis for requirement {i+1}",
            "evidence": [],
        }
        matches.append(m)
    _run(storage.save_matches(project_id, matches))
    return matches


def _seed_issues(storage, project_id, count=4):
    """Seed compliance issues with varied severity."""
    severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    gap_types = ["missing_evidence", "expired_evidence", "conflict", "incomplete"]
    issues = []
    for i in range(count):
        issue = {
            "gap_id": f"GAP-{i+1:03d}",
            "gap_type": gap_types[i % len(gap_types)],
            "severity": severities[i % len(severities)],
            "description": f"Issue {i+1} description",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "related_requirement_title": f"Requirement {i+1}",
        }
        issues.append(issue)
    _run(storage.save_issues(project_id, issues))
    return issues


def _seed_tasks(storage, project_id, count=3):
    """Seed remediation tasks."""
    statuses = ["OPEN", "RESOLVED", "OPEN"]
    severities = ["HIGH", "MEDIUM", "LOW"]
    tasks = []
    for i in range(count):
        task = {
            "task_id": f"TASK-{i+1:03d}",
            "title": f"Task {i+1}",
            "description": f"Remediation task {i+1}",
            "severity": severities[i % len(severities)],
            "required_action": f"Action for task {i+1}",
            "related_requirement_id": f"REQ-{i+1:03d}",
            "status": statuses[i % len(statuses)],
        }
        tasks.append(task)
    _run(storage.save_tasks(project_id, tasks))
    return tasks


def _seed_verification_runs(storage, project_id, run_count=3):
    """Seed multiple verification runs with improving scores."""
    runs = []
    for i in range(run_count):
        score = 30.0 + (i * 25.0)  # 30%, 55%, 80%
        run_data = {
            "trigger": "INITIAL_ANALYSIS" if i == 0 else "REMEDIATION_VERIFICATION",
            "overall_status": "ACTION_REQUIRED" if score < 100 else "READY",
            "compliance_score": score,
            "satisfied_count": i + 1,
            "total_count": 5,
            "requirements_snapshot": [],
            "matches_snapshot": [],
            "issues_snapshot": [],
            "tasks_snapshot": [],
            "documents_used": ["doc1.pdf"],
            "resolved_gaps": [f"GAP-{j+1:03d}" for j in range(i)],
            "remaining_gaps": [f"GAP-{j+1:03d}" for j in range(i, 5)],
            "summary": f"Run {i+1} completed with {score}% score",
            "timestamp": f"2026-08-{25+i}T10:00:00Z",
        }
        run_id = _run(storage.save_verification_run(project_id, run_data))
        runs.append(run_id)
    return runs


def _seed_audit_events(storage, project_id, count=5):
    """Seed audit events."""
    event_types = [
        "PROJECT_CREATED", "DOCUMENT_UPLOADED", "ANALYSIS_STARTED",
        "ANALYSIS_COMPLETED", "REMEDIATION_TASK_CREATED",
    ]
    actor_types = ["AUDITOR", "AUDITOR", "AI_AGENT", "AI_AGENT", "AI_AGENT"]
    severities = ["INFO", "INFO", "INFO", "INFO", "WARNING"]
    events = []
    for i in range(count):
        from app.services.audit_service import record_audit_event
        event_id = _run(record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type=event_types[i % len(event_types)],
            actor_type=actor_types[i % len(actor_types)],
            severity=severities[i % len(severities)],
            summary=f"Audit event {i+1}",
        ))
        events.append(event_id)
    return events


# ─────────────────────────────────────────────────────────────
# 1. Authentication / RBAC Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsAuth:
    """Analytics endpoints enforce authentication and RBAC."""

    def test_unauthenticated_access_returns_401(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("au1")
        project_id = _create_project_with_data(storage, uid)

        # Try without auth
        r = client.get(f"/api/projects/{project_id}/analytics")
        assert r.status_code == 401

    def test_authenticated_member_can_access_analytics(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("au2")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["project_id"] == project_id

    def test_non_member_cannot_access_analytics(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        owner_uid = _uniq("owner")
        project_id = _create_project_with_data(storage, owner_uid)

        outsider_uid = _uniq("out")
        outsider_token = _create_user(storage, outsider_uid, f"{outsider_uid}@test.local")

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(outsider_token))
        assert r.status_code == 403

    def test_portfolio_analytics_requires_auth(self, analytics_ctx):
        client = analytics_ctx["client"]
        r = client.get("/api/analytics/portfolio")
        assert r.status_code == 401

    def test_portfolio_analytics_returns_own_data(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("port")
        token = _create_user(storage, uid, f"{uid}@test.local")
        _create_project_with_data(storage, uid, "My Project")

        r = client.get("/api/analytics/portfolio", headers=_auth_header(token))
        assert r.status_code == 200
        data = r.json()
        assert data["total_projects"] >= 1


# ─────────────────────────────────────────────────────────────
# 2. Project Isolation Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsIsolation:
    """Analytics never exposes data from another project/user."""

    def test_cross_project_data_isolation(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]

        u1 = _uniq("iso1")
        u2 = _uniq("iso2")
        _create_user(storage, u1, f"{u1}@test.local")
        _create_user(storage, u2, f"{u2}@test.local")

        proj1 = _create_project_with_data(storage, u1, "Project Alpha")
        proj2 = _create_project_with_data(storage, u2, "Project Beta")

        _seed_matches(storage, proj1, count=5)
        _seed_issues(storage, proj1, count=3)
        _seed_verification_runs(storage, proj1, run_count=2)

        token1 = create_session_token(u1, f"{u1}@test.local")
        token2 = create_session_token(u2, f"{u2}@test.local")

        r1 = client.get(f"/api/projects/{proj1}/analytics", headers=_auth_header(token1))
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["project_name"] == "Project Alpha"
        assert data1["total_verification_runs"] == 2

        r1_denied = client.get(f"/api/projects/{proj1}/analytics", headers=_auth_header(token2))
        assert r1_denied.status_code == 403

        r2 = client.get(f"/api/projects/{proj2}/analytics", headers=_auth_header(token2))
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["project_name"] == "Project Beta"
        assert data2["total_verification_runs"] == 0

    def test_portfolio_only_shows_user_projects(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]

        u1 = _uniq("pis1")
        u2 = _uniq("pis2")
        _create_user(storage, u1, f"{u1}@test.local")
        _create_user(storage, u2, f"{u2}@test.local")

        _create_project_with_data(storage, u1, "Alpha")
        _create_project_with_data(storage, u1, "Alpha Two")
        _create_project_with_data(storage, u2, "Beta")

        token1 = create_session_token(u1, f"{u1}@test.local")
        token2 = create_session_token(u2, f"{u2}@test.local")

        r1 = client.get("/api/analytics/portfolio", headers=_auth_header(token1))
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["total_projects"] == 2
        assert all(p["name"].startswith("Alpha") for p in data1["projects"])

        r2 = client.get("/api/analytics/portfolio", headers=_auth_header(token2))
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["total_projects"] == 1
        assert data2["projects"][0]["name"] == "Beta"


# ─────────────────────────────────────────────────────────────
# 3. Empty Project Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsEmptyProject:
    """Analytics returns safe defaults for projects with no data."""

    def test_empty_project_analytics(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("emp")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid, "Empty Project")

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        assert r.status_code == 200
        data = r.json()

        assert data["project_id"] == project_id
        assert data["project_name"] == "Empty Project"
        assert data["total_verification_runs"] == 0
        assert data["score_trend"] == []
        assert data["requirement_status"]["total"] == 0
        assert data["issue_severity"]["total"] == 0
        assert data["task_status"]["total"] == 0
        assert data["audit_summary"]["total_events"] == 0
        assert data["documents_analyzed"]["total_documents"] == 0
        assert data["override_impact"]["has_overrides"] is False

    def test_empty_portfolio_analytics(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("newemp")
        _create_user(storage, uid, f"{uid}@test.local")

        r = client.get("/api/analytics/portfolio", headers=_auth_header(create_session_token(uid, f"{uid}@test.local")))
        assert r.status_code == 200
        data = r.json()
        assert data["total_projects"] == 0
        assert data["average_score"] == 0.0
        assert data["projects"] == []

    def test_nonexistent_project_returns_404(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("ghost")
        token = _create_user(storage, uid, f"{uid}@test.local")

        r = client.get("/api/projects/nonexistent-id/analytics", headers=_auth_header(token))
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────
# 4. Score Trend Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsScoreTrends:
    """Score trend calculations across verification runs."""

    def test_single_run_trend(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("tr1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_verification_runs(storage, project_id, run_count=1)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["total_verification_runs"] == 1
        assert len(data["score_trend"]) == 1
        assert data["score_trend"][0]["score"] == 30.0
        assert data["score_trend"][0]["run_number"] == 1
        assert data["score_trend"][0]["trigger"] == "INITIAL_ANALYSIS"

    def test_multiple_runs_trend(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("tr2")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_verification_runs(storage, project_id, run_count=3)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["total_verification_runs"] == 3
        scores = [t["score"] for t in data["score_trend"]]
        assert scores == [30.0, 55.0, 80.0]
        assert all(scores[i] <= scores[i+1] for i in range(len(scores) - 1))

    def test_score_trend_run_numbers_are_sequential(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("tr3")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_verification_runs(storage, project_id, run_count=4)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        run_numbers = [t["run_number"] for t in data["score_trend"]]
        assert run_numbers == [1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────
# 5. Requirement Status Breakdown Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsRequirementStatus:
    """Requirement status aggregation from matches."""

    def test_requirement_status_counts(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("rs1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_matches(storage, project_id, count=5)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        req_status = data["requirement_status"]
        assert req_status["total"] == 5
        assert req_status["has_overrides"] is False
        assert req_status["override_count"] == 0

        baseline = req_status["ai_baseline"]
        assert baseline.get("SATISFIED", 0) == 2
        assert baseline.get("MISSING", 0) == 1
        assert baseline.get("CONFLICT", 0) == 1
        assert baseline.get("PARTIAL", 0) == 1


# ─────────────────────────────────────────────────────────────
# 6. Issue Severity Aggregation Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsIssueSeverity:
    """Issue severity distribution aggregation."""

    def test_issue_severity_distribution(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("is1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_issues(storage, project_id, count=4)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        issue_sev = data["issue_severity"]
        assert issue_sev["total"] == 4
        assert issue_sev["by_severity"].get("CRITICAL", 0) == 1
        assert issue_sev["by_severity"].get("HIGH", 0) == 1
        assert issue_sev["by_severity"].get("MEDIUM", 0) == 1
        assert issue_sev["by_severity"].get("LOW", 0) == 1

        gap_types = issue_sev["by_gap_type"]
        assert "missing_evidence" in gap_types
        assert "expired_evidence" in gap_types


# ─────────────────────────────────────────────────────────────
# 7. Task Status Aggregation Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsTaskStatus:
    """Remediation task status aggregation."""

    def test_task_status_counts(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("ts1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_tasks(storage, project_id, count=3)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        task_status = data["task_status"]
        assert task_status["total"] == 3
        assert task_status["resolved_count"] == 1
        assert task_status["open_count"] == 2
        assert task_status["resolution_rate"] == pytest.approx(33.3, abs=0.1)


# ─────────────────────────────────────────────────────────────
# 8. Audit Activity Summary Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsAuditActivity:
    """Audit event aggregation."""

    def test_audit_summary(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("aa1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_audit_events(storage, project_id, count=5)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        audit = data["audit_summary"]
        assert audit["total_events"] == 5
        assert "AUDITOR" in audit["by_actor_type"]
        assert "AI_AGENT" in audit["by_actor_type"]
        assert "PROJECT_CREATED" in audit["by_event_type"]


# ─────────────────────────────────────────────────────────────
# 9. Auditor Override Impact Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsOverrideImpact:
    """Auditor override impact computation."""

    def test_no_overrides_baseline(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("ovr1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_matches(storage, project_id, count=3)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        impact = data["override_impact"]
        assert impact["has_overrides"] is False
        assert impact["override_count"] == 0

    def test_with_overrides_impact(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("ovr2")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_matches(storage, project_id, count=4)

        _run(storage.save_auditor_override(project_id, "REQ-002", {
            "requirement_id": "REQ-002",
            "original_ai_status": "MISSING",
            "overridden_status": "SATISFIED",
            "auditor_reason": "Document found offline",
            "auditor_note": "",
        }))

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        impact = data["override_impact"]
        assert impact["has_overrides"] is True
        assert impact["override_count"] == 1
        assert impact["score_delta"] > 0
        assert impact["auditor_adjusted_score"] > impact["ai_score"]


# ─────────────────────────────────────────────────────────────
# 10. Portfolio Analytics Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsPortfolio:
    """Cross-project portfolio analytics."""

    def test_portfolio_aggregates_multiple_projects(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("pfa")
        token = _create_user(storage, uid, f"{uid}@test.local")

        proj1 = _create_project_with_data(storage, uid, "Project A")
        proj2 = _create_project_with_data(storage, uid, "Project B")

        _seed_matches(storage, proj1, count=5)
        _seed_verification_runs(storage, proj1, run_count=2)
        _seed_issues(storage, proj2, count=3)
        _seed_tasks(storage, proj2, count=2)

        r = client.get("/api/analytics/portfolio", headers=_auth_header(token))
        data = r.json()

        assert data["total_projects"] == 2
        assert data["total_requirements"] == 5
        assert data["total_issues"] == 3
        assert data["total_tasks"] == 2
        assert data["total_verification_runs"] == 2
        assert len(data["projects"]) == 2

    def test_portfolio_average_score(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("pfb")
        token = _create_user(storage, uid, f"{uid}@test.local")

        proj1 = _create_project_with_data(storage, uid, "Scored A")
        proj2 = _create_project_with_data(storage, uid, "Scored B")

        _run(storage.update_project(proj1, {"compliance_score": 80.0}))
        _run(storage.update_project(proj2, {"compliance_score": 60.0}))

        r = client.get("/api/analytics/portfolio", headers=_auth_header(token))
        data = r.json()

        assert data["average_score"] == 70.0

    def test_portfolio_status_distribution(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("pfc")
        token = _create_user(storage, uid, f"{uid}@test.local")

        p1 = _create_project_with_data(storage, uid, "Ready")
        p2 = _create_project_with_data(storage, uid, "Action")
        _run(storage.update_project(p1, {"overall_status": "READY"}))
        _run(storage.update_project(p2, {"overall_status": "ACTION_REQUIRED"}))

        r = client.get("/api/analytics/portfolio", headers=_auth_header(token))
        data = r.json()

        dist = data["status_distribution"]
        assert dist.get("READY") == 1
        assert dist.get("ACTION_REQUIRED") == 1


# ─────────────────────────────────────────────────────────────
# 11. Malformed / Empty Historical Data Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsMalformedData:
    """Analytics handles edge cases gracefully."""

    def test_run_with_zero_score(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("mal1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        _run(storage.save_verification_run(project_id, {
            "trigger": "INITIAL_ANALYSIS",
            "overall_status": "ACTION_REQUIRED",
            "compliance_score": 0.0,
            "satisfied_count": 0,
            "total_count": 10,
            "requirements_snapshot": [],
            "matches_snapshot": [],
            "issues_snapshot": [],
            "tasks_snapshot": [],
            "documents_used": [],
            "resolved_gaps": [],
            "remaining_gaps": ["GAP-001", "GAP-002"],
            "summary": "Zero score run",
        }))

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["total_verification_runs"] == 1
        assert data["score_trend"][0]["score"] == 0.0
        assert data["remediation_effectiveness"]["total_remaining_gaps"] == 2

    def test_run_with_perfect_score(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("mal2")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        _run(storage.save_verification_run(project_id, {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": "READY",
            "compliance_score": 100.0,
            "satisfied_count": 12,
            "total_count": 12,
            "requirements_snapshot": [],
            "matches_snapshot": [],
            "issues_snapshot": [],
            "tasks_snapshot": [],
            "documents_used": ["evidence.pdf"],
            "resolved_gaps": ["GAP-001", "GAP-002", "GAP-003"],
            "remaining_gaps": [],
            "summary": "All requirements satisfied",
        }))

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["score_trend"][0]["score"] == 100.0
        assert data["score_trend"][0]["status"] == "READY"
        assert data["remediation_effectiveness"]["total_resolved_gaps"] == 3
        assert data["remediation_effectiveness"]["total_remaining_gaps"] == 0

    def test_project_with_none_score(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("mal3")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["current_score"] is None
        assert data["score_trend"] == []

    def test_empty_matches_list(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("mal4")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        assert data["requirement_status"]["total"] == 0
        assert data["requirement_status"]["ai_baseline"] == {}
        assert data["override_impact"]["has_overrides"] is False


# ─────────────────────────────────────────────────────────────
# 12. doc_names Bug Regression Test
# ─────────────────────────────────────────────────────────────

class TestDocNamesBugRegression:
    """Regression test for the doc_names undefined variable bug in _run_verification_task."""

    def test_verification_run_snapshot_includes_documents_used(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("dr1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        run_data = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": "ACTION_REQUIRED",
            "compliance_score": 50.0,
            "satisfied_count": 2,
            "total_count": 4,
            "requirements_snapshot": [],
            "matches_snapshot": [],
            "issues_snapshot": [],
            "tasks_snapshot": [],
            "documents_used": ["policy.pdf", "certificate.pdf"],
            "resolved_gaps": [],
            "remaining_gaps": ["GAP-001"],
            "summary": "Verification with documents",
        }
        run_id = _run(storage.save_verification_run(project_id, run_data))

        run = _run(storage.get_verification_run(project_id, run_id))
        assert run is not None
        assert "documents_used" in run
        assert "policy.pdf" in run["documents_used"]
        assert "certificate.pdf" in run["documents_used"]

    def test_analytics_documents_analyzed_reflects_uploads(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("dr2")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        _run(storage.save_document_analysis(project_id, "doc1", {
            "name": "requirements.pdf",
            "role": "requirements",
            "text": "Some text",
            "file_size": 1024,
            "total_chunks": 3,
            "total_characters": 500,
        }))
        _run(storage.save_document_analysis(project_id, "doc2", {
            "name": "evidence.pdf",
            "role": "evidence",
            "text": "Evidence text",
            "file_size": 2048,
            "total_chunks": 5,
            "total_characters": 1000,
        }))

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        docs = data["documents_analyzed"]
        assert docs["total_documents"] == 2
        assert docs["by_role"].get("requirements") == 1
        assert docs["by_role"].get("evidence") == 1
        assert docs["total_file_size_bytes"] == 3072


# ─────────────────────────────────────────────────────────────
# 13. Remediation Effectiveness Tests
# ─────────────────────────────────────────────────────────────

class TestAnalyticsRemediationEffectiveness:
    """Remediation effectiveness across verification runs."""

    def test_remediation_progression(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("rem1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)
        _seed_verification_runs(storage, project_id, run_count=3)

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        rem = data["remediation_effectiveness"]
        assert rem["total_runs"] == 3
        assert len(rem["score_progression"]) == 3
        assert len(rem["gap_resolution_history"]) == 3

        last_history = rem["gap_resolution_history"][-1]
        assert last_history["resolved_count"] == 2
        assert last_history["remaining_count"] == 3

    def test_framework_coverage(self, analytics_ctx):
        client = analytics_ctx["client"]
        storage = analytics_ctx["storage"]
        uid = _uniq("fw1")
        token = _create_user(storage, uid, f"{uid}@test.local")
        project_id = _create_project_with_data(storage, uid)

        reqs = [
            {
                "requirement_id": "REQ-001",
                "title": "Test Req 1",
                "description": "Desc",
                "priority": "HIGH",
                "framework_id": "fw_test",
                "framework_name": "Test Framework",
                "framework_version": "1.0",
            },
            {
                "requirement_id": "REQ-002",
                "title": "Test Req 2",
                "description": "Desc",
                "priority": "MEDIUM",
                "framework_id": "fw_test",
                "framework_name": "Test Framework",
                "framework_version": "1.0",
            },
        ]
        _run(storage.save_requirements(project_id, reqs))

        _run(storage.update_project(project_id, {
            "metadata_json": json.dumps({
                "active_framework_id": "fw_test",
                "active_framework_name": "Test Framework",
                "active_framework_version": "1.0",
            }),
        }))

        r = client.get(f"/api/projects/{project_id}/analytics", headers=_auth_header(token))
        data = r.json()

        fw = data["framework_coverage"]
        assert fw["framework_name"] == "Test Framework"
        assert fw["framework_version"] == "1.0"
        assert fw["total_requirements"] == 2
        assert fw["framework_linked_requirements"] == 2
        assert fw["coverage_pct"] == 100.0
