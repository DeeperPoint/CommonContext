# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
wiki_to_provenance.py — generate provenance sidecars for mfgllmwiki pages.

`chunk_and_embed.py` reads each document's doc-level metadata from a
`provenance/<stem>.json` sidecar (the `extracted_metadata` block: doc_type,
issuing organization, jurisdiction, material_class, process_type). For
documents converted by `convert_*.py` + `metadata_extractor.py` those sidecars
are produced automatically. The mfgllmwiki knowledge pages are *already* curated
Markdown with rich YAML frontmatter, so instead of re-extracting we map that
frontmatter straight into the sidecar shape.

Run this BEFORE embedding the wiki, so chunks carry real doc-level metadata
(material_class / jurisdiction / doc_type / process_type) for Cosolvent's
faceted `discovery.filter_fields` instead of schema defaults.

NOTE: this populates DOC-LEVEL metadata only. The per-chunk `topic` tag is a
separate LLM step in chunk_and_embed and is unaffected by provenance.

Usage:
  python wiki_to_provenance.py                       # default sibling mfgllmwiki/wiki/pages
  python wiki_to_provenance.py --pages-dir PATH      # explicit wiki pages root
  python wiki_to_provenance.py --dry-run             # print what would be written
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("[error] PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent
PROVENANCE_DIR = ROOT / "provenance"
DEFAULT_PAGES = ROOT.parent / "mfgllmwiki" / "wiki" / "pages"

# Valid reference_metadata doc_type vocabulary (schemas/manufacturing_metadata_schema.yaml).
DOC_TYPES = {
    "specification", "standard", "datasheet", "test_method", "drawing",
    "regulation", "guide", "report", "manual", "certificate", "other",
}
# Default doc_type per wiki page `type` when the page declares none of its own.
TYPE_TO_DOCTYPE = {
    "source": "report", "entity": "datasheet", "material": "specification",
    "process": "guide", "concept": "guide",
}


def frontmatter(md: Path) -> dict:
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        print(f"[warn] bad frontmatter: {md.name}", file=sys.stderr)
        return {}


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def build_record(md: Path) -> dict:
    fm = frontmatter(md)
    ptype = fm.get("type")

    # doc_type: a page's own `document_type` wins (sources carry e.g. guide/regulation),
    # else map from page `type`, else "other"; always coerced to the controlled vocab.
    doc_type = fm.get("document_type") or TYPE_TO_DOCTYPE.get(ptype, "other")
    if doc_type not in DOC_TYPES:
        doc_type = "other"

    material: dict = {}
    if fm.get("material_class"):
        material["material_class"] = fm["material_class"]
    # Our machining-process pages map to the coarse `machining` process_type.
    if ptype == "process":
        material["process_type"] = as_list(fm.get("process_type")) or ["machining"]
    elif fm.get("process_type"):
        material["process_type"] = as_list(fm.get("process_type"))

    extracted: dict = {
        "document_metadata": {
            "document_type": doc_type,
            "title": fm.get("title") or md.stem,
            "identifier": md.stem,
        },
        "geographic_scope": {"jurisdictions": as_list(fm.get("jurisdiction"))},
    }
    if fm.get("issuing_organization"):
        extracted["issuing_organization"] = {"name": fm["issuing_organization"]}
    if material:
        extracted["material"] = material

    return {
        "source_url": fm.get("source_url"),
        "source_type": "direct_import",
        "document_title": fm.get("title"),
        "output_filename": f"{md.stem}.md",
        "conversion_method": "wiki_export",
        "notes": "Generated from mfgllmwiki page frontmatter by wiki_to_provenance.py.",
        "extracted_metadata": extracted,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate provenance sidecars from wiki frontmatter.")
    ap.add_argument("--pages-dir", default=str(DEFAULT_PAGES), help="wiki pages root")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    pages = Path(args.pages_dir)
    if not pages.is_dir():
        sys.exit(f"[error] pages dir not found: {pages}")

    PROVENANCE_DIR.mkdir(exist_ok=True)
    written = 0
    for md in sorted(pages.rglob("*.md")):
        record = build_record(md)
        if args.dry_run:
            print(f"{md.stem}: {json.dumps(record['extracted_metadata'])}")
            continue
        (PROVENANCE_DIR / f"{md.stem}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written += 1

    where = "would write" if args.dry_run else "wrote"
    print(f"[ok] {where} {written or len(list(pages.rglob('*.md')))} provenance sidecars -> {PROVENANCE_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
