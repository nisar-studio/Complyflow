"""
ComplyFlow — Verification Run Delta Engine

Provides deterministic, immutable comparative delta analysis between two verification runs.
Calculates score transitions, status transitions, resolved requirements, newly failed requirements,
and issue resolutions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.agent.schemas import RequirementDelta, VerificationDeltaResult


class DeltaEngine:
    """Calculates deterministic comparative deltas between two verification run snapshots."""

    @staticmethod
    def calculate_delta(from_run: Dict[str, Any], to_run: Dict[str, Any]) -> VerificationDeltaResult:
        """
        Compare from_run (earlier snapshot) against to_run (later snapshot).
        Evaluates requirement transitions, score progression, and issue resolutions.
        """
        from_matches = {m.get("requirement_id"): m for m in from_run.get("matches_snapshot", []) or from_run.get("matches", [])}
        to_matches = {m.get("requirement_id"): m for m in to_run.get("matches_snapshot", []) or to_run.get("matches", [])}

        all_req_ids = sorted(list(set(list(from_matches.keys()) + list(to_matches.keys()))))

        resolved_reqs: List[RequirementDelta] = []
        newly_failed_reqs: List[RequirementDelta] = []
        unchanged_reqs: List[RequirementDelta] = []

        for req_id in all_req_ids:
            m_before = from_matches.get(req_id, {})
            m_after = to_matches.get(req_id, {})

            status_before = m_before.get("status", "MISSING").upper()
            status_after = m_after.get("status", "UNKNOWN").upper()
            title = m_after.get("requirement_title") or m_before.get("requirement_title") or req_id

            delta_item = RequirementDelta(
                requirement_id=req_id,
                title=title,
                status_before=status_before,
                status_after=status_after,
                confidence_before=m_before.get("confidence"),
                confidence_after=m_after.get("confidence"),
                reasoning_before=m_before.get("reasoning"),
                reasoning_after=m_after.get("reasoning"),
            )

            # Determine transition type
            if status_before != "SATISFIED" and status_after == "SATISFIED":
                delta_item.change_type = "RESOLVED"
                resolved_reqs.append(delta_item)
            elif status_before == "SATISFIED" and status_after != "SATISFIED":
                delta_item.change_type = "NEWLY_FAILED"
                newly_failed_reqs.append(delta_item)
            elif status_before != status_after:
                delta_item.change_type = "MODIFIED"
                unchanged_reqs.append(delta_item)
            else:
                delta_item.change_type = "UNCHANGED"
                unchanged_reqs.append(delta_item)

        score_before = float(from_run.get("compliance_score", 0.0))
        score_after = float(to_run.get("compliance_score", 0.0))
        score_diff = round(score_after - score_before, 1)

        status_before = from_run.get("overall_status", "ACTION_REQUIRED")
        status_after = to_run.get("overall_status", "READY")

        # Issues resolution
        from_issues = {i.get("gap_id", i.get("description", "")): i for i in from_run.get("issues_snapshot", []) or from_run.get("issues", [])}
        to_issues = {i.get("gap_id", i.get("description", "")): i for i in to_run.get("issues_snapshot", []) or to_run.get("issues", [])}

        resolved_issues = [issue for gid, issue in from_issues.items() if gid not in to_issues]
        new_issues = [issue for gid, issue in to_issues.items() if gid not in from_issues]

        from_run_num = from_run.get("run_number", 1)
        to_run_num = to_run.get("run_number", 2)

        summary = (
            f"Run {from_run_num} → Run {to_run_num}: Score shifted from {score_before}% ({status_before}) "
            f"to {score_after}% ({status_after}). {len(resolved_reqs)} requirement(s) resolved, "
            f"{len(newly_failed_reqs)} newly failed, {len(unchanged_reqs)} unchanged."
        )

        return VerificationDeltaResult(
            from_run_id=from_run.get("run_id", f"run_{from_run_num}"),
            to_run_id=to_run.get("run_id", f"run_{to_run_num}"),
            from_run_number=from_run_num,
            to_run_number=to_run_num,
            score_before=score_before,
            score_after=score_after,
            score_diff=score_diff,
            status_before=status_before,
            status_after=status_after,
            resolved_count=len(resolved_reqs),
            newly_failed_count=len(newly_failed_reqs),
            unchanged_count=len(unchanged_reqs),
            resolved_requirements=resolved_reqs,
            newly_failed_requirements=newly_failed_reqs,
            unchanged_requirements=unchanged_reqs,
            resolved_issues=resolved_issues,
            new_issues=new_issues,
            summary=summary,
        )


# Global singleton instance
_delta_engine: Optional[DeltaEngine] = None


def get_delta_engine() -> DeltaEngine:
    global _delta_engine
    if _delta_engine is None:
        _delta_engine = DeltaEngine()
    return _delta_engine
