"""Export CommonContext embedded chunks into the Cosolvent reference-library contract.

`chunk_and_embed.py` produces ``outputs/<doc>_processed.jsonl`` with records shaped like:
    {chunk_id, content, contextual_content, metadata{...}, embedding[1536]}

Cosolvent's `load-references` loader expects the ks-to-cosolvent ingestion contract:
    {source_doc_id, vertical, chunk_text, embedding, metadata{document_type, jurisdiction, ...}}

This is the thin adapter between the two. Pure stdlib; no heavy deps.

Usage:
    python export_references.py outputs/27_2025_processed.jsonl --vertical prairie-grain
    python export_references.py outputs/*_processed.jsonl --vertical machinery_trade -o refs.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# chunk_id looks like "<doc_stem>_<index>"; strip the trailing numeric chunk index.
_CHUNK_SUFFIX = re.compile(r"_\d+$")


def _source_doc_id(record: dict[str, Any]) -> str:
    cid = str(record.get("chunk_id", "")).strip()
    return _CHUNK_SUFFIX.sub("", cid) or cid or "unknown"


def _map_metadata(meta: dict[str, Any], vertical: str) -> dict[str, Any]:
    """Normalize CommonContext chunk metadata to the contract's metadata keys,
    preserving any extra keys for richer filtering."""
    meta = dict(meta or {})
    out: dict[str, Any] = dict(meta)  # keep originals (standard, topic, etc.)
    out["vertical"] = vertical
    # Canonical contract keys, mapped from CommonContext's names where they differ.
    out["document_type"] = meta.get("document_type") or meta.get("doc_type") or "reference"
    if "jurisdiction" in meta:
        out["jurisdiction"] = meta["jurisdiction"]
    if meta.get("organization") or meta.get("standard"):
        out["organization"] = meta.get("organization") or meta.get("standard")
    if meta.get("date_issued") or meta.get("date"):
        out["date_issued"] = meta.get("date_issued") or meta.get("date")
    return out


def transform_record(record: dict[str, Any], vertical: str) -> dict[str, Any] | None:
    """One processed-chunk record -> one ingestion record. Returns None if unusable."""
    text = record.get("contextual_content") or record.get("content")
    embedding = record.get("embedding")
    if not text or not str(text).strip():
        return None
    if not isinstance(embedding, list) or not embedding:
        return None
    return {
        "source_doc_id": _source_doc_id(record),
        "vertical": vertical,
        "chunk_text": str(text),
        "embedding": embedding,
        "metadata": _map_metadata(record.get("metadata", {}), vertical),
    }


def export_files(paths: list[Path], vertical: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            mapped = transform_record(rec, vertical)
            if mapped is not None:
                out.append(mapped)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="One or more *_processed.jsonl files")
    parser.add_argument("--vertical", required=True, help="Vertical slug to stamp on every record")
    parser.add_argument("-o", "--output", help="Output JSONL path (default: stdout)")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.inputs]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"Not found: {', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 1

    records = export_files(paths, args.vertical)
    lines = "\n".join(json.dumps(r) for r in records)
    if args.output:
        Path(args.output).write_text(lines + "\n")
        print(f"✓ Wrote {len(records)} ingestion record(s) to {args.output}", file=sys.stderr)
    else:
        print(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
