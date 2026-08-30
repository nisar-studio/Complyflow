"""
ComplyFlow — Storage Test Suite

Tests SQLiteStorageService functionality, persistence, and parity with StorageInterface.
Uses temporary isolated SQLite databases for clean test runs.
"""
from __future__ import annotations

import os
import tempfile
import pytest
from app.services.storage import SQLiteStorageService


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    
    storage = SQLiteStorageService(db_path=temp_path)
    yield storage

    # Cleanup
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_project_crud(temp_storage):
    # 1. Create project
    proj_data = {
        "name": "Acme Vendor Review",
        "status": "PENDING",
        "compliance_score": None,
        "requirements_count": 5,
    }
    project_id = await temp_storage.create_project(proj_data)
    assert project_id is not None
    assert len(project_id) > 0

    # 2. Get project
    proj = await temp_storage.get_project(project_id)
    assert proj is not None
    assert proj["name"] == "Acme Vendor Review"
    assert proj["status"] == "PENDING"
    assert proj["requirements_count"] == 5

    # 3. Update project
    await temp_storage.update_project(project_id, {
        "status": "READY",
        "compliance_score": 100.0,
        "overall_status": "READY",
    })
    updated = await temp_storage.get_project(project_id)
    assert updated["status"] == "READY"
    assert updated["compliance_score"] == 100.0
    assert updated["overall_status"] == "READY"

    # 4. List projects
    projects = await temp_storage.list_projects()
    assert len(projects) == 1
    assert projects[0]["project_id"] == project_id


@pytest.mark.asyncio
async def test_requirements_storage(temp_storage):
    proj_id = await temp_storage.create_project({"name": "Req Test"})

    requirements = [
        {
            "requirement_id": "REQ-001",
            "title": "Business License",
            "description": "Valid business license required",
            "required_evidence": "Business license PDF",
            "priority": "HIGH",
            "source_reference": "Section 1",
        },
        {
            "requirement_id": "REQ-002",
            "title": "Insurance Policy",
            "description": "General liability insurance",
            "required_evidence": "Insurance certificate",
            "priority": "CRITICAL",
            "source_reference": "Section 2",
        },
    ]

    await temp_storage.save_requirements(proj_id, requirements)
    loaded = await temp_storage.get_requirements(proj_id)
    assert len(loaded) == 2
    assert loaded[0]["requirement_id"] == "REQ-001"
    assert loaded[1]["requirement_id"] == "REQ-002"
    assert loaded[1]["priority"] == "CRITICAL"


@pytest.mark.asyncio
async def test_document_storage(temp_storage):
    proj_id = await temp_storage.create_project({"name": "Doc Test"})

    doc1 = {
        "doc_id": "req_doc",
        "name": "requirements.pdf",
        "role": "requirements",
        "text": "Checklist: 1. License, 2. Insurance",
    }
    doc2 = {
        "doc_id": "license_cert",
        "name": "license.pdf",
        "role": "evidence",
        "text": "Acme Inc License #12345 Valid until 2026",
    }

    await temp_storage.save_document_analysis(proj_id, "req_doc", doc1)
    await temp_storage.save_document_analysis(proj_id, "license_cert", doc2)

    # Get single
    loaded_doc = await temp_storage.get_document(proj_id, "license_cert")
    assert loaded_doc is not None
    assert loaded_doc["name"] == "license.pdf"
    assert "Acme Inc" in loaded_doc["text"]

    # List evidence only
    evidence_docs = await temp_storage.list_documents(proj_id, role="evidence")
    assert len(evidence_docs) == 1
    assert evidence_docs[0]["name"] == "license.pdf"

    # List all
    all_docs = await temp_storage.list_documents(proj_id)
    assert len(all_docs) == 2


@pytest.mark.asyncio
async def test_matches_issues_and_tasks(temp_storage):
    proj_id = await temp_storage.create_project({"name": "Matches Test"})

    # Matches
    matches = [
        {
            "requirement_id": "REQ-001",
            "requirement_title": "Business License",
            "status": "SATISFIED",
            "confidence": 0.95,
            "evidence_references": ["license.pdf"],
            "reasoning": "Valid license found.",
        },
        {
            "requirement_id": "REQ-002",
            "requirement_title": "Insurance Policy",
            "status": "MISSING",
            "confidence": 1.0,
            "evidence_references": [],
            "reasoning": "No insurance document uploaded.",
        },
    ]
    await temp_storage.save_matches(proj_id, matches)
    loaded_matches = await temp_storage.get_matches(proj_id)
    assert len(loaded_matches) == 2
    assert loaded_matches[0]["status"] == "SATISFIED"

    # Issues
    issues = [
        {
            "gap_id": "GAP-001",
            "gap_type": "missing_evidence",
            "severity": "CRITICAL",
            "description": "Insurance policy missing",
        }
    ]
    await temp_storage.save_issues(proj_id, issues)
    loaded_issues = await temp_storage.get_issues(proj_id)
    assert len(loaded_issues) == 1
    assert loaded_issues[0]["severity"] == "CRITICAL"

    # Tasks
    tasks = [
        {
            "task_id": "TASK-001",
            "title": "Upload Insurance Policy",
            "severity": "CRITICAL",
            "required_action": "upload_document",
            "status": "OPEN",
        }
    ]
    await temp_storage.save_tasks(proj_id, tasks)
    loaded_tasks = await temp_storage.get_tasks(proj_id)
    assert len(loaded_tasks) == 1
    assert loaded_tasks[0]["status"] == "OPEN"

    # Update task status
    await temp_storage.update_task_status(proj_id, "TASK-001", "RESOLVED")
    updated_tasks = await temp_storage.get_tasks(proj_id)
    assert updated_tasks[0]["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_events_and_verification_runs(temp_storage):
    proj_id = await temp_storage.create_project({"name": "Events Test"})

    # Events
    event1 = {
        "project_id": proj_id,
        "type": "AGENT_STARTED",
        "tool": None,
        "status": "started",
        "summary": "Agent started",
    }
    event2 = {
        "project_id": proj_id,
        "type": "TOOL_COMPLETED",
        "tool": "extract_requirements",
        "status": "completed",
        "summary": "Extracted 2 requirements",
    }
    await temp_storage.add_event(proj_id, event1)
    await temp_storage.add_event(proj_id, event2)

    events = await temp_storage.get_events(proj_id)
    assert len(events) == 2
    assert events[0]["type"] == "AGENT_STARTED"
    assert events[1]["tool"] == "extract_requirements"

    # Verification run
    verif = {
        "overall_status": "READY",
        "compliance_score": 100.0,
        "satisfied_count": 2,
        "total_count": 2,
        "summary": "All requirements verified.",
    }
    run_id = await temp_storage.save_verification_run(proj_id, verif)
    assert run_id is not None

    latest_verif = await temp_storage.get_latest_verification(proj_id)
    assert latest_verif is not None
    assert latest_verif["overall_status"] == "READY"
    assert latest_verif["compliance_score"] == 100.0

    # Consolidated results
    results = await temp_storage.get_results(proj_id)
    assert results is not None
    assert results["project"]["project_id"] == proj_id
    assert results["latest_verification"]["overall_status"] == "READY"
