"""Seed the local Chroma index from ``rag-service/seeds/manifest.json``.

Usage (from repo root ``onboarding/``):
  CHROMA_DIR=./data/chroma python rag-service/scripts/seed_index.py [--pdf|--txt]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(HERE, "..", "seeds", "manifest.json"))
    ap.add_argument("--ext", default="pdf", choices=["pdf", "txt"])
    args = ap.parse_args()

    from ingest import ingest_many

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    seed_dir = os.path.dirname(args.manifest)
    specs = [
        {
            "path": os.path.join(seed_dir, m[args.ext]),
            "doc_id": m["doc_id"],
            "region": m["region"],
            "department": m["department"],
            "effective_date": m["effective_date"],
            "version": m["version"],
        }
        for m in manifest
    ]
    for row in ingest_many(specs):
        print(row)


if __name__ == "__main__":
    main()
