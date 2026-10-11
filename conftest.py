"""Root conftest: deterministic import roots for the monorepo.

- ``onboarding/`` (this dir): `backend.*`, `db.*`, `worker.*` top-level imports.
- Its parent: `onboarding.backend.*` namespace imports used by gateway tests.

Previously this only worked by accident (a hardening test patched sys.path
at collection time, so backend suites failed standalone). Centralizing here
makes every subset (`pytest backend/tests`, etc.) importable on its own.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for _p in (_HERE, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
