"""Export the live gateway OpenAPI to backend/openapi.yaml (02-impl task 2.5).

Regenerate after any route/spec change so `make gen-api` types stay in sync:
    python onboarding/backend/tools/export_openapi.py
    python onboarding/backend/tools/gen_types.py \
        --spec onboarding/backend/openapi.yaml \
        --out onboarding/frontend/lib/api.types.ts
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import yaml  # noqa: E402

from onboarding.backend.app.main import create_app  # noqa: E402
from onboarding.backend.app.schemas import TraceEvent  # noqa: E402


def main() -> int:
    app = create_app()
    spec = app.openapi()
    spec.setdefault("servers", []).insert(0, {"url": "http://localhost:8000"})
    # TraceEvent is the SSE (text/event-stream) contract: no JSON endpoint
    # returns it, so FastAPI omits it — inject explicitly for frontend types.
    spec.setdefault("components", {}).setdefault("schemas", {})["TraceEvent"] = TraceEvent.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    out = pathlib.Path("onboarding/backend/openapi.yaml")
    out.write_text(
        "# AUTO-GENERATED from the live gateway (W2) — do not hand-edit.\n"
        "# Regenerate: python onboarding/backend/tools/export_openapi.py\n"
        + yaml.safe_dump(spec, sort_keys=True, default_flow_style=False),
    )
    print(f"export_openapi: wrote {out} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
