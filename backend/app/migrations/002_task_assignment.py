"""
Migration 002: Task Assignment & Due Dates

Adds assignment and due-date columns to the tasks table:
  - assigned_to (TEXT, nullable) — user_id of the assigned person
  - assigned_at (TEXT, nullable) — ISO timestamp of assignment
  - assigned_by (TEXT, nullable) — user_id of who made the assignment
  - due_date (TEXT, nullable) — ISO-8601 timestamp for deadline

Also adds indexes for efficient querying of:
  - Tasks assigned to a specific user
  - Tasks with due dates (for overdue detection)

This migration is additive-only. No existing data is modified or destroyed.
Existing tasks will have NULL values for the new columns.
"""
from __future__ import annotations

import aiosqlite

MIGRATION_ID = "002"
MIGRATION_NAME = "task_assignment"


async def up(db: aiosqlite.Connection) -> None:
    """Add assignment and due-date columns to the tasks table."""

    # Check which columns already exist (idempotent)
    existing_columns = set()
    try:
        async with db.execute("PRAGMA table_info(tasks)") as cursor:
            async for row in cursor:
                existing_columns.add(row[1])  # column name is at index 1
    except Exception:
        pass

    # Add columns only if they don't exist
    if "assigned_to" not in existing_columns:
        await db.execute("ALTER TABLE tasks ADD COLUMN assigned_to TEXT")

    if "assigned_at" not in existing_columns:
        await db.execute("ALTER TABLE tasks ADD COLUMN assigned_at TEXT")

    if "assigned_by" not in existing_columns:
        await db.execute("ALTER TABLE tasks ADD COLUMN assigned_by TEXT")

    if "due_date" not in existing_columns:
        await db.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")

    # Add indexes for efficient querying
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks (project_id, assigned_to)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks (project_id, due_date)"
    )

    await db.commit()
