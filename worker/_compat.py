"""Import compat: worker runs under two roots.

- `pytest` from `onboarding/`      -> `backend.app...`, `worker...`
- `pytest` from repo root (`crewai_pjt/`) -> `onboarding.backend.app...`
  (namespace packages, no `onboarding/__init__.py`).

This helper resolves `backend.app.*` under either root so worker code
and tests stay green in both layouts.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def backend_mod(name: str) -> ModuleType:
    for prefix in ("backend.app", "onboarding.backend.app"):
        try:
            return importlib.import_module(f"{prefix}.{name}")
        except ImportError:
            continue
    raise ImportError(f"cannot import backend.app.{name} under any known root")
