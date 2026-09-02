"""
test_portfolio_dashboard.py — Cross-Project Portfolio Dashboard Tests (Epic B)

Tests:
  1. Portfolio overview across multiple projects
  2. User sees only authorized projects
  3. Inaccessible project metrics cannot affect aggregates
  4. Overdue task aggregation
  5. Six-month trend calculation
  6. Recent activity authorization/filtering
  7. Top-risk aggregation/filtering
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import hash_password, Role, create_session_token
from app.services.analytics_service import AnalyticsService


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def dash_ctx(tmp_path_factory):
    """Isolated database and TestClient for dashboard tests."""
    tmp = tmp_path_factory.mktemp("portfolio_dashboard")
    db_path = str(tmp / "dash.db")
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

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    # Seed users
    _run(test_storage.create_user({
        "user_id": "dash_admin",
        "email": "dash_admin@test.com",
        "name": "Dash Admin",
        "password_hash": hash_password("AdminPass123!"),
        "is_active": True,
    }))
    _run(test_storage.create_user({
        "user_id": "dash_member",
        "email": "dash_member@test.com",
        "name": "Dash Member",
        "password_hash": hash_password("MemberPass123!"),
        "is_active": True,
    }))
    _run(test_storage.create_user({
        "user_id": "dash_outsider",
        "email": "dash_outsider@test.com",
        "name": "Dash Outsider",
        "password_hash": hash_password("OutsiderPass123!"),
        "is_active": True,
    }))

    # Create projects with different compliance states
    now = datetime.now(timezone.utc).isoformat()

    # Project 1: READY
    _run(test_storage.create_project({
        "project_id": "proj_ready",
        "name": "Ready Project",
        "status": "READY",
        "compliance_score": 100.0,
        "overall_status": "READY",
    }))
    _run(test_storage.add_project_member("proj_ready", "dash_admin", Role.ADMIN.value))
    _run(test_storage.add_project_member("proj_ready", "dash_member", Role.AUDITOR.value))

    # Project 2: ACTION_REQUIRED
    _run(test_storage.create_project({
        "project_id": "proj_action",
        "name": "Action Project",
        "status": "ACTION_REQUIRED",
        "compliance_score": 50.0,
        "overall_status": "ACTION_REQUIRED",
    }))
    _run(test_storage.add_project_member("proj_action", "dash_admin", Role.ADMIN.value))

    # Project 3: PENDING (no score)
    _run(test_storage.create_project({
        "project_id": "proj_pending",
        "name": "Pending Project",
        "status": "PENDING",
        "compliance_score": None,
        "overall_status": None,
    }))
    _run(test_storage.add_project_member("proj_pending", "dash_admin", Role.ADMIN.value))

    # Add overdue tasks to proj_action
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _run(test_storage.save_tasks("proj_action", [
        {
            "task_id": "TASK-OVERDUE-1",
            "title": "Overdue Task 1",
            "severity": "HIGH",
            "status": "OPEN",
            "due_date": yesterday,
            "related_requirement_id": "REQ-001",
        },
        {
            "task_id": "TASK-OVERDUE-2",
            "title": "Overdue Task 2",
            "severity": "CRITICAL",
            "status": "OPEN",
            "due_date": yesterday,
            "related_requirement_id": "REQ-002",
        },
    ]))

    # Add a non-overdue task
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    _run(test_storage.save_tasks("proj_action", [
        {
            "task_id": "TASK-OK-1",
            "title": "Future Task",
            "severity": "MEDIUM",
            "status": "OPEN",
            "due_date": future,
            "related_requirement_id": "REQ-003",
        },
    ]))

    # Add issues to proj_action
    _run(test_storage.save_issues("proj_action", [
        {"gap_id": "GAP-001", "gap_type": "missing_evidence", "severity": "HIGH", "description": "Missing insurance"},
        {"gap_id": "GAP-002", "gap_type": "conflict", "severity": "CRITICAL", "description": "Address mismatch"},
    ]))

    # Add a verification run to proj_ready
    _run(test_storage.save_verification_run("proj_ready", {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "READY",
        "compliance_score": 100.0,
        "satisfied_count": 12,
        "total_count": 12,
        "requirements_snapshot": [],
        "matches_snapshot": [],
        "issues_snapshot": [],
        "tasks_snapshot": [],
        "documents_used": [],
        "resolved_gaps": [],
        "remaining_gaps": [],
        "summary": "All requirements satisfied.",
    }))

    # Add an audit event
    _run(test_storage.save_audit_event("proj_ready", {
        "event_type": "ANALYSIS_COMPLETED",
        "actor_type": "AI_AGENT",
        "severity": "INFO",
        "summary": "Analysis completed successfully.",
    }))

    # Token for admin (sees all 3 projects)
    admin_token = create_session_token("dash_admin", "dash_admin@test.com")
    # Token for member (sees only proj_ready)
    member_token = create_session_token("dash_member", "dash_member@test.com")
    # Token for outsider (sees nothing)
    outsider_token = create_session_token("dash_outsider", "dash_outsider@test.com")

    yield {
        "client": client,
        "storage": test_storage,
        "admin_token": admin_token,
        "member_token": member_token,
        "outsider_token": outsider_token,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


# ── Tests ─────────────────────────────────────────────────────


class TestPortfolioOverview:
    """Test portfolio overview across multiple projects."""

    def test_portfolio_returns_multiple_projects(self, dash_ctx):
        """Admin sees all 3 projects in portfolio."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_projects"] == 3

    def test_portfolio_computes_average_score(self, dash_ctx):
        """Average score reflects only scored projects."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        # proj_ready=100, proj_action=50, proj_pending=None → avg of 2 scored
        assert data["average_score"] == 75.0

    def test_portfolio_compliant_and_needs_action_counts(self, dash_ctx):
        """Compliant and needs-action counts are correct."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        assert data["compliant_projects"] == 1  # proj_ready
        assert data["projects_needing_action"] == 2  # proj_action + proj_pending

    def test_portfolio_aggregates_totals(self, dash_ctx):
        """Aggregate counts are correct across projects."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        assert data["total_tasks"] >= 3  # at least the tasks we added
        assert data["total_issues"] >= 2  # at least the issues we added


class TestPortfolioAuthorization:
    """Test that users only see authorized projects."""

    def test_member_sees_only_member_projects(self, dash_ctx):
        """Member sees only proj_ready (1 project)."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['member_token']}"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_projects"] == 1
        assert data["projects"][0]["project_id"] == "proj_ready"

    def test_outsider_sees_nothing(self, dash_ctx):
        """User with no projects sees empty portfolio."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['outsider_token']}"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["total_projects"] == 0
        assert data["projects"] == []

    def test_unauthenticated_returns_401(self, dash_ctx):
        """Unauthenticated request returns 401."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio")
        assert res.status_code == 401


class TestOverdueTasks:
    """Test overdue task aggregation."""

    def test_overdue_tasks_detected(self, dash_ctx):
        """Overdue tasks are correctly identified."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        overdue = data["overdue_tasks"]
        assert overdue["total_overdue"] >= 2  # at least our 2 overdue tasks

    def test_overdue_tasks_project_association(self, dash_ctx):
        """Overdue tasks are associated with correct projects."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        overdue = data["overdue_tasks"]
        project_ids = [p["project_id"] for p in overdue["by_project"]]
        assert "proj_action" in project_ids

    def test_member_does_not_see_other_project_overdue(self, dash_ctx):
        """Member only sees overdue tasks from their projects."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['member_token']}"
        })
        data = res.json()
        overdue = data["overdue_tasks"]
        # Member only has proj_ready (no overdue tasks there)
        assert overdue["total_overdue"] == 0


class TestScoreTrend:
    """Test six-month compliance score trend."""

    def test_score_trend_has_six_months(self, dash_ctx):
        """Trend contains exactly 6 monthly entries."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        trend = data["score_trend"]
        assert len(trend) == 6

    def test_score_trend_chronological_order(self, dash_ctx):
        """Trend entries are in chronological order."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        trend = data["score_trend"]
        months = [t["month"] for t in trend]
        assert months == sorted(months)

    def test_score_trend_null_for_empty_months(self, dash_ctx):
        """Months with no verification data show null score."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        trend = data["score_trend"]
        # Most months should be null since we only added 1 verification run
        null_months = [t for t in trend if t["average_score"] is None]
        assert len(null_months) >= 4  # at least 4 months should be null


class TestRecentActivity:
    """Test recent activity feed."""

    def test_recent_activity_returns_events(self, dash_ctx):
        """Recent activity includes audit events."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        activity = data["recent_activity"]
        assert len(activity) >= 1
        assert activity[0]["event_type"] == "ANALYSIS_COMPLETED"

    def test_recent_activity_includes_project_info(self, dash_ctx):
        """Activity events include project name and ID."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        activity = data["recent_activity"]
        assert activity[0]["project_id"] == "proj_ready"
        assert activity[0]["project_name"] == "Ready Project"

    def test_member_only_sees_own_project_activity(self, dash_ctx):
        """Member only sees activity from their projects."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['member_token']}"
        })
        data = res.json()
        activity = data["recent_activity"]
        # Member only has proj_ready
        for event in activity:
            assert event["project_id"] == "proj_ready"


class TestTopRisks:
    """Test top-risk aggregation."""

    def test_top_risks_sorted_by_score(self, dash_ctx):
        """Top risks are sorted by compliance score ascending."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        risks = data["top_risks"]
        if len(risks) > 1:
            scores = [r["compliance_score"] for r in risks]
            assert scores == sorted(scores)

    def test_top_risks_exclude_unscored_projects(self, dash_ctx):
        """Top risks only include projects with scores."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        risks = data["top_risks"]
        for risk in risks:
            assert risk["compliance_score"] is not None

    def test_top_risks_limit_to_five(self, dash_ctx):
        """Top risks are limited to 5 entries."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['admin_token']}"
        })
        data = res.json()
        risks = data["top_risks"]
        assert len(risks) <= 5


class TestEmptyPortfolio:
    """Test behavior with empty portfolio."""

    def test_empty_portfolio_returns_defaults(self, dash_ctx):
        """User with no projects gets sensible defaults."""
        client = dash_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {dash_ctx['outsider_token']}"
        })
        data = res.json()
        assert data["total_projects"] == 0
        assert data["average_score"] == 0.0
        assert data["overdue_tasks"]["total_overdue"] == 0
        assert data["score_trend"] == []
        assert data["recent_activity"] == []
        assert data["top_risks"] == []


# ── Authorization Contamination Tests ────────────────────────


@pytest.fixture(scope="module")
def contamination_ctx(tmp_path_factory):
    """
    Test that an inaccessible project with extreme values cannot
    contaminate the portfolio aggregates for a member who lacks access.
    """
    tmp = tmp_path_factory.mktemp("contamination")
    db_path = str(tmp / "contamination.db")
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

    from app.main import app
    client = TestClient(app, raise_server_exceptions=True)

    # Create member who should only see their own project
    _run(test_storage.create_user({
        "user_id": "member_only",
        "email": "member_only@test.com",
        "name": "Member Only",
        "password_hash": hash_password("MemberPass123!"),
        "is_active": True,
    }))

    # Create the member's own project: moderate score, 0 overdue tasks
    _run(test_storage.create_project({
        "project_id": "member_proj",
        "name": "Member Project",
        "status": "ACTION_REQUIRED",
        "compliance_score": 70.0,
        "overall_status": "ACTION_REQUIRED",
    }))
    _run(test_storage.add_project_member("member_proj", "member_only", Role.AUDITOR.value))

    # Add a non-overdue task to member_proj
    future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    _run(test_storage.save_tasks("member_proj", [
        {
            "task_id": "MEM-TASK-1",
            "title": "Member Task 1",
            "severity": "LOW",
            "status": "OPEN",
            "due_date": future,
            "related_requirement_id": "MEM-REQ-1",
        },
    ]))

    # Add a verification run for member_proj with score 70
    _run(test_storage.save_verification_run("member_proj", {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 70.0,
        "satisfied_count": 7,
        "total_count": 10,
        "requirements_snapshot": [],
        "matches_snapshot": [],
        "issues_snapshot": [],
        "tasks_snapshot": [],
        "documents_used": [],
        "resolved_gaps": [],
        "remaining_gaps": [],
        "summary": "Partial compliance.",
    }))

    # Add audit event for member_proj
    _run(test_storage.save_audit_event("member_proj", {
        "event_type": "ANALYSIS_COMPLETED",
        "actor_type": "AI_AGENT",
        "severity": "INFO",
        "summary": "Analysis completed for member project.",
    }))

    # ── INACCESSIBLE project: extreme values ──
    # Score=10 (extremely low), 5 overdue tasks, 10 issues
    # Member should NEVER see any of this in their aggregates
    _run(test_storage.create_project({
        "project_id": "inaccessible_extreme",
        "name": "Inaccessible Extreme",
        "status": "ACTION_REQUIRED",
        "compliance_score": 10.0,
        "overall_status": "ACTION_REQUIRED",
    }))
    # DO NOT add member_only as a member of this project

    # Add 5 overdue tasks to the inaccessible project
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    _run(test_storage.save_tasks("inaccessible_extreme", [
        {"task_id": f"EXT-OVERDUE-{i}", "title": f"Extreme Overdue {i}",
         "severity": "CRITICAL", "status": "OPEN",
         "due_date": yesterday,
         "related_requirement_id": f"EXT-REQ-{i}"}
        for i in range(5)
    ]))

    # Add issues to the inaccessible project
    _run(test_storage.save_issues("inaccessible_extreme", [
        {"gap_id": f"EXT-GAP-{i}", "gap_type": "missing_evidence",
         "severity": "CRITICAL", "description": f"Extreme gap {i}"}
        for i in range(10)
    ]))

    # Add a verification run with extremely low score
    _run(test_storage.save_verification_run("inaccessible_extreme", {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 10.0,
        "satisfied_count": 1,
        "total_count": 10,
        "requirements_snapshot": [],
        "matches_snapshot": [],
        "issues_snapshot": [],
        "tasks_snapshot": [],
        "documents_used": [],
        "resolved_gaps": [],
        "remaining_gaps": [],
        "summary": "Very poor compliance.",
    }))

    # Add audit events to the inaccessible project
    for i in range(5):
        _run(test_storage.save_audit_event("inaccessible_extreme", {
            "event_type": "ANALYSIS_COMPLETED",
            "actor_type": "AI_AGENT",
            "severity": "INFO",
            "summary": f"Extreme analysis event {i}.",
        }))

    token = create_session_token("member_only", "member_only@test.com")

    yield {
        "client": client,
        "storage": test_storage,
        "token": token,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


class TestAuthorizationContamination:
    """Ensure inaccessible project data cannot contaminate portfolio aggregates."""

    def test_inaccessible_score_does_not_affect_average(self, contamination_ctx):
        """Inaccessible project's 10% score must not pull the average down."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        assert res.status_code == 200
        data = res.json()
        # Member sees only member_proj with score=70
        assert data["total_projects"] == 1
        assert data["average_score"] == 70.0  # NOT (70+10)/2=40

    def test_inaccessible_overdue_does_not_affect_total(self, contamination_ctx):
        """Inaccessible project's 5 overdue tasks must not appear."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        data = res.json()
        overdue = data["overdue_tasks"]
        # member_proj has 0 overdue tasks (due_date is in the future)
        assert overdue["total_overdue"] == 0
        assert len(overdue["by_project"]) == 0

    def test_inaccessible_verification_does_not_affect_trend(self, contamination_ctx):
        """Inaccessible project's verification run must not appear in trend."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        data = res.json()
        trend = data["score_trend"]
        # Only member_proj's verification run (score=70) should appear
        scored_months = [t for t in trend if t["average_score"] is not None]
        for t in scored_months:
            # The score should be 70, not 10 or an average of both
            assert t["average_score"] == 70.0

    def test_inaccessible_activity_does_not_appear(self, contamination_ctx):
        """Inaccessible project's audit events must not appear in activity."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        data = res.json()
        activity = data["recent_activity"]
        # Only member_proj events should appear
        for event in activity:
            assert event["project_id"] == "member_proj"
            assert event["project_name"] == "Member Project"

    def test_inaccessible_risk_does_not_appear(self, contamination_ctx):
        """Inaccessible project's risk data must not appear in top_risks."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        data = res.json()
        risks = data["top_risks"]
        # Only member_proj should appear (if at all)
        for risk in risks:
            assert risk["project_id"] == "member_proj"

    def test_inaccessible_project_not_in_project_list(self, contamination_ctx):
        """Inaccessible project must not appear in the projects list."""
        client = contamination_ctx["client"]
        res = client.get("/api/analytics/portfolio", headers={
            "Authorization": f"Bearer {contamination_ctx['token']}"
        })
        data = res.json()
        project_ids = [p["project_id"] for p in data["projects"]]
        assert "inaccessible_extreme" not in project_ids
        assert "member_proj" in project_ids
