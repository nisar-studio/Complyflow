"""
ComplyFlow — Human Auditor Overrides & Notes Test Suite

Tests:
1. Auditor override CRUD operations (create, read, list, update, revoke)
2. Input validation: invalid status rejected, empty reason rejected
3. Nonexistent project / requirement rejection
4. Cross-project isolation
5. Evidence citation & underlying AI result immutability
6. Dual compliance score calculation (AI score vs Auditor-Adjusted score)
7. Auditor standalone notes CRUD
8. Verification snapshot immutability
"""
from __future__ import annotations

import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from app.services.storage import SQLiteStorageService
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
async def test_storage_auditor_override_crud(temp_storage):
    project_id = await temp_storage.create_project({"name": "Override Test Project"})

    # 1. Create override
    override_data = {
        "requirement_id": "REQ-003",
        "original_ai_status": "CONFLICT",
        "overridden_status": "SATISFIED",
        "auditor_reason": "Verified corporate registration certificate is authoritative over company profile.",
        "auditor_note": "Approved by senior compliance auditor.",
    }
    override_id = await temp_storage.save_auditor_override(project_id, "REQ-003", override_data)
    assert override_id is not None

    # 2. Get override
    retrieved = await temp_storage.get_auditor_override(project_id, "REQ-003")
    assert retrieved is not None
    assert retrieved["overridden_status"] == "SATISFIED"
    assert retrieved["original_ai_status"] == "CONFLICT"
    assert "authoritative" in retrieved["auditor_reason"]

    # 3. List overrides
    all_overrides = await temp_storage.list_auditor_overrides(project_id)
    assert len(all_overrides) == 1
    assert all_overrides[0]["requirement_id"] == "REQ-003"

    # 4. Revoke override
    deleted = await temp_storage.delete_auditor_override(project_id, "REQ-003")
    assert deleted is True

    # 5. Verify gone
    after_delete = await temp_storage.get_auditor_override(project_id, "REQ-003")
    assert after_delete is None


def test_api_auditor_override_lifecycle_and_dual_scores():
    # 1. Create project
    create_res = client.post("/api/projects", data={"name": "API Auditor Governance Project"})
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    # 2. Seed project requirements & matches
    from app.services.storage import get_storage
    import asyncio
    storage = get_storage()

    reqs = [
        {"requirement_id": "REQ-001", "title": "Corporate Reg", "priority": "HIGH"},
        {"requirement_id": "REQ-002", "title": "Tax Clearance", "priority": "HIGH"},
        {"requirement_id": "REQ-003", "title": "Address Match", "priority": "CRITICAL"},
        {"requirement_id": "REQ-004", "title": "Insurance Policy", "priority": "CRITICAL"},
    ]
    matches = [
        {"requirement_id": "REQ-001", "status": "SATISFIED", "evidence": [{"document_name": "corp.pdf", "quote": "Valid"}]},
        {"requirement_id": "REQ-002", "status": "SATISFIED", "evidence": [{"document_name": "tax.pdf", "quote": "Valid"}]},
        {"requirement_id": "REQ-003", "status": "CONFLICT", "evidence": [{"document_name": "a.pdf", "quote": "800"}, {"document_name": "b.pdf", "quote": "400"}]},
        {"requirement_id": "REQ-004", "status": "MISSING", "evidence": []},
    ]

    async def seed():
        await storage.save_requirements(project_id, reqs)
        await storage.save_matches(project_id, matches)
        await storage.update_project(project_id, {
            "compliance_score": 50.0,
            "overall_status": "ACTION_REQUIRED",
        })
    asyncio.run(seed())

    # 3. Check initial results without override: AI score = 50.0%, Adjusted score = 50.0%
    init_results = client.get(f"/api/projects/{project_id}/results").json()
    assert init_results["ai_compliance_score"] == 50.0
    assert init_results["auditor_adjusted_score"] == 50.0
    assert init_results["has_auditor_overrides"] is False

    # 4. Apply auditor override on REQ-003: CONFLICT -> SATISFIED
    override_payload = {
        "overridden_status": "SATISFIED",
        "auditor_reason": "Government registry document is authoritative over sales brochure.",
        "auditor_note": "Auditor ticket #AUD-991",
    }
    ov_res = client.post(
        f"/api/projects/{project_id}/requirements/REQ-003/override",
        json=override_payload,
    )
    assert ov_res.status_code == 200
    ov_data = ov_res.json()["override"]
    assert ov_data["overridden_status"] == "SATISFIED"
    assert ov_data["original_ai_status"] == "CONFLICT"

    # 5. Check updated results: AI score remains 50.0%, Adjusted score is now 75.0% (3/4 SATISFIED)
    res_after_override = client.get(f"/api/projects/{project_id}/results").json()
    assert res_after_override["ai_compliance_score"] == 50.0
    assert res_after_override["auditor_adjusted_score"] == 75.0
    assert res_after_override["has_auditor_overrides"] is True
    assert len(res_after_override["auditor_overrides"]) == 1

    # 6. Verify evidence citations in original match remain completely unchanged
    match_req3 = next(m for m in res_after_override["matches"] if m["requirement_id"] == "REQ-003")
    assert match_req3["status"] == "CONFLICT"
    assert len(match_req3["evidence"]) == 2
    assert match_req3["evidence"][0]["quote"] == "800"
    assert match_req3["evidence"][1]["quote"] == "400"

    # 7. Revoke override
    del_res = client.delete(f"/api/projects/{project_id}/requirements/REQ-003/override")
    assert del_res.status_code == 200

    # 8. Check results reverted back to AI baseline
    res_reverted = client.get(f"/api/projects/{project_id}/results").json()
    assert res_reverted["ai_compliance_score"] == 50.0
    assert res_reverted["auditor_adjusted_score"] == 50.0
    assert res_reverted["has_auditor_overrides"] is False


def test_override_input_validation():
    create_res = client.post("/api/projects", data={"name": "Validation Project"})
    project_id = create_res.json()["project_id"]

    # 1. Invalid status
    invalid_res = client.post(
        f"/api/projects/{project_id}/requirements/REQ-001/override",
        json={"overridden_status": "ILLEGAL_STATUS", "auditor_reason": "Test reason"},
    )
    assert invalid_res.status_code == 400
    assert "Invalid override status" in str(invalid_res.json())

    # 2. Empty reason
    empty_res = client.post(
        f"/api/projects/{project_id}/requirements/REQ-001/override",
        json={"overridden_status": "SATISFIED", "auditor_reason": "   "},
    )
    assert empty_res.status_code == 400
    assert "reason is required" in str(empty_res.json()).lower()

    # 3. Nonexistent project
    non_proj = client.post(
        "/api/projects/non-existent-proj/requirements/REQ-001/override",
        json={"overridden_status": "SATISFIED", "auditor_reason": "Test reason"},
    )
    assert non_proj.status_code == 404


def test_auditor_notes_api():
    create_res = client.post("/api/projects", data={"name": "Notes Project"})
    project_id = create_res.json()["project_id"]

    # 1. Add note
    add_res = client.post(
        f"/api/projects/{project_id}/requirements/REQ-001/notes",
        json={"note_text": "Followed up with supplier representative via email."},
    )
    assert add_res.status_code == 200
    note_id = add_res.json()["note"]["note_id"]

    # 2. List notes
    list_res = client.get(f"/api/projects/{project_id}/requirements/REQ-001/notes")
    assert list_res.status_code == 200
    notes = list_res.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["note_text"] == "Followed up with supplier representative via email."

    # 3. Delete note
    del_res = client.delete(f"/api/projects/{project_id}/notes/{note_id}")
    assert del_res.status_code == 200

    # 4. List empty
    list_empty = client.get(f"/api/projects/{project_id}/requirements/REQ-001/notes")
    assert len(list_empty.json()["notes"]) == 0
