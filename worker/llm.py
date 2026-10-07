"""LLM factory (CrewAI API-drift isolation). Model string env-configured."""

from __future__ import annotations


def get_llm():
    """Return a CrewAI LLM bound to the configured Ollama chat model.

    Wrapper isolates the CrewAI/litellm upgrade surface (impl §7 risk:
    pin crewai, wrap client). Raises RuntimeError if CrewAI is unavailable.
    """
    from .config import get_worker_settings

    settings = get_worker_settings()
    try:
        from crewai import LLM
    except Exception as exc:  # pragma: no cover - import surface
        raise RuntimeError(f"crewai LLM unavailable: {exc}") from exc
    return LLM(
        model=f"ollama/{settings.chat_model}",
        base_url=settings.ollama_host,
        temperature=0.1,
    )


def llm_info() -> dict:
    from .config import get_worker_settings

    s = get_worker_settings()
    return {"provider": "ollama", "model": s.chat_model, "host": s.ollama_host}
