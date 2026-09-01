"""
Migration 003: In-App Notifications

Adds a notifications table for persistent, user-scoped in-app notifications.

Schema:
  - notification_id TEXT PRIMARY KEY
  - user_id TEXT NOT NULL — the recipient (user-scoped, no cross-user leakage)
  - project_id TEXT — nullable; linked to a project when applicable
  - type TEXT NOT NULL — notification category (TASK_ASSIGNED, VERIFICATION_COMPLETED, etc.)
  - title TEXT NOT NULL — short human-readable title
  - message TEXT NOT NULL — detailed message body
  - is_read INTEGER NOT NULL DEFAULT 0 — unread/read state
  - metadata_json TEXT — optional structured data (task_id, run_id, etc.)
  - created_at TEXT NOT NULL — ISO-8601 timestamp

Indexes:
  - user_id + created_at — for efficient user-scoped listing
  - user_id + is_read — for unread count queries

This migration is additive-only. No existing data is modified or destroyed.
"""
from __future__ import annotations

import aiosqlite

MIGRATION_ID = "003"
MIGRATION_NAME = "notifications"


async def up(db: aiosqlite.Connection) -> None:
    """Create the notifications table."""

    # Check if table already exists (idempotent)
    try:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
        ) as cursor:
            if await cursor.fetchone():
                await db.commit()
                return
    except Exception:
        pass

    await db.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            project_id TEXT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
    """)

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_notif_user_time ON notifications (user_id, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_notif_user_read ON notifications (user_id, is_read)"
    )

    await db.commit()
