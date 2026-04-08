"""In-memory SSE subscriber registry (per-process)."""
import asyncio
from collections import defaultdict
from typing import Dict, List

_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)


def subscribe(project_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[project_id].append(q)
    return q


def unsubscribe(project_id: str, q: asyncio.Queue) -> None:
    try:
        _subscribers[project_id].remove(q)
    except ValueError:
        pass


async def broadcast(project_id: str, event: dict) -> None:
    for q in list(_subscribers.get(project_id, [])):
        await q.put(event)
