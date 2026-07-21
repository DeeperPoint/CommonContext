# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""wiki_ingest.py — Fold converted documents (outputs/*.md) into the LLM Wiki.

The wiki (wiki/) is a persistent, LLM-maintained, interlinked markdown knowledge base that
sits between the raw sources and the artifacts CommonContext produces. Unlike the raw
chunk-and-embed path, ingest *accumulates* knowledge: each source is integrated into the
existing pages, cross-references and contradictions maintained by the model.

Model: Sonnet 5 via OpenRouter (override with WIKI_MODEL / --model). The OpenRouter client and
key-discovery mirror build_from_inputs.py.

Pipeline per document:
  1. Read wiki/CONVENTIONS.md + current wiki state (index + pages, bounded).
  2. Ask the model for a JSON set of page edits (prompts/wiki_ingest.md).
  3. Apply edits (write pages with frontmatter), rebuild index.md, append to log.md.

Usage:
    .venv/bin/python wiki_ingest.py                      # ingest ALL outputs/*.md
    .venv/bin/python wiki_ingest.py outputs/foo.md       # ingest one document
    .venv/bin/python wiki_ingest.py --schema schemas/grain_trade_schema.yaml
    .venv/bin/python wiki_ingest.py --dry-run            # show planned edits, write nothing
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
OUTPUTS_DIR = HERE / "outputs"
WIKI_DIR = HERE / "wiki"
CONVENTIONS_PATH = WIKI_DIR / "CONVENTIONS.md"
INDEX_PATH = WIKI_DIR / "index.md"
LOG_PATH = WIKI_DIR / "log.md"
PROMPT_PATH = HERE / "prompts" / "wiki_ingest.md"

DEFAULT_MODEL = os.environ.get("WIKI_MODEL", "anthropic/claude-sonnet-5")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# .env locations searched for keys, in order (CommonContext, then the sibling Cosolvent repo).
_ENV_CANDIDATES = [HERE / ".env", HERE.parent / "Cosolvent" / ".env"]

# Rough context budget for the current wiki state fed back to the model (chars).
WIKI_STATE_BUDGET = 40_000
# Max chars of the new document fed to the model.
DOC_CHAR_BUDGET = 40_000

REQUIRED_FRONTMATTER = ("title", "type", "summary")


# ── Key discovery (mirrors build_from_inputs.py) ─────────────────────────────
def _discover_key(name: str = "OPENROUTER_API_KEY") -> str:
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


# ── Frontmatter helpers ──────────────────────────────────────────────────────
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Empty dict if no frontmatter block."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), m.group(2)


def render_page(fields: dict, body: str) -> str:
    fm = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


# ── Provenance & staleness support ───────────────────────────────────────────
# Provenance tags classify how grounded each part of a page is:
#   W = source-backed (traceable to an ingested document)
#   D = demo-invented (a placeholder for a demo, not a real fact)
#   I = interpretive  (synthesis/bridging beyond what a source states)
# The tags make the wiki honest: a page leaning D/I without sign-off is flagged
# by the linter. source_hashes records the content hash of each source at ingest
# so the linter can detect when a page has drifted from its sources (staleness).
_PROVENANCE_TAGS = {"W", "D", "I"}
_STATUSES = {"draft", "reviewed", "signed_off"}


def _sha256_file(path: Path) -> str | None:
    """SHA-256 of a file's bytes, or None if it does not exist."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(sources: list) -> dict:
    """Record the content hash of each source's ``outputs/<stem>.md`` at ingest.

    The linter recomputes these and flags a page as stale when a source file has
    changed since the page was last written.
    """
    out: dict[str, str] = {}
    for stem in sources or []:
        h = _sha256_file(OUTPUTS_DIR / f"{stem}.md")
        if h:
            out[str(stem)] = h
    return out


def normalize_provenance(raw, *, has_sources: bool) -> list:
    """Coerce model-supplied provenance into a list of ``{section, tag}`` entries.

    Tags outside W/D/I are dropped. If nothing valid remains, default to a single
    page-level entry: W when the page cites sources, else I.
    """
    out: list[dict] = []
    for item in raw or []:
        if isinstance(item, dict):
            tag = str(item.get("tag", "")).upper()[:1]
            if tag in _PROVENANCE_TAGS:
                out.append({"section": str(item.get("section") or "page"), "tag": tag})
    if not out:
        out = [{"section": "page", "tag": "W" if has_sources else "I"}]
    return out


def _iter_pages() -> list[Path]:
    """All wiki content pages (markdown with frontmatter), excluding meta/generated files."""
    skip = {CONVENTIONS_PATH, INDEX_PATH, LOG_PATH, WIKI_DIR / "lint-report.md"}
    return sorted(p for p in WIKI_DIR.rglob("*.md") if p not in skip)


# ── Build the model context ──────────────────────────────────────────────────
def _load_schema_hint(schema_path: Path | None) -> str:
    if not schema_path or not schema_path.exists():
        return ""
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    roles = schema.get("participant_roles") or {}
    vertical = schema.get("vertical") or schema.get("domain") or "the marketplace"
    role_names = sorted({str(k) for k in roles}) if isinstance(roles, dict) else []
    lines = [f"### Domain hint\nVertical: **{vertical}**."]
    if role_names:
        lines.append(f"Participant role groups from the domain schema: {', '.join(role_names)}.")
    lines.append(
        "Prefer typed folders that reflect this domain's entity classes; keep page types "
        "consistent with the conventions."
    )
    return "\n".join(lines)


def _build_wiki_state(budget: int = WIKI_STATE_BUDGET) -> str:
    pages = _iter_pages()
    if not pages:
        return "(the wiki is empty — you are creating the first pages)"
    parts: list[str] = []
    used = 0
    for p in pages:
        rel = p.relative_to(WIKI_DIR).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        block = f"=== PAGE: {rel} ===\n{text}"
        if used + len(block) > budget:
            # Past the budget: include just the path + summary so the model still knows it exists.
            fm, _ = parse_frontmatter(text)
            summary = fm.get("summary", "")
            block = f"=== PAGE: {rel} (summary only) ===\n{summary}"
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _build_prompt(doc_stem: str, document: str, schema_path: Path | None) -> str:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
    return (
        prompt.replace("{{CONVENTIONS}}", conventions)
        .replace("{{SCHEMA_HINT}}", _load_schema_hint(schema_path))
        .replace("{{WIKI_STATE}}", _build_wiki_state())
        .replace("{{DOC_STEM}}", doc_stem)
        .replace("{{DOCUMENT}}", document[:DOC_CHAR_BUDGET])
    )


# ── Model call ────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = (fenced.group(1) if fenced else text).strip()
    # Fall back to the outermost {...} if there is stray prose around it.
    if not candidate.startswith("{"):
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        if brace:
            candidate = brace.group(0)
    return candidate


def call_model(prompt: str, *, model: str, key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=OPENROUTER_BASE)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You output only valid JSON wiki page-edit sets."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8000,
        extra_headers={"HTTP-Referer": "https://deeperpoint.com", "X-Title": "CommonContext wiki ingest"},
    )
    raw = resp.choices[0].message.content or ""
    if not raw.strip():
        raise SystemExit("Wiki ingest returned an empty response.")
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Model did not return valid JSON: {exc}\n{raw[:800]}")
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise SystemExit(f"Ingest JSON missing a 'pages' list:\n{raw[:800]}")
    return data


# ── Apply edits ────────────────────────────────────────────────────────────────
def _safe_rel_path(path: str) -> Path:
    """Resolve a model-supplied page path safely under wiki/ (no traversal)."""
    rel = Path(path.strip().lstrip("/"))
    if rel.suffix != ".md":
        rel = rel.with_suffix(".md")
    dest = (WIKI_DIR / rel).resolve()
    if WIKI_DIR.resolve() not in dest.parents and dest != WIKI_DIR.resolve():
        raise ValueError(f"page path escapes wiki/: {path}")
    return dest


def _merge_sources(existing_path: Path, new_sources: list) -> list:
    merged = {str(s) for s in (new_sources or [])}
    if existing_path.exists():
        fm, _ = parse_frontmatter(existing_path.read_text(encoding="utf-8"))
        for s in fm.get("sources") or []:
            merged.add(str(s))
    return sorted(merged)


def apply_pages(data: dict, *, today: str, dry_run: bool) -> list[str]:
    written: list[str] = []
    for page in data["pages"]:
        try:
            dest = _safe_rel_path(page["path"])
        except (KeyError, ValueError) as exc:
            print(f"  WARN: skipping page ({exc})", file=sys.stderr)
            continue
        body = page.get("body", "").strip()
        if not body:
            print(f"  WARN: skipping {page.get('path')} — empty body", file=sys.stderr)
            continue
        merged_sources = _merge_sources(dest, page.get("sources") or [])
        status = page.get("status") if page.get("status") in _STATUSES else "draft"
        fields = {
            "title": page.get("title") or dest.stem.replace("-", " ").title(),
            "type": page.get("type") or dest.parent.name.rstrip("s") or "entity",
            "summary": page.get("summary") or "",
            "sources": merged_sources,
            "provenance": normalize_provenance(page.get("provenance"), has_sources=bool(merged_sources)),
            "status": status,
            "source_hashes": source_hashes(merged_sources),
            "updated": today,
        }
        rel = dest.relative_to(WIKI_DIR).as_posix()
        action = "update" if dest.exists() else "create"
        written.append(f"{action}: {rel}")
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render_page(fields, body), encoding="utf-8")
    return written


def rebuild_index() -> None:
    """Regenerate index.md deterministically from every page's frontmatter."""
    by_type: dict[str, list[tuple[str, str, str]]] = {}
    for p in _iter_pages():
        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        rel = p.relative_to(WIKI_DIR).as_posix()
        ptype = str(fm.get("type") or p.parent.name or "misc")
        title = str(fm.get("title") or p.stem)
        summary = str(fm.get("summary") or "")
        by_type.setdefault(ptype, []).append((title, rel, summary))

    lines = [
        "# Wiki Index",
        "",
        "> Auto-generated catalog of every wiki page, grouped by type. Rebuilt on each ingest — do not edit by hand.",
        "",
    ]
    if not by_type:
        lines.append("_No pages yet. Run `python wiki_ingest.py` to populate the wiki from `outputs/*.md`._")
    for ptype in sorted(by_type):
        lines.append(f"## {ptype}")
        lines.append("")
        for title, rel, summary in sorted(by_type[ptype]):
            tail = f" — {summary}" if summary else ""
            lines.append(f"- [{title}]({rel}){tail}")
        lines.append("")
    INDEX_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_log(entry: str, *, today: str, doc_stem: str) -> None:
    line = f"\n## [{today}] ingest | {doc_stem}\n{entry.strip()}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)


# ── Orchestration ───────────────────────────────────────────────────────────
def ingest_document(md_path: Path, *, model: str, key: str, schema_path: Path | None,
                    today: str, dry_run: bool) -> bool:
    doc_stem = md_path.stem
    document = md_path.read_text(encoding="utf-8", errors="replace")
    print(f"[ingest] {md_path.name} via {model} ...")
    prompt = _build_prompt(doc_stem, document, schema_path)
    data = call_model(prompt, model=model, key=key)
    written = apply_pages(data, today=today, dry_run=dry_run)
    for w in written:
        print(f"  {w}")
    if not written:
        print("  (no page edits)")
        return False
    if not dry_run:
        rebuild_index()
        append_log(data.get("log_entry", f"ingested {doc_stem}"), today=today, doc_stem=doc_stem)
    return True


def _resolve_targets(args_paths: list[str]) -> list[Path]:
    if args_paths:
        paths = [Path(p) if Path(p).is_absolute() else (HERE / p) for p in args_paths]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise SystemExit(f"file(s) not found: {', '.join(str(m) for m in missing)}")
        return paths
    if not OUTPUTS_DIR.exists():
        raise SystemExit(f"No outputs/ directory at {OUTPUTS_DIR} — run the converter first.")
    docs = sorted(p for p in OUTPUTS_DIR.glob("*.md"))
    if not docs:
        raise SystemExit(f"No *.md files in {OUTPUTS_DIR} — run the converter first.")
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fold documents into the LLM Wiki.")
    parser.add_argument("paths", nargs="*", help="Specific outputs/*.md to ingest (default: all).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter model (default {DEFAULT_MODEL}).")
    parser.add_argument("--schema", help="Domain schema YAML to hint the page taxonomy.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned edits; write nothing.")
    args = parser.parse_args(argv)

    if not CONVENTIONS_PATH.exists():
        raise SystemExit(f"Missing {CONVENTIONS_PATH} — scaffold the wiki first.")

    key = _discover_key()
    if not key:
        raise SystemExit("OPENROUTER_API_KEY not found (env, CommonContext/.env, or ../Cosolvent/.env).")

    schema_path = (Path(args.schema) if Path(args.schema).is_absolute() else HERE / args.schema) if args.schema else None
    today = _dt.date.today().isoformat()
    targets = _resolve_targets(args.paths)

    print(f"[wiki] ingesting {len(targets)} document(s){' (dry-run)' if args.dry_run else ''}")
    changed = 0
    for md in targets:
        try:
            if ingest_document(md, model=args.model, key=key, schema_path=schema_path,
                               today=today, dry_run=args.dry_run):
                changed += 1
        except SystemExit:
            raise
        except Exception as exc:  # one bad doc shouldn't sink the batch
            print(f"  WARN: ingest failed for {md.name}: {exc}", file=sys.stderr)

    print(f"[wiki] done — {changed}/{len(targets)} document(s) changed the wiki.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
