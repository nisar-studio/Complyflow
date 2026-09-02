"""
Migration 005: Evidence Expiration / Lifecycle

Adds expiration metadata to document_versions and deduplication
support to notifications.

Changes:
  1. ALTER TABLE document_versions ADD COLUMN expires_at TEXT DEFAULT NULL
     - Immutable per-version expiration timestamp
     - NULL means no expiration configured
     - Assigned at version creation, never mutated

  2. ALTER TABLE notifications ADD COLUMN notification_id TEXT DEFAULT NULL
     - Deterministic identity for deduplication
     - UNIQUE INDEX prevents duplicate notifications per identity

  3. Index on document_versions(project_id, doc_id, expires_at)
     - For efficient expiration-aware queries

This migration is additive-only. No existing data is modified or destroyed.
"""
from __future__ import annotations

import aiosqlite

MIGRATION_ID = "005"
MIGRATION_NAME = "evidence_expiration"


async def up(db: aiosqlite.Connection) -> None:
    """Add expires_at to document_versions and notification_id to notifications."""

    # 1. Add expires_at to document_versions if not present
    try:
        async with db.execute("PRAGMA table_info(document_versions)") as cursor:
            columns = {row[1] async for row in cursor}
            if "expires_at" not in columns:
                await db.execute(
                    "ALTER TABLE document_versions ADD COLUMN expires_at TEXT DEFAULT NULL"
                )
    except Exception:
        pass

    # 2. Add notification_id to notifications if not present
    try:
        async with db.execute("PRAGMA table_info(notifications)") as cursor:
            columns = {row[1] async for row in cursor}
            if "notification_id" not in columns:
                await db.execute(
                    "ALTER TABLE notifications ADD COLUMN notification_id TEXT DEFAULT NULL"
                )
    except Exception:
        pass

    # 3. Index for expiration-aware queries on document_versions
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_dv_expires ON document_versions (project_id, doc_id, expires_at) WHERE expires_at IS NOT NULL"
    )

    # 4. Unique index for notification deduplication (where notification_id is set)
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_notif_dedup ON notifications (notification_id) WHERE notification_id IS NOT NULL"
    )

    await db.commit()
