"""Embeddings: Ollama (local, free) with deterministic hash fallback.

``EmbeddingBackend.embed(["a","b"]) -> [[float...], ...]``

Backend selection via ``EMBEDDING_BACKEND``: ``ollama`` | ``hash`` | ``auto``
(auto = try Ollama, fall back to hash on connection failure — used by CI
and unit tests so no server is required).
"""
from __future__ import annotations

import hashlib
import math
import os

import httpx

DIM_HASH = 384


def _hash_embed(text: str, dim: int = DIM_HASH) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class OllamaEmbeddingBackend:
    def __init__(self, host: str, model: str, timeout_s: float = 30.0) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with httpx.Client(timeout=self.timeout_s) as client:
            for t in texts:
                r = client.post(
                    f"{self.host}/api/embeddings", json={"model": self.model, "prompt": t}
                )
                r.raise_for_status()
                data = r.json()
                vec = data.get("embedding") or data.get("embeddings", [[]])[0]
                out.append([float(x) for x in vec])
        return out


class HashEmbeddingBackend:
    def __init__(self, dim: int = DIM_HASH) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embed(t, self.dim) for t in texts]


def get_backend(kind: str = "", host: str = "", model: str = ""):
    kind = (kind or os.getenv("EMBEDDING_BACKEND", "auto")).lower()
    host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    if kind == "ollama":
        return OllamaEmbeddingBackend(host, model)
    if kind == "hash":
        return HashEmbeddingBackend()
    # auto: probe quickly; fall back to hash
    try:
        with httpx.Client(timeout=3.0) as c:
            c.get(f"{host.rstrip('/')}/api/tags").raise_for_status()
        probe = OllamaEmbeddingBackend(host, model, timeout_s=30.0)
        probe.embed(["ok"])
        return probe
    except Exception:
        return HashEmbeddingBackend()


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    denom = math.sqrt(sum(x * x for x in a[:n])) * math.sqrt(sum(x * x for x in b[:n]))
    if not denom:
        return 0.0
    return sum(x * y for x, y in zip(a[:n], b[:n])) / denom
