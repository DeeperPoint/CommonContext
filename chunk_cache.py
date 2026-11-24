# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""Content-addressed cache for the two paid steps of the chunking pipeline.

Both LLM topic tagging and embedding are deterministic functions of their input,
and the pipeline re-runs them for every chunk on every run. Re-ingesting one
edited page in a 1,345-chunk corpus pays for all 1,345 chunks twice over: once in
tagging calls, once in embedding calls. Nothing about that is visible at demo
size and all of it is a recurring cost at realistic size.

The cache is keyed on content, not on filename or position, which is what makes
it correct under the edits that actually happen. Insert a paragraph at the top of
a page and every chunk below it shifts position while its text is unchanged — a
position-keyed cache misses on all of them, a content-keyed cache hits on all but
the new one.

SQLite rather than a JSON file: the values are 1536-element float vectors, and a
corpus-sized JSON cache is tens of megabytes that must be parsed in full to read
one entry. sqlite3 is in the standard library, so this adds no dependency.

The cache is disposable by construction. Delete the file and the next run rebuilds
it at full price, correctly. Nothing reads it as a source of truth.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("curation.cache")

# Overridable so a test run, or two checkouts sharing a machine, do not write into
# each other's cache. A cache that persists across a test suite makes tests pass or
# fail depending on what ran before them.
CACHE_PATH_ENV = "CHUNK_CACHE_PATH"


def default_cache_path() -> Path:
    override = os.environ.get(CACHE_PATH_ENV, "").strip()
    return Path(override) if override else Path("outputs") / ".chunk_cache.sqlite"

# Bump when a change makes previously cached values wrong rather than merely
# stale. Entries written under an older version are ignored, not deleted, so
# rolling back a release does not throw away a warm cache.
SCHEMA_VERSION = 1


def content_key(*parts: Any) -> str:
    """A stable key over any number of string-ish parts.

    Parts are joined with a separator that cannot occur in them, so that
    ("ab", "c") and ("a", "bc") do not collide onto the same key — the usual way
    a hand-rolled cache key quietly returns the wrong entry.
    """
    joined = "\x00".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class ChunkCache:
    """Key→value store for embeddings and topic tags, namespaced by kind."""

    def __init__(self, path: Path | str | None = None, *, enabled: bool = True):
        self.enabled = enabled
        self.path = Path(path) if path is not None else default_cache_path()
        self._conn: sqlite3.Connection | None = None
        self.hits = 0
        self.misses = 0
        if self.enabled:
            self._open()

    def _open(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "  kind TEXT NOT NULL,"
                "  key TEXT NOT NULL,"
                "  version INTEGER NOT NULL,"
                "  value TEXT NOT NULL,"
                "  PRIMARY KEY (kind, key, version))"
            )
            self._conn.commit()
        except (sqlite3.Error, OSError) as exc:
            # OSError as well as sqlite3.Error: creating the parent directory is
            # the first thing that happens here and the first thing that fails,
            # on a read-only volume or where a file already occupies the path.
            # A cache that cannot open is a performance problem, never a
            # correctness one: fall through to recomputing everything.
            logger.warning("chunk cache unavailable (%s); continuing without it", exc)
            self._conn = None
            self.enabled = False

    def get(self, kind: str, key: str) -> Any | None:
        if not self._conn:
            return None
        try:
            row = self._conn.execute(
                "SELECT value FROM entries WHERE kind=? AND key=? AND version=?",
                (kind, key, SCHEMA_VERSION),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            self.misses += 1
            return None
        try:
            value = json.loads(row[0])
        except json.JSONDecodeError:
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, kind: str, key: str, value: Any) -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO entries (kind, key, version, value) VALUES (?,?,?,?)",
                (kind, key, SCHEMA_VERSION, json.dumps(value)),
            )
            self._conn.commit()
        except (sqlite3.Error, TypeError, ValueError) as exc:
            logger.warning("could not cache %s/%s (%s)", kind, key[:12], exc)

    def put_many(self, kind: str, items: list[tuple[str, Any]]) -> None:
        """Write a batch in one transaction — one commit per chunk is most of
        the wall-clock cost of a warm run otherwise."""
        if not self._conn or not items:
            return
        try:
            self._conn.executemany(
                "INSERT OR REPLACE INTO entries (kind, key, version, value) VALUES (?,?,?,?)",
                [(kind, k, SCHEMA_VERSION, json.dumps(v)) for k, v in items],
            )
            self._conn.commit()
        except (sqlite3.Error, TypeError, ValueError) as exc:
            logger.warning("could not cache a batch of %s (%s)", kind, exc)

    @property
    def stats(self) -> str:
        total = self.hits + self.misses
        if not self.enabled:
            return "cache disabled"
        if not total:
            return "cache empty"
        return f"{self.hits}/{total} cached ({self.hits * 100 // total}%)"

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> ChunkCache:
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.close()
        return False
