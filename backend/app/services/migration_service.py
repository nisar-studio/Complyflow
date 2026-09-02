"""
ComplyFlow — Database Migration Framework

Provides deterministic, idempotent schema migration for SQLite.
Tracks applied migrations in a schema_migrations table.
Supports fresh databases, existing v1.0.0 databases, and already-migrated databases.

Usage:
    from app.services.migration_service import run_pending_migrations, get_migration_status
    await run_pending_migrations(db_path)
    status = await get_migration_status(db_path)
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import logging
import os
import pkgutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

logger = logging.getLogger("complyflow.migrations")


def _compute_checksum(code: str) -> str:
    """Compute a SHA-256 checksum of migration source code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


# ── Migration Registry ─────────────────────────────────────────
# Migrations are imported in order. Each module must expose:
#   MIGRATION_ID: str   — e.g. "001"
#   MIGRATION_NAME: str — e.g. "initial_schema"
#   async def up(db: aiosqlite.Connection) -> None

_MIGRATION_MODULES: List[str] = [
    "app.migrations.001_initial_schema",
    "app.migrations.002_task_assignment",
    "app.migrations.003_notifications",
    "app.migrations.004_document_versions",
    "app.migrations.005_evidence_expiration",
]


def _load_migration(module_path: str) -> Dict[str, Any]:
    """Import a migration module and extract its metadata."""
    mod = importlib.import_module(module_path)
    source = inspect.getsource(mod)
    return {
        "id": mod.MIGRATION_ID,
        "name": mod.MIGRATION_NAME,
        "module_path": module_path,
        "up": mod.up,
        "checksum": _compute_checksum(source),
    }


def _get_all_migrations() -> List[Dict[str, Any]]:
    """Load all registered migrations in order."""
    migrations = []
    for module_path in _MIGRATION_MODULES:
        try:
            migrations.append(_load_migration(module_path))
        except Exception as exc:
            logger.error(f"Failed to load migration {module_path}: {exc}")
            raise
    return migrations


# ── Schema Management ──────────────────────────────────────────

async def _ensure_migrations_table(db: aiosqlite.Connection) -> None:
    """Create the schema_migrations table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL
        )
    """)
    await db.commit()


async def _get_applied_migrations(db: aiosqlite.Connection) -> Dict[str, str]:
    """Return a dict of {migration_id: checksum} for all applied migrations."""
    applied = {}
    try:
        async with db.execute(
            "SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id"
        ) as cursor:
            async for row in cursor:
                applied[row[0]] = row[1]
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        pass
    return applied


async def _record_migration(
    db: aiosqlite.Connection,
    migration_id: str,
    name: str,
    checksum: str,
) -> None:
    """Record a successfully applied migration."""
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO schema_migrations (migration_id, name, applied_at, checksum) VALUES (?, ?, ?, ?)",
        (migration_id, name, now, checksum),
    )
    await db.commit()


# ── Public API ─────────────────────────────────────────────────

async def run_pending_migrations(db_path: str) -> List[str]:
    """
    Run all pending migrations against the given database.

    Returns a list of migration IDs that were applied.
    Raises on failure — does NOT mark a failed migration as applied.
    """
    all_migrations = _get_all_migrations()
    applied_ids: List[str] = []

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=5000;")
        await _ensure_migrations_table(db)
        applied = await _get_applied_migrations(db)

        for migration in all_migrations:
            mid = migration["id"]
            if mid in applied:
                # Verify checksum hasn't changed (safety check)
                stored_checksum = applied[mid]
                if stored_checksum != migration["checksum"]:
                    logger.warning(
                        f"Migration {mid} checksum mismatch! "
                        f"Stored: {stored_checksum}, Current: {migration['checksum']}. "
                        f"Migration was already applied with different code."
                    )
                continue

            logger.info(f"Applying migration {mid}: {migration['name']}...")
            try:
                await migration["up"](db)
                await _record_migration(db, mid, migration["name"], migration["checksum"])
                applied_ids.append(mid)
                logger.info(f"Migration {mid} applied successfully.")
            except Exception as exc:
                logger.error(f"Migration {mid} FAILED: {exc}")
                raise

    return applied_ids


async def get_migration_status(db_path: str) -> Dict[str, Any]:
    """
    Get the current migration status.

    Returns:
        {
            "applied": [{"id": "001", "name": "...", "applied_at": "...", "checksum": "..."}],
            "pending": [{"id": "002", "name": "...", "checksum": "..."}],
            "total": int,
            "applied_count": int,
            "pending_count": int,
        }
    """
    all_migrations = _get_all_migrations()

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await _ensure_migrations_table(db)
        applied = await _get_applied_migrations(db)

        # Get full applied info
        applied_details = []
        try:
            async with db.execute(
                "SELECT migration_id, name, applied_at, checksum FROM schema_migrations ORDER BY migration_id"
            ) as cursor:
                async for row in cursor:
                    applied_details.append({
                        "id": row[0],
                        "name": row[1],
                        "applied_at": row[2],
                        "checksum": row[3],
                    })
        except sqlite3.OperationalError:
            pass

        # Determine pending
        pending = []
        for m in all_migrations:
            if m["id"] not in applied:
                pending.append({
                    "id": m["id"],
                    "name": m["name"],
                    "checksum": m["checksum"],
                })

    return {
        "applied": applied_details,
        "pending": pending,
        "total": len(all_migrations),
        "applied_count": len(applied_details),
        "pending_count": len(pending),
    }


async def verify_migration_integrity(db_path: str) -> List[str]:
    """
    Verify that all applied migrations have matching checksums.
    Returns a list of warnings for any mismatches.
    """
    all_migrations = {m["id"]: m for m in _get_all_migrations()}
    warnings = []

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await _ensure_migrations_table(db)
        try:
            async with db.execute(
                "SELECT migration_id, name, checksum FROM schema_migrations ORDER BY migration_id"
            ) as cursor:
                async for row in cursor:
                    mid, name, stored_checksum = row[0], row[1], row[2]
                    if mid in all_migrations:
                        current_checksum = all_migrations[mid]["checksum"]
                        if stored_checksum != current_checksum:
                            warnings.append(
                                f"Migration {mid} ({name}): checksum mismatch "
                                f"(stored={stored_checksum}, current={current_checksum})"
                            )
                    else:
                        warnings.append(
                            f"Migration {mid} ({name}): applied but not in registry"
                        )
        except sqlite3.OperationalError:
            pass

    return warnings
