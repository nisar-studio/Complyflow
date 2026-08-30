"""
ComplyFlow — Versioned Verification Snapshots & Delta Engine Test Suite

Tests immutable snapshot persistence, sequential run numbering,
historical retrieval, and deterministic Before/After delta calculations
including the NovaTech 75% -> 100% regression test.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from app.services.storage import SQLiteStorageService
from app.services.delta_service import DeltaEngine
from fastapi.testclient import TestClient
from app.services.auth_service import create_session_token
from app.main import app

client = TestClient(app)
token = create_session_token("demo-user", "demo@complyflow.local")
client.headers["Authorization"] = f"Bearer {token}"



@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    storage = SQLiteStorageService(db_path=temp_path)
    yield storage
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_first_verification_creates_run_1_and_second_creates_run_2(temp_storage):
    project_id = await temp_storage.create_project({"name": "Snapshot Test"})

    # 1. First run (Initial Analysis - 75%)
    run_1_data = {
        "trigger": "INITIAL_ANALYSIS",
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 75.0,
        "satisfied_count": 3,
        "total_count": 4,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED", "confidence": 0.98},
            {"requirement_id": "REQ-002", "requirement_title": "Insurance Policy", "status": "MISSING", "confidence": 1.0},
            {"requirement_id": "REQ-003", "requirement_title": "Registered Address", "status": "CONFLICT", "confidence": 0.95},
            {"requirement_id": "REQ-004", "requirement_title": "Tax Good Standing", "status": "SATISFIED", "confidence": 0.99},
        ],
        "issues_snapshot": [
            {"gap_id": "GAP-001", "description": "Missing insurance"},
            {"gap_id": "GAP-002", "description": "Address conflict Suite 800 vs Suite 400"},
        ],
        "summary": "Initial analysis: 2 issues detected.",
    }

    run_1_id = await temp_storage.save_verification_run(project_id, run_1_data)
    assert run_1_id == "run_1"

    loaded_run_1 = await temp_storage.get_verification_run(project_id, "run_1")
    assert loaded_run_1 is not None
    assert loaded_run_1["run_number"] == 1
    assert loaded_run_1["compliance_score"] == 75.0
    assert loaded_run_1["overall_status"] == "ACTION_REQUIRED"

    # 2. Second run (Post-Remediation Verification - 100%)
    run_2_data = {
        "trigger": "REMEDIATION_VERIFICATION",
        "overall_status": "READY",
        "compliance_score": 100.0,
        "satisfied_count": 4,
        "total_count": 4,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED", "confidence": 0.98},
            {"requirement_id": "REQ-002", "requirement_title": "Insurance Policy", "status": "SATISFIED", "confidence": 0.97},
            {"requirement_id": "REQ-003", "requirement_title": "Registered Address", "status": "SATISFIED", "confidence": 0.96},
            {"requirement_id": "REQ-004", "requirement_title": "Tax Good Standing", "status": "SATISFIED", "confidence": 0.99},
        ],
        "issues_snapshot": [],
        "resolved_gaps": ["GAP-001", "GAP-002"],
        "summary": "Post-remediation: 100% verified.",
    }

    run_2_id = await temp_storage.save_verification_run(project_id, run_2_data)
    assert run_2_id == "run_2"

    loaded_run_2 = await temp_storage.get_verification_run(project_id, "run_2")
    assert loaded_run_2 is not None
    assert loaded_run_2["run_number"] == 2
    assert loaded_run_2["compliance_score"] == 100.0
    assert loaded_run_2["overall_status"] == "READY"

    # 3. Verify Run 1 remained completely immutable and unchanged
    run_1_check = await temp_storage.get_verification_run(project_id, "run_1")
    assert run_1_check["compliance_score"] == 75.0
    assert run_1_check["overall_status"] == "ACTION_REQUIRED"
    assert len(run_1_check["issues_snapshot"]) == 2

    # 4. List runs returns both in order
    all_runs = await temp_storage.list_verification_runs(project_id)
    assert len(all_runs) == 2
    assert all_runs[0]["run_id"] == "run_1"
    assert all_runs[1]["run_id"] == "run_2"


def test_novatech_75_to_100_delta_calculation():
    engine = DeltaEngine()

    run_1 = {
        "run_id": "run_1",
        "run_number": 1,
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 75.0,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED"},
            {"requirement_id": "REQ-002", "requirement_title": "Insurance Certificate", "status": "MISSING"},
            {"requirement_id": "REQ-003", "requirement_title": "Office Address", "status": "CONFLICT"},
            {"requirement_id": "REQ-004", "requirement_title": "Tax Clearance", "status": "SATISFIED"},
        ],
        "issues_snapshot": [
            {"gap_id": "GAP-001", "description": "Insurance missing"},
            {"gap_id": "GAP-002", "description": "Address conflict"},
        ],
    }

    run_2 = {
        "run_id": "run_2",
        "run_number": 2,
        "overall_status": "READY",
        "compliance_score": 100.0,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "requirement_title": "Corporate Registration", "status": "SATISFIED"},
            {"requirement_id": "REQ-002", "requirement_title": "Insurance Certificate", "status": "SATISFIED"},
            {"requirement_id": "REQ-003", "requirement_title": "Office Address", "status": "SATISFIED"},
            {"requirement_id": "REQ-004", "requirement_title": "Tax Clearance", "status": "SATISFIED"},
        ],
        "issues_snapshot": [],
    }

    delta = engine.calculate_delta(run_1, run_2)

    assert delta.score_before == 75.0
    assert delta.score_after == 100.0
    assert delta.score_diff == 25.0
    assert delta.status_before == "ACTION_REQUIRED"
    assert delta.status_after == "READY"
    assert delta.resolved_count == 2
    assert delta.newly_failed_count == 0
    assert delta.unchanged_count == 2

    # Resolved list
    resolved_ids = [r.requirement_id for r in delta.resolved_requirements]
    assert "REQ-002" in resolved_ids
    assert "REQ-003" in resolved_ids

    # Unchanged list
    unchanged_ids = [r.requirement_id for r in delta.unchanged_requirements]
    assert "REQ-001" in unchanged_ids
    assert "REQ-004" in unchanged_ids

    # Resolved issues
    assert len(delta.resolved_issues) == 2


def test_delta_detects_newly_failed_requirements():
    engine = DeltaEngine()

    run_a = {
        "run_id": "run_1",
        "run_number": 1,
        "overall_status": "READY",
        "compliance_score": 100.0,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "status": "SATISFIED"},
            {"requirement_id": "REQ-002", "status": "SATISFIED"},
        ],
    }

    run_b = {
        "run_id": "run_2",
        "run_number": 2,
        "overall_status": "ACTION_REQUIRED",
        "compliance_score": 50.0,
        "matches_snapshot": [
            {"requirement_id": "REQ-001", "status": "SATISFIED"},
            {"requirement_id": "REQ-002", "status": "EXPIRED"},
        ],
    }

    delta = engine.calculate_delta(run_a, run_b)
    assert delta.newly_failed_count == 1
    assert delta.resolved_count == 0
    assert delta.score_diff == -50.0
    assert delta.newly_failed_requirements[0].requirement_id == "REQ-002"


def test_api_verification_runs_and_delta():
    # 1. Create project
    create_res = client.post("/api/projects", data={"name": "Delta API Test"})
    project_id = create_res.json()["project_id"]

    # 2. Get verification runs (empty initially)
    runs_res = client.get(f"/api/projects/{project_id}/verification-runs")
    assert runs_res.status_code == 200
    assert len(runs_res.json()["runs"]) == 0
