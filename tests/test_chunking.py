# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for the semantic chunker and the doc-level metadata mapping."""
from __future__ import annotations

import chunk_and_embed as ce


# ── Frontmatter stripping ─────────────────────────────────────────────────────

def test_strip_frontmatter_removes_leading_block():
    raw = "---\nsource_url: x\ntitle: y\n---\n\n# Heading\n\nBody text."
    out = ce._strip_frontmatter(raw)
    assert not out.lstrip().startswith("---")
    assert "# Heading" in out
    assert "source_url" not in out


def test_strip_frontmatter_noop_without_block():
    raw = "# Heading\n\nNo frontmatter here."
    assert ce._strip_frontmatter(raw) == raw


def test_frontmatter_not_emitted_as_chunk():
    """Regression: the YAML frontmatter must never become an embedded chunk."""
    raw = "---\nsource_url: https://x\n---\n\n# 1. GOODS\n\nWheat in bulk."
    chunks = ce._split_markdown_by_headings(ce._strip_frontmatter(raw))
    joined = " ".join(c["content"] for c in chunks)
    assert "source_url" not in joined
    assert any("Wheat in bulk" in c["content"] for c in chunks)


# ── Heading-based splitting ───────────────────────────────────────────────────

def test_split_builds_hierarchy_lineage():
    md = (
        "# 13. PAYMENT\n\n"
        "Intro to payment.\n\n"
        "## (b) Shipping documents\n\n"
        "Invoice and bill of lading."
    )
    chunks = ce._split_markdown_by_headings(md)
    # The nested chunk carries the full heading lineage.
    nested = [c for c in chunks if "Invoice" in c["content"]][0]
    assert nested["hierarchy"] == "13. PAYMENT > (b) Shipping documents"


def test_split_pops_deeper_levels_on_new_section():
    md = (
        "# A\n\nbody a\n\n"
        "## A.1\n\nbody a1\n\n"
        "# B\n\nbody b"
    )
    chunks = ce._split_markdown_by_headings(md)
    b_chunk = [c for c in chunks if c["content"] == "body b"][0]
    # Section B must not inherit A.1 in its lineage.
    assert b_chunk["hierarchy"] == "B"


def test_split_drops_empty_sections():
    md = "# Empty\n\n# Real\n\nReal content here."
    chunks = ce._split_markdown_by_headings(md)
    assert all(c["content"].strip() for c in chunks)
    assert len(chunks) == 1


# ── Standard normalisation (grain) ────────────────────────────────────────────

def test_normalize_standard_extracts_acronym():
    assert ce._normalize_standard("Grain and Feed Trade Association (GAFTA)") == "GAFTA"
    assert ce._normalize_standard("Canadian Grain Commission CGC") == "CGC"


def test_normalize_standard_unknown_returns_none():
    assert ce._normalize_standard("Some Random Org") is None
    assert ce._normalize_standard(None) is None
    assert ce._normalize_standard("") is None


# ── Standards-body normalisation (manufacturing) ──────────────────────────────

def test_normalize_standard_body_word_boundary():
    assert ce._normalize_standard_body("ASTM International") == "ASTM"
    assert ce._normalize_standard_body("ISO/TC 79") == "ISO"
    # "EN" must not match inside an unrelated word like "ENGINEERING".
    assert ce._normalize_standard_body("Engineering Standards Group") is None
    assert ce._normalize_standard_body("EN 573 Committee") == "EN"


# ── Vertical-aware base metadata ──────────────────────────────────────────────

def test_build_base_metadata_grain():
    block = {
        "document_metadata": {"document_type": "contract"},
        "issuing_organization": {"name": "GAFTA"},
        "geographic_scope": {"jurisdictions": ["Canada", "United States"]},
    }
    md = ce._build_base_metadata("grain", block)
    assert md == {
        "doc_type": "contract",
        "standard": "GAFTA",
        "jurisdiction": ["Canada", "United States"],
    }
    # Grain metadata must not carry manufacturing-only keys.
    assert "material_class" not in md


def test_build_base_metadata_manufacturing():
    block = {
        "document_metadata": {"document_type": "specification"},
        "issuing_organization": {"name": "ASTM International"},
        "geographic_scope": {"jurisdictions": ["United States"]},
        "material": {
            "material_class": "aluminum_alloy",
            "export_control_regime": "EAR",
            "process_type": ["rolling", "heat_treatment"],
        },
    }
    md = ce._build_base_metadata("manufacturing", block)
    assert md["doc_type"] == "specification"
    assert md["standard_body"] == "ASTM"
    assert md["material_class"] == "aluminum_alloy"
    assert md["export_control_regime"] == "EAR"
    assert md["process_type"] == ["rolling", "heat_treatment"]
    # Manufacturing metadata must not carry the grain "standard" key.
    assert "standard" not in md


def test_build_base_metadata_defaults_when_empty():
    assert ce._build_base_metadata("grain", {})["doc_type"] == "other"
    assert ce._build_base_metadata("manufacturing", {})["doc_type"] == "specification"
