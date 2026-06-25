# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for the seed script's record validation and I/O helpers.

These cover the pure functions only — the live DB upsert path is exercised by
the Dockerized integration test (test_db_integration.py).
"""
from __future__ import annotations

import json

import pytest

import seed_reference_library as seed


def _record(**overrides):
    base = {
        "chunk_id": "27_2025_0",
        "content": "Payment terms...",
        "contextual_content": "[27_2025.md] 13. PAYMENT > Payment terms...",
        "metadata": {"doc_type": "contract", "topic": "payment_terms"},
        "embedding": [0.1] * 1536,
    }
    base.update(overrides)
    return base


def test_to_params_accepts_valid_record():
    params = seed.to_params(_record())
    assert params["chunk_id"] == "27_2025_0"
    assert params["embedding"] == [0.1] * 1536
    # metadata is wrapped for psycopg JSONB encoding.
    assert type(params["metadata"]).__name__ == "Jsonb"


def test_to_params_denormalizes_source_document():
    rec = _record(metadata={"topic": "x", "source_document": "27_2025.md"})
    assert seed.to_params(rec)["source_document"] == "27_2025.md"


def test_to_params_missing_field_raises():
    rec = _record()
    del rec["embedding"]
    with pytest.raises(ValueError, match="missing fields"):
        seed.to_params(rec)


def test_to_params_embedding_must_be_list():
    with pytest.raises(ValueError, match="embedding"):
        seed.to_params(_record(embedding="not-a-list"))


def test_to_params_metadata_must_be_dict():
    with pytest.raises(ValueError, match="metadata"):
        seed.to_params(_record(metadata="not-a-dict"))


def test_iter_records_skips_blanks_and_flags_bad_json(tmp_path):
    p = tmp_path / "chunks.jsonl"
    p.write_text(
        json.dumps(_record()) + "\n"
        "\n"                       # blank line — skipped entirely
        "{ not valid json\n"        # parse error — yielded as None
        + json.dumps(_record(chunk_id="27_2025_1")) + "\n",
        encoding="utf-8",
    )
    results = list(seed.iter_records(p))
    parsed = [r for _, r in results]
    assert parsed.count(None) == 1
    good = [r for r in parsed if r is not None]
    assert {r["chunk_id"] for r in good} == {"27_2025_0", "27_2025_1"}


def test_fast_line_count(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text("a\nb\nc\n", encoding="utf-8")
    assert seed.fast_line_count(p) == 3


def test_run_counter_total_and_merge():
    a = seed.RunCounter(inserted=2, updated=1)
    b = seed.RunCounter(inserted=3, failed=1)
    a += b
    assert a.inserted == 5
    assert a.failed == 1
    assert a.total == 7
