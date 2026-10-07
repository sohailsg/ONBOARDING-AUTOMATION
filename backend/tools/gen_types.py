"""W2 OpenAPI -> TypeScript codegen (02-impl task 2.5).

Reads backend/openapi.yaml (or a live openapi.json) and emits TS types for
every component schema + a typed endpoint map consumed by 06 frontend.
Falls back to the W0 stub shapes if PyYAML is unavailable.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

STUB = (
    "// AUTO-GENERATED (W0 stub) from backend/openapi.yaml — real types land in W2.\n"
    "export type CaseStatus = 'pending_ingestion' | 'agent_processing' | 'awaiting_hr_approval' | 'executing' | 'needs_attention' | 'active';\n"
    "export interface TraceEvent { ts: string; step: string; message: string; case_id: string; session_id: string }\n"
)


def _to_ts_type(schema: dict, name: str = "") -> str:
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    t = schema.get("type", "object")
    if t == "string":
        if schema.get("enum"):
            return " | ".join(f"'{e}'" for e in schema["enum"])
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        inner = _to_ts_type(schema.get("items", {}), name)
        return f"{inner}[]"
    if t == "object":
        props = schema.get("properties", {})
        if not props:
            return "Record<string, unknown>"
        lines = []
        required = set(schema.get("required", []))
        for key, sub in props.items():
            opt = "" if key in required else "?"
            lines.append(f"  {key}{opt}: {_to_ts_type(sub, key)};")
        return "{\n" + "\n".join(lines) + "\n}"
    return "unknown"


def generate(spec: dict) -> str:
    out = ["// AUTO-GENERATED from backend/openapi.yaml — do not edit. Regenerate: make gen-api"]
    schemas = (spec.get("components", {}) or {}).get("schemas", {}) or {}
    for name, schema in schemas.items():
        out.append(f"export type {name} = {_to_ts_type(schema, name)};")
    out.append("\nexport const ApiRoutes = {")
    for path, methods in (spec.get("paths", {}) or {}).items():
        for method, op in (methods or {}).items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId", re.sub(r"\W+", "_", f"{method}_{path}"))
            out.append(f"  {op_id}: '{path}',")
    out.append("};")
    return "\n".join(out) + "\n"


def _load_spec(path: pathlib.Path) -> dict | None:
    text = path.read_text()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        pass
    if path.suffix == ".json":
        return json.loads(text)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate TS types from openapi spec (W2)")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    spec_path = pathlib.Path(args.spec)
    out = pathlib.Path(args.out)
    if not spec_path.exists():
        print(f"gen_types: spec not found: {spec_path}")
        return 1
    spec = _load_spec(spec_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if spec is None:
        out.write_text(STUB)
        print(f"gen_types: PyYAML unavailable or unparsable YAML — wrote stub {out}")
        return 0
    out.write_text(generate(spec))
    print(f"gen_types: wrote {out} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
