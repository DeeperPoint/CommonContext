"""Tests for export_references.py — the chunk_and_embed -> Cosolvent ingestion adapter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from export_references import _source_doc_id, _map_metadata, transform_record  # noqa: E402


def test_source_doc_id_strips_chunk_index():
    assert _source_doc_id({"chunk_id": "27_2025_0"}) == "27_2025"
    assert _source_doc_id({"chunk_id": "27_2025_137"}) == "27_2025"
    assert _source_doc_id({"chunk_id": "doc"}) == "doc"


def test_map_metadata_canonicalizes_keys():
    meta = _map_metadata({"doc_type": "contract", "standard": "GAFTA"}, "prairie-grain")
    assert meta["vertical"] == "prairie-grain"
    assert meta["document_type"] == "contract"   # doc_type -> document_type
    assert meta["organization"] == "GAFTA"       # standard -> organization
    assert meta["doc_type"] == "contract"        # original preserved for filtering


def test_transform_record_happy_path():
    rec = {
        "chunk_id": "27_2025_3",
        "contextual_content": "clause body...",
        "content": "raw",
        "metadata": {"doc_type": "contract", "jurisdiction": ["Canada"]},
        "embedding": [0.1] * 1536,
    }
    out = transform_record(rec, "prairie-grain")
    assert out["source_doc_id"] == "27_2025"
    assert out["vertical"] == "prairie-grain"
    assert out["chunk_text"] == "clause body..."   # prefers contextual_content
    assert len(out["embedding"]) == 1536
    assert out["metadata"]["document_type"] == "contract"


@pytest.mark.parametrize("rec", [
    {"chunk_id": "x_0", "metadata": {}, "embedding": [0.1]},        # no text
    {"chunk_id": "x_0", "content": "t", "metadata": {}},            # no embedding
    {"chunk_id": "x_0", "content": "t", "embedding": [], "metadata": {}},
])
def test_transform_skips_unusable(rec):
    assert transform_record(rec, "v") is None
