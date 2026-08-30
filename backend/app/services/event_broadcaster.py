"""
ComplyFlow — Robust Multi-Subscriber SSE Event Broadcaster

Manages per-project SSE subscribers with automatic cleanup on client disconnect,
broadcasts agent lifecycle events to multiple simultaneous clients,
and prevents memory leaks.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("complyflow.events")


class EventBroadcaster:
    """Thread-safe, leak-free multi-subscriber SSE broadcaster for agent events."""

    def __init__(self, max_queue_size: int = 100):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self, project_id: str) -> asyncio.Queue:
        """Subscribe a new client to project events."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = set()
            self._subscribers[project_id].add(queue)
        return queue

    async def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber and clean up empty project mappings."""
        async with self._lock:
            if project_id in self._subscribers:
                self._subscribers[project_id].discard(queue)
                if not self._subscribers[project_id]:
                    del self._subscribers[project_id]

    async def broadcast(self, project_id: str, event: Dict[str, Any]) -> int:
        """
        Broadcast an event to all active subscribers for the project.
        Returns the number of subscribers reached.
        """
        async with self._lock:
            queues = list(self._subscribers.get(project_id, set()))

        sent_count = 0
        for queue in queues:
            try:
                if queue.full():
                    # Evict oldest event if queue is full to prevent blocking
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(event)
                sent_count += 1
            except Exception as e:
                logger.debug(f"Failed to push event to queue for project {project_id}: {e}")

        return sent_count

    async def get_active_subscriber_count(self, project_id: str) -> int:
        """Return the number of active SSE subscribers for a project."""
        async with self._lock:
            return len(self._subscribers.get(project_id, set()))

    async def get_total_tracked_projects(self) -> int:
        """Return the number of projects with active subscribers."""
        async with self._lock:
            return len(self._subscribers)


# Global singleton instance
_broadcaster_instance: Optional[EventBroadcaster] = None


def get_broadcaster() -> EventBroadcaster:
    global _broadcaster_instance
    if _broadcaster_instance is None:
        _broadcaster_instance = EventBroadcaster()
    return _broadcaster_instance
