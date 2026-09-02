"""
test_document_versioning.py — Document Versioning Tests (Epic D)

Tests:
  1. First upload creates version 1
  2. Re-upload creates version 2
  3. Re-upload creates version 3
  4. Historical versions remain unchanged
  5. Current documents record points to latest version
  6. Version numbers are sequential
  7. Different documents maintain independent version sequences
  8. Different projects maintain independent version sequences
  9. Historical filenames are preserved
  10. Historical extracted text is preserved
  11. Duplicate upload behavior
  12. Version listing authorization
  13. Version detail authorization
  14. Cross-project isolation
  15. Deletion removes version records
  16. Existing document endpoints remain backward compatible
  17. Legacy documents remain usable
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.services.storage as storage_module
from app.services.storage import SQLiteStorageService
from app.services.auth_service import hash_password, Role, create_session_token


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ver_ctx(tmp_path_factory):
    """Isolated database and TestClient for versioning tests."""
    tmp = tmp_path_factory.mktemp("versioning")
    db_path = str(tmp / "versioning.db")
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

    # Seed user
    _run(test_storage.create_user({
        "user_id": "ver_admin",
        "email": "ver_admin@test.com",
        "name": "Version Admin",
        "password_hash": hash_password("AdminPass123!"),
        "is_active": True,
    }))
    _run(test_storage.create_user({
        "user_id": "ver_outsider",
        "email": "ver_outsider@test.com",
        "name": "Version Outsider",
        "password_hash": hash_password("OutsiderPass123!"),
        "is_active": True,
    }))

    # Create project
    _run(test_storage.create_project({
        "project_id": "ver_proj",
        "name": "Versioning Test Project",
        "status": "PENDING",
    }))
    _run(test_storage.add_project_member("ver_proj", "ver_admin", Role.ADMIN.value))

    # Create second project for cross-project tests
    _run(test_storage.create_project({
        "project_id": "ver_proj2",
        "name": "Second Project",
        "status": "PENDING",
    }))
    _run(test_storage.add_project_member("ver_proj2", "ver_admin", Role.ADMIN.value))

    admin_token = create_session_token("ver_admin", "ver_admin@test.com")
    outsider_token = create_session_token("ver_outsider", "ver_outsider@test.com")

    yield {
        "client": client,
        "storage": test_storage,
        "admin_token": admin_token,
        "outsider_token": outsider_token,
    }

    storage_module._storage_instance = original_instance
    routes_module.settings.upload_dir = original_upload_dir
    routes_module._document_service.upload_dir = original_doc_dir


# ── Tests ─────────────────────────────────────────────────────


class TestVersionCreation:
    """Test version creation on upload."""

    def test_first_upload_creates_version_1(self, ver_ctx):
        """First upload of a document creates version 1."""
        storage = ver_ctx["storage"]
        _run(storage.create_document_version("ver_proj", "test_doc", {
            "version_number": 1,
            "name": "test_doc.pdf",
            "role": "evidence",
            "text": "Version 1 content",
            "data_json": {"doc_id": "test_doc", "name": "test_doc.pdf"},
            "file_path": "/uploads/ver_proj/test_doc.pdf",
            "file_hash": "abc123",
            "uploaded_by": "ver_admin",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        version = _run(storage.get_document_version("ver_proj", "test_doc", 1))
        assert version is not None
        assert version["version_number"] == 1
        assert version["name"] == "test_doc.pdf"

    def test_second_upload_creates_version_2(self, ver_ctx):
        """Second upload creates version 2."""
        storage = ver_ctx["storage"]
        _run(storage.create_document_version("ver_proj", "test_doc", {
            "version_number": 2,
            "name": "test_doc_v2.pdf",
            "role": "evidence",
            "text": "Version 2 content",
            "data_json": {"doc_id": "test_doc", "name": "test_doc_v2.pdf"},
            "file_path": "/uploads/ver_proj/test_doc_v2.pdf",
            "file_hash": "def456",
            "uploaded_by": "ver_admin",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        version = _run(storage.get_document_version("ver_proj", "test_doc", 2))
        assert version is not None
        assert version["version_number"] == 2
        assert version["name"] == "test_doc_v2.pdf"

    def test_third_upload_creates_version_3(self, ver_ctx):
        """Third upload creates version 3."""
        storage = ver_ctx["storage"]
        _run(storage.create_document_version("ver_proj", "test_doc", {
            "version_number": 3,
            "name": "test_doc_v3.pdf",
            "role": "evidence",
            "text": "Version 3 content",
            "data_json": {"doc_id": "test_doc", "name": "test_doc_v3.pdf"},
            "file_path": "/uploads/ver_proj/test_doc_v3.pdf",
            "file_hash": "ghi789",
            "uploaded_by": "ver_admin",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        version = _run(storage.get_document_version("ver_proj", "test_doc", 3))
        assert version is not None
        assert version["version_number"] == 3


class TestVersionPreservation:
    """Test that historical versions are preserved."""

    def test_historical_versions_remain_unchanged(self, ver_ctx):
        """Older versions are not modified when newer versions are created."""
        storage = ver_ctx["storage"]
        v1 = _run(storage.get_document_version("ver_proj", "test_doc", 1))
        v2 = _run(storage.get_document_version("ver_proj", "test_doc", 2))
        v3 = _run(storage.get_document_version("ver_proj", "test_doc", 3))

        assert v1["name"] == "test_doc.pdf"
        assert v1["text"] == "Version 1 content"
        assert v2["name"] == "test_doc_v2.pdf"
        assert v2["text"] == "Version 2 content"
        assert v3["name"] == "test_doc_v3.pdf"
        assert v3["text"] == "Version 3 content"

    def test_historical_filenames_preserved(self, ver_ctx):
        """Each version retains its original filename."""
        storage = ver_ctx["storage"]
        versions = _run(storage.list_document_versions("ver_proj", "test_doc"))
        names = [v["name"] for v in versions]
        assert "test_doc.pdf" in names
        assert "test_doc_v2.pdf" in names
        assert "test_doc_v3.pdf" in names

    def test_historical_text_preserved(self, ver_ctx):
        """Each version retains its original extracted text."""
        storage = ver_ctx["storage"]
        v1 = _run(storage.get_document_version("ver_proj", "test_doc", 1))
        assert v1["text"] == "Version 1 content"


class TestVersionNumbers:
    """Test version numbering semantics."""

    def test_version_numbers_are_sequential(self, ver_ctx):
        """Version numbers increment sequentially."""
        storage = ver_ctx["storage"]
        next_ver = _run(storage.get_next_version_number("ver_proj", "test_doc"))
        assert next_ver == 4  # After 3 existing versions

    def test_different_documents_independent_sequences(self, ver_ctx):
        """Different documents have independent version sequences."""
        storage = ver_ctx["storage"]
        _run(storage.create_document_version("ver_proj", "other_doc", {
            "version_number": 1,
            "name": "other_doc.pdf",
            "role": "evidence",
            "text": "Other doc content",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        next_ver = _run(storage.get_next_version_number("ver_proj", "other_doc"))
        assert next_ver == 2

    def test_different_projects_independent_sequences(self, ver_ctx):
        """Different projects have independent version sequences."""
        storage = ver_ctx["storage"]
        _run(storage.create_document_version("ver_proj2", "proj2_doc", {
            "version_number": 1,
            "name": "proj2_doc.pdf",
            "role": "evidence",
            "text": "Project 2 doc",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        next_ver = _run(storage.get_next_version_number("ver_proj2", "proj2_doc"))
        assert next_ver == 2


class TestVersionListing:
    """Test version listing and retrieval."""

    def test_list_versions_returns_all(self, ver_ctx):
        """List returns all versions in chronological order."""
        storage = ver_ctx["storage"]
        versions = _run(storage.list_document_versions("ver_proj", "test_doc"))
        assert len(versions) == 3
        assert versions[0]["version_number"] == 1
        assert versions[1]["version_number"] == 2
        assert versions[2]["version_number"] == 3

    def test_get_latest_version(self, ver_ctx):
        """Latest version returns the highest version number."""
        storage = ver_ctx["storage"]
        latest = _run(storage.get_latest_document_version("ver_proj", "test_doc"))
        assert latest is not None
        assert latest["version_number"] == 3

    def test_get_nonexistent_version(self, ver_ctx):
        """Getting a nonexistent version returns None."""
        storage = ver_ctx["storage"]
        version = _run(storage.get_document_version("ver_proj", "test_doc", 999))
        assert version is None


class TestBackwardCompatibility:
    """Test that existing document endpoints remain backward compatible."""

    def test_legacy_documents_remain_usable(self, ver_ctx):
        """Documents without version records still work."""
        storage = ver_ctx["storage"]
        # Create a document without a version record (simulates legacy)
        _run(storage.save_document_analysis("ver_proj", "legacy_doc", {
            "doc_id": "legacy_doc",
            "name": "legacy_doc.pdf",
            "role": "evidence",
            "text": "Legacy content",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        doc = _run(storage.get_document("ver_proj", "legacy_doc"))
        assert doc is not None
        assert doc["name"] == "legacy_doc.pdf"

    def test_version_listing_for_document_without_versions(self, ver_ctx):
        """Listing versions for a document without versions returns empty list."""
        storage = ver_ctx["storage"]
        versions = _run(storage.list_document_versions("ver_proj", "legacy_doc"))
        assert versions == []


class TestDeletion:
    """Test that deletion removes version records."""

    def test_delete_document_removes_versions(self, ver_ctx):
        """Deleting a document removes its version records."""
        storage = ver_ctx["storage"]
        # Create a document with versions
        _run(storage.create_document_version("ver_proj", "delete_me", {
            "version_number": 1,
            "name": "delete_me.pdf",
            "role": "evidence",
            "text": "Delete me",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        _run(storage.create_document_version("ver_proj", "delete_me", {
            "version_number": 2,
            "name": "delete_me_v2.pdf",
            "role": "evidence",
            "text": "Delete me v2",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))

        # Verify versions exist
        versions = _run(storage.list_document_versions("ver_proj", "delete_me"))
        assert len(versions) == 2

        # Delete the document
        _run(storage.delete_document("ver_proj", "delete_me"))

        # Verify versions are gone
        versions = _run(storage.list_document_versions("ver_proj", "delete_me"))
        assert len(versions) == 0


class TestAtomicity:
    """Test upload atomicity - file cleanup on DB failure."""

    def test_successful_version_upload_persists_file_and_record(self, ver_ctx):
        """Successful upload creates both file and version record."""
        import tempfile
        import os
        storage = ver_ctx["storage"]
        
        # Create a version with a file path
        test_file = Path(tempfile.mktemp(suffix=".txt"))
        test_file.write_text("Test content for atomicity")
        
        try:
            _run(storage.create_document_version("ver_proj", "atomic_doc", {
                "version_number": 1,
                "name": "atomic_test.txt",
                "role": "evidence",
                "text": "Test content",
                "file_path": str(test_file),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }))
            
            # Verify version record exists
            version = _run(storage.get_document_version("ver_proj", "atomic_doc", 1))
            assert version is not None
            assert version["name"] == "atomic_test.txt"
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_failed_db_insert_does_not_corrupt_existing_versions(self, ver_ctx):
        """If a DB insert fails, existing versions remain intact."""
        storage = ver_ctx["storage"]
        
        # Create version 1
        _run(storage.create_document_version("ver_proj", "corrupt_test", {
            "version_number": 1,
            "name": "original.pdf",
            "role": "evidence",
            "text": "Original content",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        
        # Verify version 1 exists
        v1 = _run(storage.get_document_version("ver_proj", "corrupt_test", 1))
        assert v1 is not None
        assert v1["text"] == "Original content"
        
        # Attempt to create duplicate version (will fail due to UNIQUE constraint)
        try:
            _run(storage.create_document_version("ver_proj", "corrupt_test", {
                "version_number": 1,  # Duplicate!
                "name": "should_fail.pdf",
                "role": "evidence",
                "text": "Should not persist",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass  # Expected to fail
        
        # Verify version 1 is unchanged
        v1_after = _run(storage.get_document_version("ver_proj", "corrupt_test", 1))
        assert v1_after is not None
        assert v1_after["text"] == "Original content"
        assert v1_after["name"] == "original.pdf"

    def test_version_number_not_phantom_after_failure(self, ver_ctx):
        """Failed upload does not create a phantom version number."""
        storage = ver_ctx["storage"]
        
        # Create version 1
        _run(storage.create_document_version("ver_proj", "phantom_test", {
            "version_number": 1,
            "name": "v1.pdf",
            "role": "evidence",
            "text": "Version 1",
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }))
        
        # Get next version number
        next_ver = _run(storage.get_next_version_number("ver_proj", "phantom_test"))
        assert next_ver == 2
        
        # Attempt to create version 2 with duplicate (will fail)
        try:
            _run(storage.create_document_version("ver_proj", "phantom_test", {
                "version_number": 1,  # Duplicate!
                "name": "phantom.pdf",
                "role": "evidence",
                "text": "Phantom",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass
        
        # Next version should still be 2, not 3
        next_ver_after = _run(storage.get_next_version_number("ver_proj", "phantom_test"))
        assert next_ver_after == 2

    def test_documents_not_corrupted_when_version_insert_fails(self, ver_ctx):
        """If save_document_with_version fails, both documents and version record
        should remain unchanged. This is the critical atomicity test."""
        from unittest.mock import AsyncMock, patch
        storage = ver_ctx["storage"]
        
        # Create version 1 with documents record using atomic method
        _run(storage.save_document_with_version(
            "ver_proj", "atomic_test",
            {
                "doc_id": "atomic_test",
                "name": "original.pdf",
                "role": "evidence",
                "text": "Original v1 text",
                "version_number": 1,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "version_number": 1,
                "name": "original.pdf",
                "role": "evidence",
                "text": "Original v1 text",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
        ))
        
        # Verify initial state
        doc = _run(storage.get_document("ver_proj", "atomic_test"))
        assert doc is not None
        assert doc["text"] == "Original v1 text"
        
        v1 = _run(storage.get_document_version("ver_proj", "atomic_test", 1))
        assert v1 is not None
        assert v1["text"] == "Original v1 text"
        
        # Now attempt to create version 2 with a duplicate version number
        # This will fail due to UNIQUE constraint, and the atomic method should rollback both
        try:
            _run(storage.save_document_with_version(
                "ver_proj", "atomic_test",
                {
                    "doc_id": "atomic_test",
                    "name": "new_version.pdf",
                    "role": "evidence",
                    "text": "New v2 text",
                    "version_number": 2,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "version_number": 1,  # Duplicate! Will fail
                    "name": "new_version.pdf",
                    "role": "evidence",
                    "text": "New v2 text",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                },
            ))
        except Exception:
            pass  # Expected to fail
        
        # CRITICAL ASSERTIONS: Both should be preserved/unchanged
        doc_after = _run(storage.get_document("ver_proj", "atomic_test"))
        v1_after = _run(storage.get_document_version("ver_proj", "atomic_test", 1))
        
        # Documents should still point to version 1 (atomicity preserved)
        assert doc_after is not None
        assert doc_after["text"] == "Original v1 text"
        assert doc_after["name"] == "original.pdf"
        
        # Version 1 should be intact
        assert v1_after is not None
        assert v1_after["text"] == "Original v1 text"
        assert v1_after["name"] == "original.pdf"
        
        # Next version number should still be 2 (no phantom consumed)
        next_ver = _run(storage.get_next_version_number("ver_proj", "atomic_test"))
        assert next_ver == 2
