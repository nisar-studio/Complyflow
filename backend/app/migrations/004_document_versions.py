"""
Migration 004: Document Versioning

Adds a document_versions table to preserve immutable historical versions
of uploaded documents. The existing documents table continues to represent
the CURRENT/LATEST version only.

Schema:
  - version_id TEXT PRIMARY KEY — unique version identifier
  - project_id TEXT NOT NULL — project association
  - doc_id TEXT NOT NULL — parent document identifier
  - version_number INTEGER NOT NULL — sequential version number
  - name TEXT NOT NULL — original filename for this version
  - role TEXT NOT NULL — "requirements" or "evidence"
  - text TEXT — extracted text for this version
  - data_json TEXT — full metadata for this version
  - file_path TEXT — physical file path
  - file_hash TEXT — SHA-256 of file content
  - uploaded_by TEXT — user_id who uploaded
  - uploaded_at TEXT NOT NULL — ISO-8601 timestamp

Constraints:
  - UNIQUE(project_id, doc_id, version_number)

Indexes:
  - (project_id, doc_id) — for version listing
  - (project_id, doc_id, version_number) — for latest version lookup

This migration is additive-only. No existing data is modified or destroyed.
"""
from __future__ import annotations

import aiosqlite

MIGRATION_ID = "004"
MIGRATION_NAME = "document_versions"


async def up(db: aiosqlite.Connection) -> None:
    """Create the document_versions table."""

    # Check if table already exists (idempotent)
    try:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='document_versions'"
        ) as cursor:
            if await cursor.fetchone():
                await db.commit()
                return
    except Exception:
        pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS document_versions (
            version_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            text TEXT,
            data_json TEXT,
            file_path TEXT,
            file_hash TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL,
            UNIQUE(project_id, doc_id, version_number)
        );
    """)

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dv_proj_doc ON document_versions (project_id, doc_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dv_proj_doc_ver ON document_versions (project_id, doc_id, version_number)"
    )

    await db.commit()
