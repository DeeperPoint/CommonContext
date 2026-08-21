"""One-off driver: embed the curated outputs/*.md set and export the reference-library
JSONL for the machine-market vertical."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_from_inputs import build_knowledge  # noqa: E402

OUTPUTS_DIR = Path(__file__).parent / "outputs"
EXCLUDE = {"global_machinery_marketplace_whitepaper.md"}
SCHEMA_PATH = Path(__file__).parent / "schemas" / "generated_schema.yaml"
VERTICAL = "cnc_machining_capacity"
REFS_OUT = Path(__file__).parent / "generated_refs.jsonl"

md_paths = sorted(p for p in OUTPUTS_DIR.glob("*.md") if p.name not in EXCLUDE)
ok = build_knowledge(md_paths, SCHEMA_PATH, VERTICAL, REFS_OUT)
print("build_knowledge returned:", ok)
