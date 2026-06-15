"""Event-Bus fuer SSE (Server-Sent Events).

Wird von Routers (projekt + task) befuellt und von main.py
fuer den SSE-Endpoint konsumiert. Separate Datei um circular
imports zu vermeiden.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any

# In-Memory Event-Bus (pro project_id) — wird von Routers befuellt
_event_queues: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish_event(project_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Veroeffentlicht ein Event an alle Listener dieses Projekts."""
    if not project_id:
        return
    event = {
        "type": event_type,
        "ts": datetime.utcnow().isoformat(),
        "project_id": project_id,
        "data": data,
    }
    for q in list(_event_queues.get(project_id, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def subscribe(project_id: str) -> asyncio.Queue:
    """Erzeugt eine neue Queue fuer einen SSE-Listener."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_queues[project_id].append(queue)
    return queue


def unsubscribe(project_id: str, queue: asyncio.Queue) -> None:
    """Entfernt eine Queue (Cleanup bei SSE-Disconnect)."""
    try:
        _event_queues[project_id].remove(queue)
    except (ValueError, KeyError):
        pass
