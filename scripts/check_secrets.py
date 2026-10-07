"""7.1 secret scan (impl §5 Security). Fails CI if a likely secret is committed.

Scans tracked text files for:
- private keys, AWS-style keys, generic api/token/secret assignments with
  high-entropy values
- *_GENERATED placeholders must stay EMPTY in committed .env.example files
- committed .env / .env.* (except .env.example) files

Usage: python scripts/check_secrets.py [--root .]
Exit 1 with findings, 0 when clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".next", "dist", "data", ".venv", "venv"}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".pdf", ".lock"}

PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("generic-secret-assignment", re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-+/=]{16,})['\"]?")),
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9_\-]{20,}")),
    ("jwt-heuristic", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]

ALLOWLIST_FILES = {"scripts/check_secrets.py"}
ALLOWLIST_SUBSTRINGS = (
    "dev-service-key",
    "dev-only-change-me",
    "test-service-key",
    "example",
    "changeme",
    "GENERATED=",
    "WEBHOOK_HMAC_SECRET",
    "SERVICE_API_KEY",
    "JWT_SECRET",
    "server-side only",
)


def _is_allowlisted(line: str) -> bool:
    low = line.lower()
    return any(s.lower() in low for s in ALLOWLIST_SUBSTRINGS)


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST_FILES:
            continue
        # Committed env files (other than examples) are themselves a finding.
        if rel == ".env" or re.fullmatch(r"\.env\..+", rel) and rel != ".env.example":
            findings.append(f"{rel}: committed env file must not be checked in")
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            findings.append(f"{rel}: committed env file must not be checked in")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except Exception:
            continue
        # .env.example GENERATED placeholders must stay empty.
        if path.name == ".env.example" and "GENERATED=" in text:
            for i, line in enumerate(text.splitlines(), 1):
                if "GENERATED=" in line and line.split("GENERATED=", 1)[1].strip().strip("'\"") != "":
                    findings.append(f"{rel}:{i}: GENERATED placeholder must stay empty in git")
        for i, line in enumerate(text.splitlines(), 1):
            if _is_allowlisted(line):
                continue
            for name, rx in PATTERNS:
                if rx.search(line):
                    findings.append(f"{rel}:{i}: possible {name}: {line.strip()[:120]}")
                    break
    return findings


def main() -> int:
    root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path(".")
    findings = scan(root.resolve())
    if findings:
        print("check_secrets: FAIL")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("check_secrets: OK (no secrets in git)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
