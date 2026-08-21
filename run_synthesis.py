"""One-off driver: synthesize the machine-market domain schema from the curated
outputs/*.md set (excludes the pre-existing low-signal global_machinery_marketplace_whitepaper.md)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_from_inputs import _discover_key, synthesize_schema, write_schema  # noqa: E402

OUTPUTS_DIR = Path(__file__).parent / "outputs"
EXCLUDE = {"global_machinery_marketplace_whitepaper.md"}

md_paths = sorted(p for p in OUTPUTS_DIR.glob("*.md") if p.name not in EXCLUDE)
print(f"Synthesizing from {len(md_paths)} docs:")
for p in md_paths:
    print(" -", p.name)

key = _discover_key("OPENROUTER_API_KEY")
if not key:
    raise SystemExit("No OPENROUTER_API_KEY found")

schema = synthesize_schema(md_paths, model="anthropic/claude-opus-4.8", key=key, per_doc_chars=12000)
write_schema(schema, Path("schemas/generated_schema.yaml"))
