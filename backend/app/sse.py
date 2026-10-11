"""In-memory fallback + redis pub/sub fan-out for trace:{session_id} (sse.py)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def publish(session_id: str, step: str, message: str, case_id: str = "") -> dict:
    """Publish to in-memory bus AND redis (best-effort). Returns the event dict."""
    event = {"ts": _now(), "step": step, "message": message, "case_id": case_id, "session_id": session_id}
    for q in list(_subscribers.get(session_id, set())):
        await q.put(event)
    try:
        from .config import get_settings

        settings = get_settings()
        if settings.REDIS_URL:
            import json

            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.REDIS_URL)
            try:
                await client.publish(f"trace:{session_id}", json.dumps(event))
            finally:
                await client.aclose()
    except Exception:
        pass  # redis optional in dev/tests; in-memory bus is source for SSE
    return event


def subscribe_queue(session_id: str) -> tuple[asyncio.Queue[Any], Callable[[], None]]:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[session_id].add(q)

    def _unsub() -> None:
        _subscribers[session_id].discard(q)

    return q, _unsub


async def redis_listener(session_id: str, queue: asyncio.Queue) -> None:
    """Bridge redis pub/sub into the in-memory queue. No-op if redis unavailable."""
    try:
        from .config import get_settings

        settings = get_settings()
        import json

        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"trace:{session_id}")
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    await queue.put(json.loads(msg["data"]))
                except Exception:
                    continue
        finally:
            await pubsub.unsubscribe(f"trace:{session_id}")
            await client.aclose()
    except Exception:
        return


async def event_stream(session_id: str) -> AsyncIterator[dict]:
    """Infinite live-event iterator. No timeout here (callers add heartbeats
    with wait_for around queue.get(), never around __anext__)."""
    q, unsub = subscribe_queue(session_id)
    bridge = asyncio.create_task(redis_listener(session_id, q))
    try:
        while True:
            yield await q.get()
    finally:
        unsub()
        bridge.cancel()


def reset_bus() -> None:
    _subscribers.clear()
