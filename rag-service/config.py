"""RAG service settings — free/local stack only (docs/STACK_DECISION_FREE.md).

All model strings are config-driven (env). No paid keys exist here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return v if v != "" else default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Ollama (local LLM + embeddings)
    ollama_host: str = field(default_factory=lambda: _get("OLLAMA_HOST", "http://localhost:11434"))
    embed_model: str = field(default_factory=lambda: _get("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    chat_model: str = field(default_factory=lambda: _get("OLLAMA_CHAT_MODEL", "llama3.1:8b"))
    embedding_backend: str = field(default_factory=lambda: _get("EMBEDDING_BACKEND", "auto"))
    # Chroma (local vectors, replaces Qdrant)
    chroma_dir: str = field(default_factory=lambda: _get("CHROMA_DIR", "./data/chroma"))
    collection: str = field(default_factory=lambda: _get("CHROMA_COLLECTION", "policies_v1"))
    # Chunking (parent ~1024 tokens / child ~256 tokens; ~4 chars/token)
    chunk_parent_tokens: int = field(default_factory=lambda: _get_int("CHUNK_PARENT_TOKENS", 1024))
    chunk_child_tokens: int = field(default_factory=lambda: _get_int("CHUNK_CHILD_TOKENS", 256))
    chunker_version: str = field(default_factory=lambda: _get("CHUNKER_VERSION", "pypdf-v1"))
    # Retrieval
    hybrid_top_k: int = field(default_factory=lambda: _get_int("HYBRID_TOP_K", 30))
    rerank_top_k: int = field(default_factory=lambda: _get_int("RERANK_TOP_K", 5))
    rerank_model: str = field(
        default_factory=lambda: _get(
            "RERANK_MODEL", "sentence-transformers/ms-marco-MiniLM-L-6-v2"
        )
    )
    rrf_k: int = field(default_factory=lambda: _get_int("RRF_K", 60))
    # Answer
    confidence_threshold: float = field(
        default_factory=lambda: _get_float("ANSWER_CONFIDENCE_THRESHOLD", 0.55)
    )
    abstain_text: str = field(
        default_factory=lambda: _get(
            "ABSTAIN_TEXT",
            "I couldn't find this in the current policies for your region/department. "
            "I've escalated this to HR — please check with them for the latest guidance.",
        )
    )
    # Cache / observability
    cache_ttl_s: int = field(default_factory=lambda: _get_int("ENTITLEMENT_CACHE_TTL_S", 300))
    redis_url: str = field(default_factory=lambda: _get("REDIS_URL", ""))
    langfuse_host: str = field(default_factory=lambda: _get("LANGFUSE_HOST", ""))
    langfuse_public_key: str = field(default_factory=lambda: _get("LANGFUSE_PUBLIC_KEY", ""))
    langfuse_secret_key: str = field(default_factory=lambda: _get("LANGFUSE_SECRET_KEY", ""))


SETTINGS = Settings()
