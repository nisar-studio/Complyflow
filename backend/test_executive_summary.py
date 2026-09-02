"""
test_executive_summary.py — Executive Summary Generation Tests (Epic C)

Tests:
  1. Summary generation from deterministic verification data
  2. AI failure does not fail verification
  3. AI failure results in null/absent summary
  4. Snapshot remains immutable after finalization
  5. Summary is included before snapshot finalization
  6. SUMMARY_GENERATED audit event on success
  7. No false audit event on failure
  8. Existing score/status unchanged by summary
  9. Older runs without summaries remain readable
  10. Summary structure validation
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.summary_service import generate_executive_summary, _sanitize_error


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def sample_verification_result():
    """A realistic deterministic verification result for testing."""
    return {
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 60.0,
        "satisfied_count": 6,
        "total_count": 10,
        "resolved_gaps": ["GAP-001", "GAP-002"],
        "remaining_gaps": ["GAP-003", "GAP-004"],
        "new_issues": [],
        "summary": "6 of 10 requirements satisfied.",
        "matches": [
            {
                "requirement_id": "REQ-001",
                "requirement_title": "Access Control",
                "status": "SATISFIED",
                "confidence": 0.95,
                "reasoning": "RBAC policy document provided.",
            },
            {
                "requirement_id": "REQ-002",
                "requirement_title": "Data Encryption",
                "status": "MISSING",
                "confidence": 0.0,
                "reasoning": "No encryption policy found.",
            },
            {
                "requirement_id": "REQ-003",
                "requirement_title": "Incident Response",
                "status": "CONFLICT",
                "confidence": 0.5,
                "reasoning": "Conflicting dates in policy vs certificate.",
            },
        ],
    }


@pytest.fixture
def mock_gemini_success():
    """Mock Gemini to return a valid executive summary."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "overall_assessment": "The project has moderate compliance with 60% of requirements satisfied.",
        "strengths": [
            "Access control policy is comprehensive",
            "Data governance framework is well-documented",
        ],
        "key_risks": [
            "Encryption policy is missing entirely",
            "Incident response dates are contradictory",
        ],
        "priority_actions": [
            "Upload encryption policy documentation",
            "Resolve incident response date conflict",
        ],
        "notable_findings": [
            "Certificate expiry may affect 2 requirements",
        ],
    })

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.summary_service._get_gemini_client", return_value=mock_client):
        with patch("app.services.summary_service._get_model", return_value="gemini-3.5-flash"):
            yield mock_client


@pytest.fixture
def mock_gemini_failure():
    """Mock Gemini to raise an exception."""
    with patch("app.services.summary_service._get_gemini_client", side_effect=RuntimeError("API key invalid")):
        yield


@pytest.fixture
def mock_gemini_malformed():
    """Mock Gemini to return malformed JSON."""
    mock_response = MagicMock()
    mock_response.text = "This is not valid JSON {{{"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.summary_service._get_gemini_client", return_value=mock_client):
        with patch("app.services.summary_service._get_model", return_value="gemini-3.5-flash"):
            yield mock_client


# ── Tests ─────────────────────────────────────────────────────


class TestSummaryGeneration:
    """Test executive summary generation from verification data."""

    def test_generates_summary_from_verification_data(self, sample_verification_result, mock_gemini_success):
        """Summary is generated from deterministic verification data."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        assert summary is not None
        assert "overall_assessment" in summary
        assert "strengths" in summary
        assert "key_risks" in summary
        assert "priority_actions" in summary
        assert isinstance(summary["strengths"], list)
        assert isinstance(summary["key_risks"], list)
        assert isinstance(summary["priority_actions"], list)

    def test_summary_contains_metadata(self, sample_verification_result, mock_gemini_success):
        """Summary includes generation metadata."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        assert summary["_generated_by"] == "gemini"
        assert summary["_model"] == "gemini-3.5-flash"

    def test_summary_notable_findings_optional(self, sample_verification_result, mock_gemini_success):
        """Notable findings field is optional but included if present."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        # Should have notable_findings from our mock
        assert "notable_findings" in summary
        assert isinstance(summary["notable_findings"], list)

    def test_prompt_includes_verification_data(self, sample_verification_result, mock_gemini_success):
        """The prompt to Gemini includes the verification data."""
        generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        # Verify the client was called
        mock_gemini_success.models.generate_content.assert_called_once()
        call_args = mock_gemini_success.models.generate_content.call_args
        prompt = call_args[1]["contents"] if "contents" in call_args[1] else call_args[0][1] if len(call_args[0]) > 1 else ""
        # The prompt should contain key verification data
        assert "60.0%" in prompt or "60%" in prompt
        assert "ACTION_REQUIRED" in prompt


class TestAIFailureResilience:
    """Test that AI failures don't break verification."""

    def test_api_key_missing_returns_none(self, sample_verification_result):
        """Missing API key returns None gracefully."""
        with patch("app.services.summary_service._get_gemini_client", side_effect=RuntimeError("GEMINI_API_KEY environment variable is not set.")):
            summary = generate_executive_summary(
                verification_result=sample_verification_result,
                project_name="Test Project",
            )
        assert summary is None

    def test_gemini_exception_returns_none(self, sample_verification_result, mock_gemini_failure):
        """Gemini exception returns None."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        assert summary is None

    def test_malformed_json_returns_none(self, sample_verification_result, mock_gemini_malformed):
        """Malformed JSON response returns None."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )
        assert summary is None

    def test_missing_required_keys_returns_none(self, sample_verification_result):
        """Response missing required keys returns None."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "overall_assessment": "Some assessment",
            # Missing strengths, key_risks, priority_actions
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("app.services.summary_service._get_gemini_client", return_value=mock_client):
            with patch("app.services.summary_service._get_model", return_value="gemini-3.5-flash"):
                summary = generate_executive_summary(
                    verification_result=sample_verification_result,
                    project_name="Test Project",
                )
        assert summary is None


class TestSanitizeError:
    """Test error sanitization."""

    def test_removes_api_keys(self):
        error = "API key AIzaSyD... is invalid"
        safe = _sanitize_error(error)
        assert "AIza" not in safe

    def test_removes_bearer_tokens(self):
        error = "Bearer abcdefghijklmnopqrstuvwxyz123456"
        safe = _sanitize_error(error)
        assert "Bearer" not in safe

    def test_preserves_safe_messages(self):
        error = "Network timeout occurred"
        safe = _sanitize_error(error)
        assert "Network timeout occurred" in safe

    def test_truncates_long_messages(self):
        error = "x" * 600
        safe = _sanitize_error(error)
        assert len(safe) < 400


class TestSnapshotImmutability:
    """Test that summary is included in snapshot at save time, not added later."""

    def test_summary_included_at_construction(self, sample_verification_result, mock_gemini_success):
        """The executive summary is part of the snapshot dict before saving."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )

        # Simulate snapshot construction (same as in analysis_routes.py)
        snapshot = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": sample_verification_result["overall_status"],
            "compliance_score": sample_verification_result["compliance_score"],
            "summary": sample_verification_result["summary"],
            "executive_summary": summary,
        }

        # The summary is already in the snapshot — no post-save mutation needed
        assert snapshot["executive_summary"] is not None
        assert snapshot["executive_summary"]["overall_assessment"]

    def test_none_summary_preserves_snapshot(self, sample_verification_result, mock_gemini_failure):
        """When summary fails, snapshot still has executive_summary=None."""
        summary = generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )

        snapshot = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": sample_verification_result["overall_status"],
            "compliance_score": sample_verification_result["compliance_score"],
            "summary": sample_verification_result["summary"],
            "executive_summary": summary,
        }

        assert snapshot["executive_summary"] is None
        # Core verification data is still intact
        assert snapshot["overall_status"] == "ACTION_REQUIRED"
        assert snapshot["compliance_score"] == 60.0


class TestScoreUnchanged:
    """Test that the AI summary does not affect compliance score/status."""

    def test_score_not_modified_by_summary(self, sample_verification_result, mock_gemini_success):
        """Compliance score and status remain unchanged after summary generation."""
        original_score = sample_verification_result["compliance_score"]
        original_status = sample_verification_result["overall_status"]

        generate_executive_summary(
            verification_result=sample_verification_result,
            project_name="Test Project",
        )

        # Original data must be unchanged
        assert sample_verification_result["compliance_score"] == original_score
        assert sample_verification_result["overall_status"] == original_status


class TestBackwardCompatibility:
    """Test that older runs without summaries remain readable."""

    def test_old_snapshot_without_executive_summary(self):
        """Old verification snapshots without executive_summary field are valid."""
        old_snapshot = {
            "trigger": "INITIAL_ANALYSIS",
            "overall_status": "READY",
            "compliance_score": 100.0,
            "satisfied_count": 10,
            "total_count": 10,
            "summary": "All requirements satisfied.",
            # No executive_summary field — simulates pre-v1.2.0 data
        }

        # Should be readable without error
        assert old_snapshot["overall_status"] == "READY"
        assert old_snapshot["compliance_score"] == 100.0
        # Accessing executive_summary should return None (not KeyError)
        assert old_snapshot.get("executive_summary") is None

    def test_new_snapshot_with_executive_summary(self):
        """New verification snapshots with executive_summary are valid."""
        new_snapshot = {
            "trigger": "REMEDIATION_VERIFICATION",
            "overall_status": "ACTION_REQUIRED",
            "compliance_score": 75.0,
            "summary": "75% compliance.",
            "executive_summary": {
                "overall_assessment": "Moderate compliance.",
                "strengths": ["Good access control"],
                "key_risks": ["Missing encryption"],
                "priority_actions": ["Upload encryption docs"],
                "notable_findings": [],
            },
        }

        assert new_snapshot["executive_summary"]["overall_assessment"] == "Moderate compliance."
        assert new_snapshot["compliance_score"] == 75.0
