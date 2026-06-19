# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""Build a Cosolvent-ready domain schema (+ optional knowledge library) from
EVERY file in ``inputs/``.

Pipeline (CommonContext half of the cross-repo build):
  1. Convert every inputs/* file  -> outputs/<stem>.md      (convert_pdf.convertFile, fast)
  2. Synthesize ONE domain schema -> --out-schema           (LLM via OpenRouter/Claude)
  3. [only if an embedding key exists] chunk_and_embed each doc -> *_processed.jsonl,
     then export_references                                  -> --refs-out

Embeddings require a real OpenAI key (OpenRouter has no embeddings endpoint — see
Cosolvent's provider registry, openrouter.supports_embeddings=False). Without
OPENAI_API_KEY the knowledge-library track is skipped and only the schema is produced;
the Cosolvent half (configgen -> compile) still runs.

Usage:
    .venv/bin/python build_from_inputs.py
    .venv/bin/python build_from_inputs.py --out-schema schemas/generated_schema.yaml \
        --refs-out generated_refs.jsonl --model anthropic/claude-opus-4.8
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
INPUTS_DIR = HERE / "inputs"
OUTPUTS_DIR = HERE / "outputs"
PROMPT_PATH = HERE / "prompts" / "schema_synthesis.md"
DEFAULT_MODEL = "anthropic/claude-opus-4.8"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# .env locations searched for keys, in order (CommonContext, then the sibling Cosolvent repo).
_ENV_CANDIDATES = [HERE / ".env", HERE.parent / "Cosolvent" / ".env"]
_CONVERTIBLE = {".pdf", ".html", ".htm", ".csv", ".xlsx"}


def _discover_key(name: str) -> str:
    key = os.environ.get(name, "").strip()
    if key:
        return key
    for env_path in _ENV_CANDIDATES:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            key = os.environ.get(name, "").strip()
            if key:
                return key
    return ""


# ── 1. Convert every input to Markdown ───────────────────────────────────────
def _clean_outputs() -> None:
    """Remove previously-generated artifacts so outputs/ reflects only the current inputs.
    Only deletes regenerable files (.md and *_processed.jsonl); leaves anything else."""
    if not OUTPUTS_DIR.exists():
        return
    removed = 0
    for p in list(OUTPUTS_DIR.glob("*.md")) + list(OUTPUTS_DIR.glob("*_processed.jsonl")):
        p.unlink()
        removed += 1
    if removed:
        print(f"[clean] removed {removed} stale file(s) from {OUTPUTS_DIR.name}/")


def convert_all(*, full: bool, clean: bool = True) -> list[Path]:
    """Convert each convertible file in inputs/ to outputs/<stem>.md. Returns the .md paths."""
    from convert_pdf import convertFile, getOutputPath

    OUTPUTS_DIR.mkdir(exist_ok=True)
    if clean:
        _clean_outputs()
    md_paths: list[Path] = []
    inputs = sorted(p for p in INPUTS_DIR.iterdir() if p.is_file() and p.suffix.lower() in _CONVERTIBLE)
    if not inputs:
        raise SystemExit(f"No convertible files in {INPUTS_DIR} (looked for {sorted(_CONVERTIBLE)})")

    print(f"[convert] {len(inputs)} input file(s) -> Markdown ({'marker' if full else 'fast'} mode)")
    for src in inputs:
        out = getOutputPath(src, OUTPUTS_DIR)
        try:
            convertFile(src, out, fast=not full)
            if out.exists():
                md_paths.append(out)
                print(f"  ok: {src.name} -> {out.name}")
        except Exception as exc:  # one bad doc shouldn't sink the whole corpus
            print(f"  WARN: failed to convert {src.name}: {exc}", file=sys.stderr)
    if not md_paths:
        raise SystemExit("No documents converted successfully — cannot synthesize a schema.")
    return md_paths


# ── 2. Synthesize one domain schema from all the docs ────────────────────────
def _extract_yaml(text: str) -> str:
    fenced = re.search(r"```(?:yaml)?\s*(.*?)```", text, re.DOTALL)
    return (fenced.group(1) if fenced else text).strip()


def _build_documents_blob(md_paths: list[Path], *, per_doc_chars: int) -> str:
    parts = []
    for p in md_paths:
        body = p.read_text(encoding="utf-8", errors="replace")[:per_doc_chars]
        parts.append(f"=== DOCUMENT: {p.name} ===\n{body}")
    return "\n\n".join(parts)


def synthesize_schema(md_paths: list[Path], *, model: str, key: str, per_doc_chars: int) -> dict:
    """Call the LLM to produce a configgen-format schema; validate and return the parsed dict."""
    from openai import OpenAI

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    documents = _build_documents_blob(md_paths, per_doc_chars=per_doc_chars)
    user_prompt = prompt.replace("{{DOCUMENTS}}", documents)

    print(f"[schema] synthesizing from {len(md_paths)} doc(s) via {model} ...")
    client = OpenAI(api_key=key, base_url=OPENROUTER_BASE)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You output only valid YAML domain schemas."},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=8000,
        extra_headers={"HTTP-Referer": "https://deeperpoint.com", "X-Title": "CommonContext schema synthesis"},
    )
    raw = resp.choices[0].message.content or ""
    if not raw.strip():
        raise SystemExit("Schema synthesis returned an empty response.")

    schema = yaml.safe_load(_extract_yaml(raw))
    if not isinstance(schema, dict):
        raise SystemExit(f"Synthesized output was not a YAML mapping:\n{raw[:500]}")
    roles = schema.get("participant_roles") or {}
    if not (isinstance(roles, dict) and roles.get("supply") and roles.get("demand")):
        raise SystemExit(
            "Synthesized schema is missing participant_roles.supply/demand — cannot build a marketplace.\n"
            f"Got top-level keys: {list(schema.keys())}"
        )
    return schema


def write_schema(schema: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Auto-generated by build_from_inputs.py from CommonContext/inputs/.\n"
        "# Hand edits will be overwritten on the next build.\n\n"
    )
    out_path.write_text(header + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    print(f"[schema] wrote {out_path}  (vertical: {schema.get('vertical')})")


# ── 3. Optional knowledge library (needs a real embedding key) ───────────────
# chunk_and_embed only supports these tagging verticals; map the (free-form) marketplace
# vertical onto the closest one for the metadata-tagging step. The real marketplace vertical
# is still what gets stamped on the exported records (export_references --vertical).
_KNOWN_TAG_VERTICALS = ("grain", "manufacturing")


def _tag_vertical(vertical: str) -> str:
    v = vertical.lower()
    if any(t in v for t in ("machin", "manufact", "equip", "industrial")):
        return "manufacturing"
    return "grain"  # default; covers grain/agri and anything else


def build_knowledge(md_paths: list[Path], schema_path: Path, vertical: str, refs_out: Path) -> bool:
    """Embed each doc and export an ingestion file. Returns True if it ran."""
    if not _discover_key("OPENAI_API_KEY"):
        print(
            "[knowledge] SKIPPED — no OPENAI_API_KEY found. OpenRouter has no embeddings "
            "endpoint, so the knowledge library cannot be built without an OpenAI (or other "
            "embedding-capable) key. Schema + marketplace + compile still proceed.",
            file=sys.stderr,
        )
        return False

    import asyncio

    from chunk_and_embed import process_document

    tag_vertical = _tag_vertical(vertical)
    processed: list[Path] = []
    print(f"[knowledge] embedding {len(md_paths)} doc(s) (tagging vertical: {tag_vertical}) ...")
    for md in md_paths:
        try:
            asyncio.run(process_document(str(md), str(schema_path), tag_vertical))
            out = OUTPUTS_DIR / f"{md.stem}_processed.jsonl"
            if out.exists():
                processed.append(out)
        except Exception as exc:
            print(f"  WARN: embedding failed for {md.name}: {exc}", file=sys.stderr)

    if not processed:
        print("[knowledge] no chunks embedded — nothing to export.", file=sys.stderr)
        return False

    cmd = [sys.executable, str(HERE / "export_references.py"), *map(str, processed),
           "--vertical", vertical, "-o", str(refs_out)]
    subprocess.run(cmd, check=True, cwd=HERE)
    print(f"[knowledge] wrote {refs_out}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Cosolvent schema (+ knowledge) from inputs/.")
    parser.add_argument("--out-schema", default="schemas/generated_schema.yaml")
    parser.add_argument("--refs-out", default="generated_refs.jsonl")
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--vertical", help="Override the vertical slug (default: derived by the LLM)")
    parser.add_argument("--full", action="store_true", help="Use marker-pdf (ML/OCR) instead of fast extraction")
    parser.add_argument("--per-doc-chars", type=int, default=12000, help="Max chars per doc fed to the LLM")
    parser.add_argument("--skip-knowledge", action="store_true", help="Skip the embed/export step entirely")
    parser.add_argument("--keep-outputs", action="store_true",
                        help="Do NOT wipe stale .md/_processed.jsonl in outputs/ before converting")
    args = parser.parse_args(argv)

    key = _discover_key("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not found (env, CommonContext/.env, or ../Cosolvent/.env).", file=sys.stderr)
        return 1

    md_paths = convert_all(full=args.full, clean=not args.keep_outputs)
    schema = synthesize_schema(md_paths, model=args.model, key=key, per_doc_chars=args.per_doc_chars)
    if args.vertical:
        schema["vertical"] = args.vertical
    out_schema = (HERE / args.out_schema).resolve()
    write_schema(schema, out_schema)
    vertical = str(schema.get("vertical") or "marketplace")

    if not args.skip_knowledge:
        build_knowledge(md_paths, out_schema, vertical, (HERE / args.refs_out).resolve())

    # Final line is machine-readable so the Cosolvent half can pick up the paths/vertical.
    print(f"RESULT schema={out_schema} vertical={vertical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
