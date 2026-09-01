"""
ComplyFlow — Shared Route Dependencies

Centralized service instances, helpers, and factory functions used across
multiple route modules. Imported by each domain route module and re-exported
by routes.py for backward compatibility.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.core.config import get_settings
from app.services.storage import get_storage, StorageInterface

settings = get_settings()


def _get_storage() -> StorageInterface:
    return get_storage()


def _emit_factory(project_id: str, storage: StorageInterface):
    """Returns an emit_event callback that writes to Storage AND broadcasts to SSE clients."""
    from app.services.event_broadcaster import get_broadcaster
    broadcaster = get_broadcaster()

    def emit(event: dict):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        # Non-blocking async background storage write and SSE broadcast
        loop.create_task(storage.add_event(project_id, event))
        loop.create_task(broadcaster.broadcast(project_id, event))

    return emit
