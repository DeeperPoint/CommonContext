# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for provenance recording and frontmatter injection."""
from __future__ import annotations

import provenance as prov


def test_record_and_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path)
    rec = prov.recordProvenance(
        outputStem="doc1",
        sourceUrl="https://example.com/x.pdf",
        sourceType="url_download",
        conversionMethod="marker-pdf",
    )
    assert rec["source_url"] == "https://example.com/x.pdf"
    assert rec["output_filename"] == "doc1.md"

    fetched = prov.getProvenance("doc1")
    assert fetched["source_type"] == "url_download"
    assert fetched["conversion_method"] == "marker-pdf"


def test_get_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path)
    assert prov.getProvenance("nope") is None


def test_record_merges_without_clobbering(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path)
    prov.recordProvenance(outputStem="d", sourceUrl="https://a")
    # A later call that omits sourceUrl must not wipe the existing value.
    prov.recordProvenance(outputStem="d", notes="second pass")
    rec = prov.getProvenance("d")
    assert rec["source_url"] == "https://a"
    assert rec["notes"] == "second pass"


def test_list_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path)
    prov.recordProvenance(outputStem="a", sourceUrl="https://a")
    prov.recordProvenance(outputStem="b", sourceUrl="https://b")
    stems = {r["_stem"] for r in prov.listProvenance()}
    assert {"a", "b"} <= stems
    assert prov.deleteProvenance("a") is True
    assert prov.deleteProvenance("a") is False


def test_inject_frontmatter_prepends_when_absent(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nBody.", encoding="utf-8")
    prov.injectFrontmatter(md, {
        "source_url": "https://example.com",
        "document_title": "My Doc",
        "source_type": "file_upload",
    })
    text = md.read_text(encoding="utf-8")
    assert text.startswith("---")
    # URLs contain ':' so the injector quotes them — that's the correct YAML.
    assert 'source_url: "https://example.com"' in text
    assert "# Title" in text


def test_inject_frontmatter_merges_into_existing(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: Existing\n---\n\n# Body", encoding="utf-8")
    prov.injectFrontmatter(md, {
        "source_url": "https://example.com",
        "document_title": "Should Not Overwrite Title",
    })
    text = md.read_text(encoding="utf-8")
    # Existing key preserved, new key added.
    assert "title: Existing" in text
    assert 'source_url: "https://example.com"' in text
    # Only one frontmatter block.
    assert text.count("---") == 2
