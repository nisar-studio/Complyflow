"""
ComplyFlow — Persistence Service (Firestore & SQLite Unified)

Backward compatibility bridge for FirestoreService.
Redirects to the unified StorageInterface provided by app.services.storage.
"""
from __future__ import annotations

from typing import Optional
from app.services.storage import get_storage, StorageInterface, SQLiteStorageService, FirestoreStorageService


def get_firestore_service(project_id: Optional[str] = None) -> StorageInterface:
    """Return the active storage service."""
    return get_storage()


# Alias for backward compatibility
FirestoreService = SQLiteStorageService
