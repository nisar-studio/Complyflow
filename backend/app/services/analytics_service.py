"""
ComplyFlow — Enterprise Compliance Analytics Service

Read-only aggregation service for compliance analytics.
Queries existing storage methods without any mutations.
Supports project-scoped analytics and cross-project portfolio views.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.storage import StorageInterface, get_storage


class AnalyticsService:
    """Provides read-only analytics across ComplyFlow compliance data."""

    def __init__(self, storage: Optional[StorageInterface] = None):
        self._storage = storage

    @property
    def storage(self) -> StorageInterface:
        return self._storage or get_storage()

    @storage.setter
    def storage(self, value: Optional[StorageInterface]):
        self._storage = value

    # ── Project-Scoped Analytics ─────────────────────────────

    async def get_project_analytics(self, project_id: str) -> Dict[str, Any]:
        """
        Compute comprehensive analytics for a single project.
        All reads are against existing storage — no mutations.
        """
        project = await self.storage.get_project(project_id)
        if not project:
            return {}

        # Gather all data sources in parallel-ish pattern
        matches = await self.storage.get_matches(project_id)
        issues = await self.storage.get_issues(project_id)
        tasks = await self.storage.get_tasks(project_id)
        runs = await self.storage.list_verification_runs(project_id)
        overrides = await self.storage.list_auditor_overrides(project_id)
        documents = await self.storage.list_documents(project_id)
        audit_events = await self.storage.list_audit_events(
            project_id, limit=200
        )
        requirements = await self.storage.get_requirements(project_id)

        # 1. Score trend across verification runs
        score_trend = self._compute_score_trend(runs)

        # 2. Requirement status breakdown
        requirement_status = self._compute_requirement_status(matches, overrides)

        # 3. Issue severity distribution
        issue_severity = self._compute_issue_severity(issues)

        # 4. Remediation task status
        task_status = self._compute_task_status(tasks)

        # 5. Audit activity summary
        audit_summary = self._compute_audit_summary(audit_events)

        # 6. Framework coverage
        framework_coverage = self._compute_framework_coverage(
            project, requirements, runs
        )

        # 7. Remediation effectiveness
        remediation_effectiveness = self._compute_remediation_effectiveness(runs)

        # 8. Documents analyzed
        documents_analyzed = self._compute_documents_analyzed(documents)

        # 9. Auditor override impact
        override_impact = self._compute_override_impact(
            project, matches, overrides
        )

        return {
            "project_id": project_id,
            "project_name": project.get("name", "Untitled"),
            "overall_status": project.get("overall_status"),
            "current_score": project.get("compliance_score"),
            "score_trend": score_trend,
            "requirement_status": requirement_status,
            "issue_severity": issue_severity,
            "task_status": task_status,
            "audit_summary": audit_summary,
            "framework_coverage": framework_coverage,
            "remediation_effectiveness": remediation_effectiveness,
            "documents_analyzed": documents_analyzed,
            "override_impact": override_impact,
            "total_verification_runs": len(runs),
        }

    # ── Portfolio-Level Analytics ────────────────────────────

    async def get_portfolio_analytics(
        self, user_id: str
    ) -> Dict[str, Any]:
        """
        Compute cross-project portfolio analytics for a user.
        Only returns data for projects the user is a member of.
        """
        user_projects = await self.storage.list_user_projects(user_id)

        if not user_projects:
            return {
                "total_projects": 0,
                "average_score": 0.0,
                "status_distribution": {},
                "total_requirements": 0,
                "total_issues": 0,
                "total_tasks": 0,
                "total_verification_runs": 0,
                "total_audit_events": 0,
                "projects": [],
            }

        total_score = 0.0
        scored_count = 0
        status_counter: Counter = Counter()
        total_requirements = 0
        total_issues = 0
        total_tasks = 0
        total_runs = 0
        total_events = 0
        project_summaries: List[Dict[str, Any]] = []

        for proj in user_projects:
            pid = proj.get("project_id", "")
            score = proj.get("compliance_score")
            status = proj.get("overall_status") or proj.get("status", "PENDING")

            if score is not None:
                total_score += float(score)
                scored_count += 1

            status_counter[status] += 1

            # Gather counts from child tables
            proj_matches = await self.storage.get_matches(pid)
            proj_issues = await self.storage.get_issues(pid)
            proj_tasks = await self.storage.get_tasks(pid)
            proj_runs = await self.storage.list_verification_runs(pid)
            proj_events = await self.storage.list_audit_events(pid, limit=10)

            total_requirements += len(proj_matches)
            total_issues += len(proj_issues)
            total_tasks += len(proj_tasks)
            total_runs += len(proj_runs)

            # Get full event count
            event_count = await self.storage.count_audit_events(pid)
            total_events += event_count

            project_summaries.append({
                "project_id": pid,
                "name": proj.get("name", "Untitled"),
                "compliance_score": score,
                "overall_status": status,
                "requirements_count": len(proj_matches),
                "issues_count": len(proj_issues),
                "tasks_count": len(proj_tasks),
                "verification_runs_count": len(proj_runs),
                "audit_events_count": event_count,
                "created_at": proj.get("created_at"),
            })

        average_score = (
            round(total_score / scored_count, 1) if scored_count > 0 else 0.0
        )

        return {
            "total_projects": len(user_projects),
            "average_score": average_score,
            "status_distribution": dict(status_counter),
            "total_requirements": total_requirements,
            "total_issues": total_issues,
            "total_tasks": total_tasks,
            "total_verification_runs": total_runs,
            "total_audit_events": total_events,
            "projects": project_summaries,
        }

    # ── Private Aggregation Methods ─────────────────────────

    def _compute_score_trend(
        self, runs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract compliance score over time from verification runs.
        Returns a list of {run_number, score, timestamp, status, trigger} dicts.
        """
        trend = []
        for run in runs:
            run_data = {
                "run_number": run.get("run_number", 0),
                "run_id": run.get("run_id", ""),
                "score": run.get("compliance_score", 0.0),
                "status": run.get("overall_status", "PENDING"),
                "timestamp": run.get("timestamp", ""),
                "trigger": run.get("trigger", "INITIAL_ANALYSIS"),
                "satisfied_count": run.get("satisfied_count", 0),
                "total_count": run.get("total_count", 0),
            }
            trend.append(run_data)
        return trend

    def _compute_requirement_status(
        self,
        matches: List[Dict[str, Any]],
        overrides: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute requirement status breakdown from matches and overrides.
        Reports both AI baseline and auditor-adjusted counts.
        """
        ai_status_counter: Counter = Counter()
        adjusted_status_counter: Counter = Counter()
        override_map = {o.get("requirement_id"): o for o in overrides}

        for m in matches:
            status = m.get("status", "UNKNOWN")
            ai_status_counter[status] += 1

            # Check if auditor overrode this requirement
            req_id = m.get("requirement_id")
            if req_id and req_id in override_map:
                overridden = override_map[req_id].get("overridden_status", status)
                adjusted_status_counter[overridden] += 1
            else:
                adjusted_status_counter[status] += 1

        total = len(matches)
        return {
            "total": total,
            "ai_baseline": dict(ai_status_counter),
            "auditor_adjusted": dict(adjusted_status_counter),
            "has_overrides": len(overrides) > 0,
            "override_count": len(overrides),
        }

    def _compute_issue_severity(
        self, issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute issue/gap severity distribution."""
        severity_counter: Counter = Counter()
        gap_type_counter: Counter = Counter()

        for issue in issues:
            severity = issue.get("severity", "MEDIUM")
            severity_counter[severity] += 1
            gap_type = issue.get("gap_type", "unknown")
            gap_type_counter[gap_type] += 1

        return {
            "total": len(issues),
            "by_severity": dict(severity_counter),
            "by_gap_type": dict(gap_type_counter),
        }

    def _compute_task_status(
        self, tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute remediation task status and severity breakdown."""
        status_counter: Counter = Counter()
        severity_counter: Counter = Counter()

        for task in tasks:
            status = task.get("status", "OPEN")
            status_counter[status] += 1
            severity = task.get("severity", "MEDIUM")
            severity_counter[severity] += 1

        total = len(tasks)
        resolved = status_counter.get("RESOLVED", 0)
        open_count = status_counter.get("OPEN", 0)

        return {
            "total": total,
            "by_status": dict(status_counter),
            "by_severity": dict(severity_counter),
            "resolved_count": resolved,
            "open_count": open_count,
            "resolution_rate": (
                round((resolved / total) * 100, 1) if total > 0 else 0.0
            ),
        }

    def _compute_audit_summary(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute audit activity summary from events."""
        event_type_counter: Counter = Counter()
        actor_type_counter: Counter = Counter()
        severity_counter: Counter = Counter()

        for event in events:
            event_type_counter[event.get("event_type", "UNKNOWN")] += 1
            actor_type_counter[event.get("actor_type", "UNKNOWN")] += 1
            severity_counter[event.get("severity", "INFO")] += 1

        return {
            "total_events": len(events),
            "by_event_type": dict(event_type_counter),
            "by_actor_type": dict(actor_type_counter),
            "by_severity": dict(severity_counter),
        }

    def _compute_framework_coverage(
        self,
        project: Dict[str, Any],
        requirements: List[Dict[str, Any]],
        runs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute framework coverage metrics from project metadata."""
        meta = {}
        meta_raw = project.get("metadata_json")
        if meta_raw:
            if isinstance(meta_raw, str):
                import json
                try:
                    meta = json.loads(meta_raw)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            elif isinstance(meta_raw, dict):
                meta = meta_raw

        framework_id = meta.get("active_framework_id")
        framework_name = meta.get("active_framework_name", "")
        framework_version = meta.get("active_framework_version", "")

        # Count requirements with framework references
        framework_req_count = 0
        category_counts: Counter = Counter()
        for req in requirements:
            if req.get("framework_id") or req.get("framework_name"):
                framework_req_count += 1
            cat = req.get("category", "General")
            category_counts[cat] += 1

        total_reqs = len(requirements)

        return {
            "framework_id": framework_id,
            "framework_name": framework_name,
            "framework_version": framework_version,
            "total_requirements": total_reqs,
            "framework_linked_requirements": framework_req_count,
            "coverage_pct": (
                round((framework_req_count / total_reqs) * 100, 1)
                if total_reqs > 0
                else 0.0
            ),
            "category_breakdown": dict(category_counts),
        }

    def _compute_remediation_effectiveness(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compute remediation effectiveness across verification runs.
        Tracks gap resolution rate and score progression.
        """
        if not runs:
            return {
                "total_runs": 0,
                "score_progression": [],
                "gap_resolution_history": [],
                "total_resolved_gaps": 0,
                "total_remaining_gaps": 0,
            }

        score_progression: List[Dict[str, Any]] = []
        gap_resolution_history: List[Dict[str, Any]] = []
        all_resolved: set = set()
        all_remaining: set = set()

        for run in runs:
            run_num = run.get("run_number", 0)
            score = run.get("compliance_score", 0.0)
            resolved = run.get("resolved_gaps", []) or []
            remaining = run.get("remaining_gaps", []) or []

            score_progression.append({
                "run_number": run_num,
                "score": score,
            })

            gap_resolution_history.append({
                "run_number": run_num,
                "resolved_count": len(resolved),
                "remaining_count": len(remaining),
                "resolved_gaps": resolved,
                "remaining_gaps": remaining,
            })

            all_resolved.update(resolved)
            all_remaining.update(remaining)

        # Remove gaps that appear in both (more recent remaining wins)
        final_remaining = all_remaining - all_resolved
        # Actually, resolved is cumulative — gaps that appear resolved in any run
        # were resolved. Remaining in the latest run are truly remaining.
        if runs:
            latest = runs[-1]
            final_remaining = set(latest.get("remaining_gaps", []) or [])
            final_resolved = set(latest.get("resolved_gaps", []) or [])
        else:
            final_resolved = set()
            final_remaining = set()

        return {
            "total_runs": len(runs),
            "score_progression": score_progression,
            "gap_resolution_history": gap_resolution_history,
            "total_resolved_gaps": len(final_resolved),
            "total_remaining_gaps": len(final_remaining),
        }

    def _compute_documents_analyzed(
        self, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute document analysis metrics."""
        role_counter: Counter = Counter()
        total_size = 0
        total_chunks = 0
        total_characters = 0

        for doc in documents:
            role = doc.get("role", "unknown")
            role_counter[role] += 1
            total_size += doc.get("file_size", 0)
            total_chunks += doc.get("total_chunks", 0)
            total_characters += doc.get("total_characters", 0)

        return {
            "total_documents": len(documents),
            "by_role": dict(role_counter),
            "total_file_size_bytes": total_size,
            "total_chunks": total_chunks,
            "total_characters": total_characters,
        }

    def _compute_override_impact(
        self,
        project: Dict[str, Any],
        matches: List[Dict[str, Any]],
        overrides: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute the impact of auditor overrides on compliance scores.
        Shows AI baseline score vs auditor-adjusted score.
        """
        ai_score = float(project.get("compliance_score") or 0.0)

        if not overrides or not matches:
            return {
                "has_overrides": False,
                "ai_score": ai_score,
                "auditor_adjusted_score": ai_score,
                "score_delta": 0.0,
                "override_count": 0,
                "overrides": [],
            }

        override_map = {o.get("requirement_id"): o for o in overrides}
        total = len(matches)

        # Calculate adjusted score
        adjusted_sum = 0.0
        for m in matches:
            req_id = m.get("requirement_id")
            if req_id in override_map:
                effective = override_map[req_id].get("overridden_status", m.get("status", "UNKNOWN"))
            else:
                effective = m.get("status", "UNKNOWN")

            if effective == "SATISFIED":
                adjusted_sum += 100.0
            elif effective == "PARTIAL":
                adjusted_sum += 50.0
            # MISSING, CONFLICT, UNKNOWN = 0

        adjusted_score = round(adjusted_sum / total, 1) if total > 0 else ai_score
        delta = round(adjusted_score - ai_score, 1)

        override_details = []
        for o in overrides:
            override_details.append({
                "requirement_id": o.get("requirement_id"),
                "original_status": o.get("original_ai_status", "UNKNOWN"),
                "overridden_status": o.get("overridden_status", "UNKNOWN"),
                "reason": o.get("auditor_reason", ""),
                "created_at": o.get("created_at"),
            })

        return {
            "has_overrides": True,
            "ai_score": ai_score,
            "auditor_adjusted_score": adjusted_score,
            "score_delta": delta,
            "override_count": len(overrides),
            "overrides": override_details,
        }


# Global singleton
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
