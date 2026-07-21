# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""wiki_lint.py — Health-check the LLM Wiki (the pattern's "lint" operation).

Two layers:
  1. Structural (deterministic, no LLM): build the [[wikilink]] graph and report
     ORPHAN pages (no inbound links) and BROKEN links (target page missing).
  2. Editorial (LLM, Sonnet 5): contradictions, stale claims, coverage gaps — returned
     as a JSON report. Coverage/missing findings can be emitted as pull-signals into the
     Cosolvent knowledge_gap_signals table via the existing gap_signal.emit_gap_signal.

Writes wiki/lint-report.md and appends a line to wiki/log.md.

Usage:
    .venv/bin/python wiki_lint.py                 # structural + editorial report
    .venv/bin/python wiki_lint.py --structural    # structural only (no LLM, no key needed)
    .venv/bin/python wiki_lint.py --emit-signals \
        --dsn postgresql://postgres:postgres@localhost:15432/cosolvent
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Reuse the ingest module's helpers so conventions stay in one place.
import wiki_ingest  # module handle so OUTPUTS_DIR / hashing stay in sync (and are patchable in tests)
from wiki_ingest import (  # type: ignore
    CONVENTIONS_PATH,
    LOG_PATH,
    WIKI_DIR,
    WIKI_STATE_BUDGET,
    _build_wiki_state,
    _discover_key,
    _extract_json,
    _iter_pages,
    parse_frontmatter,
)

HERE = Path(__file__).resolve().parent
LINT_PROMPT_PATH = HERE / "prompts" / "wiki_lint.md"
REPORT_PATH = WIKI_DIR / "lint-report.md"
DEFAULT_MODEL = os.environ.get("WIKI_MODEL", "anthropic/claude-sonnet-5")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


# ── Structural checks (no LLM) ────────────────────────────────────────────────
def _page_key(path: Path) -> str:
    """The [[wikilink]] target key for a page: its stem (filename without .md)."""
    return path.stem


def structural_report() -> dict:
    pages = _iter_pages()
    keys = {_page_key(p) for p in pages}
    inbound: dict[str, int] = {k: 0 for k in keys}
    broken: list[tuple[str, str]] = []  # (source page rel, missing target)

    for p in pages:
        _, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        rel = p.relative_to(WIKI_DIR).as_posix()
        for raw in _WIKILINK_RE.findall(body):
            target = raw.split("|")[0].strip()          # allow [[target|alias]]
            target_key = Path(target).stem               # tolerate folder/target forms
            if target_key in inbound:
                if target_key != _page_key(p):           # ignore self-links
                    inbound[target_key] += 1
            else:
                broken.append((rel, target))

    # sources/ pages and the top-level overview are orphans by design — don't flag them.
    _exempt = {"overview", "index"}
    orphans = sorted(
        p.relative_to(WIKI_DIR).as_posix()
        for p in pages
        if inbound.get(_page_key(p), 0) == 0
        and p.parent.name != "sources"
        and p.stem not in _exempt
    )
    return {"page_count": len(pages), "orphans": orphans, "broken_links": broken}


# ── Provenance honesty gate (no LLM) ─────────────────────────────────────────
def tag_mix(provenance) -> dict:
    """Count a page's provenance entries by W/D/I tag."""
    mix = {"W": 0, "D": 0, "I": 0}
    for item in provenance or []:
        if isinstance(item, dict):
            tag = str(item.get("tag", "")).upper()[:1]
            if tag in mix:
                mix[tag] += 1
    return mix


def page_is_honest(fm: dict) -> bool:
    """A page is honest if signed off, or its provenance is majority source-backed.

    Declaring no provenance at all is not honest — every page must own its tags.
    """
    if fm.get("status") == "signed_off":
        return True
    prov = fm.get("provenance")
    if not prov:
        return False
    mix = tag_mix(prov)
    total = mix["W"] + mix["D"] + mix["I"]
    if total == 0:
        return False
    return mix["W"] >= (mix["D"] + mix["I"])


def provenance_report() -> dict:
    """Flag pages missing provenance, or majority demo/interpretive without sign-off."""
    violations: list[tuple[str, str]] = []
    checked = 0
    for p in _iter_pages():
        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        rel = p.relative_to(WIKI_DIR).as_posix()
        checked += 1
        if not fm.get("provenance"):
            violations.append((rel, "no provenance declared (add W/D/I tags)"))
        elif not page_is_honest(fm):
            m = tag_mix(fm.get("provenance"))
            violations.append(
                (rel, f"majority demo/interpretive without sign-off (W/D/I={m['W']}/{m['D']}/{m['I']})")
            )
    return {"checked": checked, "violations": violations}


# ── Staleness (deterministic, hash-based) ────────────────────────────────────
def staleness_report() -> dict:
    """Flag pages whose recorded source hash no longer matches the live source file."""
    stale: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    for p in _iter_pages():
        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        rel = p.relative_to(WIKI_DIR).as_posix()
        for stem, recorded in (fm.get("source_hashes") or {}).items():
            src = wiki_ingest.OUTPUTS_DIR / f"{stem}.md"
            current = wiki_ingest._sha256_file(src)
            if current is None:
                missing.append((rel, str(stem)))
            elif current != recorded:
                stale.append((rel, str(stem)))
    return {"stale": stale, "missing_source": missing}


# ── Editorial checks (LLM) ───────────────────────────────────────────────────
def _structural_hints_text(struct: dict) -> str:
    lines = [f"- Pages: {struct['page_count']}"]
    if struct["orphans"]:
        lines.append(f"- Orphan pages (no inbound links): {', '.join(struct['orphans'])}")
    if struct["broken_links"]:
        lines.append("- Broken links (source → missing target):")
        for src, tgt in struct["broken_links"]:
            lines.append(f"    - {src} → [[{tgt}]]")
    if len(lines) == 1:
        lines.append("- No structural issues found.")
    return "\n".join(lines)


def editorial_report(struct: dict, *, model: str, key: str) -> dict:
    from openai import OpenAI

    prompt = (
        LINT_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{CONVENTIONS}}", CONVENTIONS_PATH.read_text(encoding="utf-8"))
        .replace("{{STRUCTURAL_HINTS}}", _structural_hints_text(struct))
        .replace("{{WIKI_STATE}}", _build_wiki_state(WIKI_STATE_BUDGET))
    )
    client = OpenAI(api_key=key, base_url=OPENROUTER_BASE)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You output only a valid JSON wiki lint report."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,
        extra_headers={"HTTP-Referer": "https://deeperpoint.com", "X-Title": "CommonContext wiki lint"},
    )
    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        print(f"  WARN: editorial lint returned invalid JSON ({exc}); structural report only.", file=sys.stderr)
        return {"findings": []}
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return {"findings": []}
    return data


# ── Gap-signal emission (optional, reuses gap_signal.py) ─────────────────────
def emit_signals(findings: list[dict], dsn: str) -> int:
    try:
        import psycopg  # noqa: F401
        from gap_signal import GapSignal, emit_gap_signal
    except Exception as exc:  # pragma: no cover - optional path
        print(f"  WARN: cannot emit signals ({exc}). Install psycopg / check gap_signal.py.", file=sys.stderr)
        return 0
    import psycopg

    emitted = 0
    with psycopg.connect(dsn) as conn:
        for f in findings:
            gs = f.get("gap_signal") or {}
            if not gs.get("gap_description"):
                continue
            signal = GapSignal(
                query=f.get("detail", "")[:500],
                topic_needed=gs.get("topic_needed", "") or "",
                jurisdiction_needed=gs.get("jurisdiction_needed", "") or "",
                gap_description=gs.get("gap_description", ""),
                metadata={"source": "wiki_lint", "kind": f.get("kind", ""), "pages": f.get("pages", [])},
            )
            try:
                emit_gap_signal(signal, conn)
                emitted += 1
            except Exception as exc:
                print(f"  WARN: failed to emit a gap signal: {exc}", file=sys.stderr)
    return emitted


# ── Report writing ───────────────────────────────────────────────────────────
def write_report(struct: dict, prov: dict, stale: dict, editorial: dict, *, today: str) -> None:
    lines = [f"# Wiki Lint Report — {today}", "", "## Structural", ""]
    lines.append(f"- Pages: {struct['page_count']}")
    lines.append(f"- Orphans: {len(struct['orphans'])}")
    for o in struct["orphans"]:
        lines.append(f"  - {o}")
    lines.append(f"- Broken links: {len(struct['broken_links'])}")
    for src, tgt in struct["broken_links"]:
        lines.append(f"  - {src} → [[{tgt}]]")

    lines += ["", "## Provenance (honesty)", ""]
    lines.append(f"- Pages checked: {prov['checked']}")
    lines.append(f"- Violations: {len(prov['violations'])}")
    for rel, reason in prov["violations"]:
        lines.append(f"  - {rel}: {reason}")

    lines += ["", "## Staleness", ""]
    lines.append(f"- Stale pages (source changed since ingest): {len(stale['stale'])}")
    for rel, stem in stale["stale"]:
        lines.append(f"  - {rel} ← {stem}")
    if stale["missing_source"]:
        lines.append(f"- Missing sources: {len(stale['missing_source'])}")
        for rel, stem in stale["missing_source"]:
            lines.append(f"  - {rel} ← {stem} (source file gone)")

    findings = editorial.get("findings", [])
    lines += ["", "## Editorial findings", ""]
    if not findings:
        lines.append("_None reported._")
    for f in findings:
        pages = ", ".join(f.get("pages", []))
        lines.append(f"- **{f.get('kind', 'issue')}** ({pages}): {f.get('detail', '')}")
    REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n## [{today}] lint | {struct['page_count']} pages, "
            f"{len(struct['orphans'])} orphan(s), {len(findings)} finding(s)\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Health-check the LLM Wiki.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--structural", action="store_true", help="Structural checks only (no LLM).")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on broken links, provenance violations, or stale pages (CI gate).")
    parser.add_argument("--emit-signals", action="store_true", help="Emit coverage gaps to the DB.")
    parser.add_argument("--dsn", help="Postgres DSN for gap-signal emission (or POSTGRES_DSN env).")
    args = parser.parse_args(argv)

    if not CONVENTIONS_PATH.exists():
        raise SystemExit(f"Missing {CONVENTIONS_PATH} — scaffold the wiki first.")

    today = _dt.date.today().isoformat()
    struct = structural_report()
    prov = provenance_report()
    stale = staleness_report()
    print(f"[lint] {struct['page_count']} pages | {len(struct['orphans'])} orphan(s) | "
          f"{len(struct['broken_links'])} broken link(s) | "
          f"{len(prov['violations'])} provenance issue(s) | {len(stale['stale'])} stale")

    editorial = {"findings": []}
    if not args.structural:
        key = _discover_key()
        if not key:
            print("  WARN: no OPENROUTER_API_KEY — structural report only.", file=sys.stderr)
        else:
            editorial = editorial_report(struct, model=args.model, key=key)
            print(f"[lint] {len(editorial['findings'])} editorial finding(s)")

    write_report(struct, prov, stale, editorial, today=today)
    print(f"[lint] wrote {REPORT_PATH.relative_to(HERE)}")

    if args.emit_signals:
        for env_path in (HERE / ".env", HERE.parent / "Cosolvent" / ".env"):
            if env_path.exists():
                load_dotenv(env_path, override=False)
        dsn = args.dsn or os.environ.get("POSTGRES_DSN", "")
        if not dsn:
            print("  WARN: --emit-signals set but no --dsn / POSTGRES_DSN; skipping.", file=sys.stderr)
        else:
            n = emit_signals(editorial.get("findings", []), dsn)
            print(f"[lint] emitted {n} gap signal(s) to the DB.")

    if args.strict and (struct["broken_links"] or prov["violations"] or stale["stale"]):
        print("[lint] FAILED (--strict): fix broken links, provenance, and staleness above.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
