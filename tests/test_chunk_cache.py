# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""The content-addressed cache for the pipeline's two paid steps.

Both tagging and embedding are deterministic functions of their input and were
recomputed on every run. These tests pin the properties that make skipping them
safe — above all that the key covers everything the answer depends on, since a
cache that returns a confidently wrong vector is worse than no cache.
"""
from __future__ import annotations

import pytest

from chunk_cache import ChunkCache, content_key


@pytest.fixture
def cache(tmp_path):
    with ChunkCache(tmp_path / "c.sqlite") as c:
        yield c


# ── Keys ─────────────────────────────────────────────────────────────────────
def test_same_content_same_key():
    assert content_key("model", "text") == content_key("model", "text")


def test_different_content_different_key():
    assert content_key("model", "a") != content_key("model", "b")


def test_the_model_is_part_of_the_key():
    """Two models produce different vectors for identical text."""
    assert content_key("model-a", "text") != content_key("model-b", "text")


def test_parts_cannot_be_smeared_together():
    """The classic hand-rolled-key bug: ("ab","c") and ("a","bc") colliding, so
    one entry is served for two different inputs."""
    assert content_key("ab", "c") != content_key("a", "bc")


# ── Store ────────────────────────────────────────────────────────────────────
def test_round_trips_a_vector(cache):
    vector = [0.1, 0.2, 0.3]
    cache.put("embedding", "k", vector)
    assert cache.get("embedding", "k") == vector


def test_kinds_are_namespaced(cache):
    """An embedding and a topic tag can share a key without colliding."""
    cache.put("embedding", "k", [1.0])
    cache.put("topic", "k", "payment_terms")
    assert cache.get("embedding", "k") == [1.0]
    assert cache.get("topic", "k") == "payment_terms"


def test_a_miss_returns_none(cache):
    assert cache.get("embedding", "absent") is None


def test_put_many_writes_a_batch(cache):
    cache.put_many("embedding", [("a", [1.0]), ("b", [2.0])])
    assert cache.get("embedding", "a") == [1.0]
    assert cache.get("embedding", "b") == [2.0]


def test_entries_survive_reopening(tmp_path):
    """The point of the cache: a later run pays nothing for unchanged chunks."""
    path = tmp_path / "c.sqlite"
    with ChunkCache(path) as first:
        first.put("embedding", "k", [0.5])
    with ChunkCache(path) as second:
        assert second.get("embedding", "k") == [0.5]


def test_a_newer_schema_version_ignores_older_entries(tmp_path, monkeypatch):
    """Rolling a release forward must not serve values the new code would
    compute differently — and rolling back must not destroy a warm cache."""
    import chunk_cache

    path = tmp_path / "c.sqlite"
    with ChunkCache(path) as first:
        first.put("embedding", "k", [0.5])

    monkeypatch.setattr(chunk_cache, "SCHEMA_VERSION", chunk_cache.SCHEMA_VERSION + 1)
    with ChunkCache(path) as second:
        assert second.get("embedding", "k") is None

    monkeypatch.undo()
    with ChunkCache(path) as third:
        assert third.get("embedding", "k") == [0.5], "old entries must still be there"


# ── Degradation ──────────────────────────────────────────────────────────────
def test_disabled_cache_never_hits(tmp_path):
    c = ChunkCache(tmp_path / "c.sqlite", enabled=False)
    c.put("embedding", "k", [1.0])
    assert c.get("embedding", "k") is None


def test_an_unopenable_cache_degrades_instead_of_raising(tmp_path):
    """A cache is a performance feature. Losing it must never fail a build."""
    unusable = tmp_path / "a-file"
    unusable.write_text("not a database", encoding="utf-8")
    c = ChunkCache(unusable / "nested" / "c.sqlite")
    c.put("embedding", "k", [1.0])
    assert c.get("embedding", "k") is None


def test_stats_report_the_hit_rate(cache):
    cache.put("embedding", "hit", [1.0])
    cache.get("embedding", "hit")
    cache.get("embedding", "miss")
    assert "1/2" in cache.stats
