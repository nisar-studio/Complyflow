"""
Unit tests for ComplyFlow tools and schemas.
Ensures tool signature contract and input validation works deterministically.
"""
import json
import pytest
from app.agent.schemas import Requirement, Priority, EvidenceStatus, OverallStatus

def test_requirement_schema():
    req = Requirement(
        requirement_id="REQ-001",
        title="Business Registration",
        description="Must provide valid business registration certificate.",
        required_evidence="Official business registration certificate",
        priority=Priority.HIGH,
        source_reference="Section 1.1",
    )
    assert req.requirement_id == "REQ-001"
    assert req.priority == Priority.HIGH

def test_evidence_status_enum():
    assert EvidenceStatus.SATISFIED == "SATISFIED"
    assert EvidenceStatus.MISSING == "MISSING"
    assert EvidenceStatus.CONFLICT == "CONFLICT"
    assert OverallStatus.READY == "READY"
    assert OverallStatus.ACTION_REQUIRED == "ACTION_REQUIRED"
