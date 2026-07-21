# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for the wiki tooling: frontmatter, provenance honesty, staleness, structure.

Network-free and filesystem-isolated — the wiki and outputs directories are
redirected into a tmp tree, so no LLM key or real repo files are touched.
"""
from __future__ import annotations

import pytest

import wiki_ingest
import wiki_lint
from wiki_ingest import (
    normalize_provenance,
    parse_frontmatter,
    render_page,
    source_hashes,
)


# ── pure helpers ─────────────────────────────────────────────────────────────

def test_frontmatter_roundtrip():
    fields = {
        "title": "GAFTA 27", "type": "entity", "summary": "A contract.",
        "sources": ["27_2025"], "provenance": [{"section": "Terms", "tag": "W"}],
        "status": "draft", "source_hashes": {"27_2025": "abc"}, "updated": "2026-07-21",
    }
    fm, body = parse_frontmatter(render_page(fields, "# Body\n\nText [[wheat]]."))
    assert fm == fields
    assert body.strip().startswith("# Body")


def test_normalize_provenance_defaults_and_filters():
    assert normalize_provenance(None, has_sources=True) == [{"section": "page", "tag": "W"}]
    assert normalize_provenance([], has_sources=False) == [{"section": "page", "tag": "I"}]
    # Bad tags dropped; valid kept and upper-cased.
    got = normalize_provenance(
        [{"section": "a", "tag": "w"}, {"section": "b", "tag": "X"}, {"section": "c", "tag": "D"}],
        has_sources=True,
    )
    assert got == [{"section": "a", "tag": "W"}, {"section": "c", "tag": "D"}]


def test_honesty_gate_logic():
    assert wiki_lint.page_is_honest({"provenance": [{"tag": "W"}, {"tag": "I"}]})       # W>=D+I
    assert not wiki_lint.page_is_honest({"provenance": [{"tag": "I"}, {"tag": "D"}]})   # W<D+I
    assert wiki_lint.page_is_honest({"status": "signed_off", "provenance": [{"tag": "I"}]})
    assert not wiki_lint.page_is_honest({})                                             # no provenance


# ── fixtures for the filesystem-scanning reports ─────────────────────────────

@pytest.fixture
def wiki(tmp_path, monkeypatch):
    wdir = tmp_path / "wiki"
    (wdir / "entities").mkdir(parents=True)
    odir = tmp_path / "outputs"
    odir.mkdir()
    monkeypatch.setattr(wiki_ingest, "WIKI_DIR", wdir)
    monkeypatch.setattr(wiki_lint, "WIKI_DIR", wdir)
    monkeypatch.setattr(wiki_ingest, "OUTPUTS_DIR", odir)
    return wdir, odir


def _page(wdir, rel, fields, body="# Page\n\nBody."):
    p = wdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_page(fields, body), encoding="utf-8")
    return p


def _fields(**over):
    base = {"title": "P", "type": "entity", "summary": "s", "sources": ["src"],
            "provenance": [{"section": "main", "tag": "W"}], "status": "draft",
            "source_hashes": {}, "updated": "2026-07-21"}
    base.update(over)
    return base


# ── provenance report (honesty gate) ─────────────────────────────────────────

def test_provenance_report_flags_missing_and_dishonest(wiki):
    wdir, _ = wiki
    _page(wdir, "entities/clean.md", _fields())                                   # W → ok
    _page(wdir, "entities/nofm.md", _fields(provenance=[]))                        # none → flagged
    _page(wdir, "entities/interp.md", _fields(provenance=[{"section": "x", "tag": "I"},
                                                          {"section": "y", "tag": "D"}]))  # majority D/I
    _page(wdir, "entities/signed.md", _fields(status="signed_off",
                                              provenance=[{"section": "x", "tag": "I"}]))   # signed off → ok
    rep = wiki_lint.provenance_report()
    flagged = {rel for rel, _ in rep["violations"]}
    assert rep["checked"] == 4
    assert flagged == {"entities/nofm.md", "entities/interp.md"}


# ── staleness report (hash-based) ────────────────────────────────────────────

def test_staleness_report_detects_drift_and_missing(wiki):
    wdir, odir = wiki
    (odir / "src.md").write_text("ORIGINAL SOURCE", encoding="utf-8")
    hashes = source_hashes(["src"])                       # record current hash
    _page(wdir, "entities/fresh.md", _fields(source_hashes=hashes))
    assert wiki_lint.staleness_report()["stale"] == []    # matches → clean

    (odir / "src.md").write_text("CHANGED SOURCE", encoding="utf-8")
    rep = wiki_lint.staleness_report()
    assert ("entities/fresh.md", "src") in rep["stale"]   # drift → stale

    (odir / "src.md").unlink()
    rep = wiki_lint.staleness_report()
    assert ("entities/fresh.md", "src") in rep["missing_source"]


# ── structural report (orphans / broken links) ───────────────────────────────

def test_structural_report_orphan_and_broken(wiki):
    wdir, _ = wiki
    _page(wdir, "entities/a.md", _fields(title="A"), body="# A\n\nLinks to [[b]] and [[ghost]].")
    _page(wdir, "entities/b.md", _fields(title="B"), body="# B\n\nNo inbound links here.")
    rep = wiki_lint.structural_report()
    assert rep["page_count"] == 2
    assert "entities/a.md" in rep["orphans"]              # nothing links to a
    assert ("entities/a.md", "ghost") in rep["broken_links"]
