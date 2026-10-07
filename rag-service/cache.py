"""Entitlement cache (task 3.6): TTL cache keyed by ``(role, region)``.

Backed by Redis when ``REDIS_URL`` is set, else process-local dict.
Only caches small entitlement-lookup payloads — never policy text.
"""
from __future__ import annotations

import json
import os
import time

_local: dict[str, tuple[float, str]] = {}


def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, socket_timeout=2)
    except Exception:
        return None


def _ttl() -> int:
    try:
        return int(os.getenv("ENTITLEMENT_CACHE_TTL_S", "300"))
    except Exception:
        return 300


def get(role: str, region: str):
    key = f"ent:{role}:{region}"
    r = _redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    item = _local.get(key)
    if item and item[0] > time.time():
        return json.loads(item[1])
    return None


def put(role: str, region: str, value) -> None:
    key = f"ent:{role}:{region}"
    raw = json.dumps(value)
    r = _redis()
    if r is not None:
        try:
            r.setex(key, _ttl(), raw)
            return
        except Exception:
            pass
    _local[key] = (time.time() + _ttl(), raw)


def invalidate(role: str = "", region: str = "") -> int:
    if role or region:
        _local.pop(f"ent:{role}:{region}", None)
        return 1
    n = len(_local)
    _local.clear()
    return n
