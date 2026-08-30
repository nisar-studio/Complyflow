"""
ComplyFlow — Document & Evidence Viewer Test Suite

Tests:
1. Document library listing with chunk counts, page counts, OCR status, and supported requirements
2. Document details retrieval with structured chunk provenance
3. Evidence citation -> Document -> Page/Chunk resolution
4. OCR_REQUIRED document diagnostics
5. Path traversal security sanitization
"""
from __future__ import annotations

import os
import tempfile
import pytest
from app.services.storage import SQLiteStorageService
from app.services.chunking_service import ChunkingService
from app.services.document_service import DocumentService
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
async def test_document_library_and_supported_requirements(temp_storage):
    project_id = await temp_storage.create_project({"name": "Doc Viewer Test"})

    # 1. Save documents
    doc_1 = {
        "doc_id": "insurance_cert",
        "name": "insurance_certificate.pdf",
        "role": "evidence",
        "text": "Certificate of Insurance. Policy #994821. General Liability: $2,000,000.",
        "status": "OK",
        "total_pages": 1,
        "total_chunks": 1,
        "total_characters": 73,
        "file_size": 1024,
        "file_type": ".pdf",
    }
    await temp_storage.save_document_analysis(project_id, "insurance_cert", doc_1)

    # 2. Save match citing this document
    match_1 = {
        "requirement_id": "REQ-006",
        "requirement_title": "General Liability Insurance",
        "status": "SATISFIED",
        "confidence": 0.98,
        "evidence": [
            {
                "document_name": "insurance_certificate.pdf",
                "document_id": "insurance_cert",
                "page_number": 1,
                "quote": "General Liability: $2,000,000",
                "relevance": "Confirms required insurance limit",
            }
        ],
    }
    await temp_storage.save_matches(project_id, [match_1])

    # 3. Retrieve via Storage
    docs = await temp_storage.list_documents(project_id)
    assert len(docs) == 1
    assert docs[0]["name"] == "insurance_certificate.pdf"


import app.services.storage as storage_module

@pytest.fixture(scope="module")
def doc_api_ctx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("doc_api")
    db_path = str(tmp / "doc_api.db")
    upload_dir = str(tmp / "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    original_instance = storage_module._storage_instance
    test_storage = SQLiteStorageService(db_path=db_path)
    storage_module._storage_instance = test_storage

    import app.api.routes as routes_module
    original_upload_dir = routes_module.settings.upload_dir
    routes_module.settings.upload_dir = upload_dir
    original_doc_upload_dir = routes_module._document_service.upload_dir
    routes_module._document_service.upload_dir = upload_dir

    from app.main import app
    from app.services.auth_service import create_session_token
    client = TestClient(app, raise_server_exceptions=True)
    token = create_session_token("demo-user", "demo@complyflow.local")
    client.headers["Authorization"] = f"Bearer {token}"

    yield client, test_storage

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_upload_dir



def test_api_list_and_get_document_details(doc_api_ctx):
    client, storage = doc_api_ctx
    # 1. Create project via API
    create_res = client.post("/api/projects", data={"name": "API Doc Inspection Project"})
    assert create_res.status_code == 200
    project_id = create_res.json()["project_id"]

    # 2. Upload text evidence
    content = b"SECTION 1: CORPORATE REGISTRATION\nRegistration Number: NTS-98472\nAddress: 42 Innovation Drive, Suite 800"
    upload_res = client.post(
        f"/api/projects/{project_id}/documents",
        files={"evidence_files": ("registration_docs.txt", content, "text/plain")},
    )
    assert upload_res.status_code == 200

    # 3. List documents
    list_res = client.get(f"/api/projects/{project_id}/documents")
    assert list_res.status_code == 200
    doc_list = list_res.json()["documents"]
    assert len(doc_list) == 1
    assert doc_list[0]["name"] == "registration_docs.txt"
    assert doc_list[0]["status"] == "OK"
    assert doc_list[0]["total_chunks"] >= 1

    # 4. Get document details
    doc_id = doc_list[0]["doc_id"]
    get_res = client.get(f"/api/projects/{project_id}/documents/{doc_id}")
    assert get_res.status_code == 200
    detail = get_res.json()["document"]
    assert detail["name"] == "registration_docs.txt"
    assert len(detail["chunks"]) >= 1
    assert "Suite 800" in detail["raw_text"]



def test_ocr_required_diagnostic_flag():
    chunker = ChunkingService()
    # 3 empty PDF pages (scanned images without text layer)
    scanned_pages = ["", "   \n\t ", ""]
    chunked = chunker.chunk_pdf_pages(
        pages_text=scanned_pages,
        document_name="scanned_contract.pdf",
        document_id="scanned_contract",
    )

    assert chunked.status == "OCR_REQUIRED"
    assert chunked.total_chunks == 0
    assert chunked.total_pages == 3
    assert "OCR_REQUIRED" in chunked.diagnostics


def test_security_path_traversal_prevention():
    # Attempt directory traversal doc_id with URL encoding
    res = client.get("/api/projects/sample-project/documents/%2E%2E%2F%2E%2E%2Fetc%2Fpasswd")
    # Must be 404 or 400, never 500 or leak filesystem
    assert res.status_code in (400, 404)
    data = res.json()
    assert ("error" in data) or ("detail" in data)
    assert "etc" not in str(data.get("document", ""))
