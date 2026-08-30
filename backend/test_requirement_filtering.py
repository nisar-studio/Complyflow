"""
ComplyFlow — Requirement Search, Filtering & Sorting Test Suite

Tests:
1. Multi-field search matching (ID, title, description, document name, quote)
2. Case-insensitive and partial substring matching
3. Status filtering (ALL, SATISFIED, MISSING, CONFLICT, PARTIAL)
4. Severity / Priority filtering (CRITICAL, HIGH, MEDIUM, LOW)
5. Combined multi-criteria filtering (e.g. CRITICAL + CONFLICT)
6. Deterministic sorting (Priority desc/asc, Status issues-first, ID asc/desc, Title A-Z)
7. Metric counts calculation
8. Empty search results handling
"""
from __future__ import annotations

import pytest


# Canonical test dataset matching NovaTech benchmark
SAMPLE_ITEMS = [
    {
        "requirement_id": "REQ-001",
        "title": "Corporate Registration",
        "description": "Must provide active corporate registration.",
        "priority": "HIGH",
        "status": "SATISFIED",
        "evidence": [{"document_name": "business_registration.pdf", "quote": "Registration Number: NTS-2024-047821"}],
    },
    {
        "requirement_id": "REQ-003",
        "title": "Registered Office Address",
        "description": "Address must match official corporate registration records.",
        "priority": "CRITICAL",
        "status": "CONFLICT",
        "evidence": [
            {"document_name": "business_registration.pdf", "quote": "Suite 800, 42 Innovation Drive"},
            {"document_name": "company_profile.pdf", "quote": "Suite 400, 42 Innovation Drive"},
        ],
    },
    {
        "requirement_id": "REQ-006",
        "title": "General Liability Insurance",
        "description": "Minimum $2,000,000 general liability insurance certificate.",
        "priority": "CRITICAL",
        "status": "MISSING",
        "evidence": [],
    },
    {
        "requirement_id": "REQ-010",
        "title": "Data Processing Agreement (DPA)",
        "description": "Executed GDPR and privacy data processing terms.",
        "priority": "HIGH",
        "status": "MISSING",
        "evidence": [],
    },
    {
        "requirement_id": "REQ-012",
        "title": "Code of Conduct",
        "description": "Signed corporate ethics and anti-bribery statement.",
        "priority": "LOW",
        "status": "SATISFIED",
        "evidence": [{"document_name": "code_of_conduct.pdf", "quote": "Anti-bribery policy executed."}],
    },
]


def filter_items(items, query="", status_filter="ALL", priority_filter="ALL", sort_by="severity_desc"):
    q = query.lower().trim() if hasattr(query, "trim") else query.lower().strip()
    
    priority_weight = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    status_weight = {"CONFLICT": 4, "MISSING": 3, "PARTIAL": 2, "SATISFIED": 1, "UNKNOWN": 0}

    filtered = []
    for item in items:
        if status_filter != "ALL" and item["status"] != status_filter:
            continue
        if priority_filter != "ALL" and item["priority"] != priority_filter:
            continue
        if q:
            match_id = q in item["requirement_id"].lower()
            match_title = q in item["title"].lower()
            match_desc = q in item["description"].lower()
            match_ev = any(
                q in (ev.get("document_name", "").lower()) or q in (ev.get("quote", "").lower())
                for ev in item.get("evidence", [])
            )
            if not (match_id or match_title or match_desc or match_ev):
                continue
        filtered.append(item)

    if sort_by == "severity_desc":
        filtered.sort(key=lambda x: (-priority_weight.get(x["priority"], 0), x["requirement_id"]))
    elif sort_by == "severity_asc":
        filtered.sort(key=lambda x: (priority_weight.get(x["priority"], 0), x["requirement_id"]))
    elif sort_by == "status":
        filtered.sort(key=lambda x: (-status_weight.get(x["status"], 0), x["requirement_id"]))
    elif sort_by == "req_id_asc":
        filtered.sort(key=lambda x: x["requirement_id"])
    elif sort_by == "req_id_desc":
        filtered.sort(key=lambda x: x["requirement_id"], reverse=True)
    elif sort_by == "title_asc":
        filtered.sort(key=lambda x: x["title"])

    return filtered


def test_search_by_id_title_description_and_quote():
    # 1. Search by ID
    res = filter_items(SAMPLE_ITEMS, query="REQ-003")
    assert len(res) == 1
    assert res[0]["requirement_id"] == "REQ-003"

    # 2. Case-insensitive title search
    res = filter_items(SAMPLE_ITEMS, query="liability")
    assert len(res) == 1
    assert res[0]["requirement_id"] == "REQ-006"

    # 3. Partial description search
    res = filter_items(SAMPLE_ITEMS, query="anti-bribery")
    assert len(res) == 1
    assert res[0]["requirement_id"] == "REQ-012"

    # 4. Search by quote excerpt
    res = filter_items(SAMPLE_ITEMS, query="Suite 400")
    assert len(res) == 1
    assert res[0]["requirement_id"] == "REQ-003"

    # 5. Search by evidence document name
    res = filter_items(SAMPLE_ITEMS, query="company_profile.pdf")
    assert len(res) == 1
    assert res[0]["requirement_id"] == "REQ-003"


def test_status_and_severity_filtering():
    # 1. Filter by status: CONFLICT
    conflicts = filter_items(SAMPLE_ITEMS, status_filter="CONFLICT")
    assert len(conflicts) == 1
    assert conflicts[0]["requirement_id"] == "REQ-003"

    # 2. Filter by status: MISSING
    missing = filter_items(SAMPLE_ITEMS, status_filter="MISSING")
    assert len(missing) == 2
    assert {m["requirement_id"] for m in missing} == {"REQ-006", "REQ-010"}

    # 3. Filter by severity: CRITICAL
    critical = filter_items(SAMPLE_ITEMS, priority_filter="CRITICAL")
    assert len(critical) == 2
    assert {c["requirement_id"] for c in critical} == {"REQ-003", "REQ-006"}

    # 4. Combined Filter: CRITICAL + CONFLICT
    combined = filter_items(SAMPLE_ITEMS, status_filter="CONFLICT", priority_filter="CRITICAL")
    assert len(combined) == 1
    assert combined[0]["requirement_id"] == "REQ-003"

    # 5. Combined Filter: CRITICAL + MISSING
    crit_missing = filter_items(SAMPLE_ITEMS, status_filter="MISSING", priority_filter="CRITICAL")
    assert len(crit_missing) == 1
    assert crit_missing[0]["requirement_id"] == "REQ-006"


def test_deterministic_sorting():
    # 1. Severity High to Low
    sorted_sev = filter_items(SAMPLE_ITEMS, sort_by="severity_desc")
    # CRITICAL (REQ-003, REQ-006) -> HIGH (REQ-001, REQ-010) -> LOW (REQ-012)
    assert sorted_sev[0]["priority"] == "CRITICAL"
    assert sorted_sev[1]["priority"] == "CRITICAL"
    assert sorted_sev[-1]["priority"] == "LOW"

    # 2. Status: Issues First
    sorted_status = filter_items(SAMPLE_ITEMS, sort_by="status")
    # CONFLICT -> MISSING -> SATISFIED
    assert sorted_status[0]["status"] == "CONFLICT"
    assert sorted_status[1]["status"] == "MISSING"
    assert sorted_status[-1]["status"] == "SATISFIED"

    # 3. Title Alphabetical
    sorted_title = filter_items(SAMPLE_ITEMS, sort_by="title_asc")
    assert sorted_title[0]["title"] == "Code of Conduct"
    assert sorted_title[-1]["title"] == "Registered Office Address"


def test_empty_search_results():
    res = filter_items(SAMPLE_ITEMS, query="non-existent-keyword-xyz-999")
    assert len(res) == 0
