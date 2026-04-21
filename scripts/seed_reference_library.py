#!/usr/bin/env python3
"""
seed_reference_library.py
─────────────────────────
Streams .jsonl output from chunk_and_embed.py into Cosolvent's
reference_library PostgreSQL / pgvector table.

Behaviour
─────────
  Idempotent   Re-running on the same file updates changed chunks in-place.
               chunk_id is the natural key — ON CONFLICT DO UPDATE.
  Streaming    Reads .jsonl one line at a time; safe for large files.
  Batched      Commits every --batch-size rows so a crash leaves a
               recoverable state, not an all-or-nothing failure.
  Observable   Live tqdm progress bar + per-error stderr logging.
  Safe         --dry-run validates every record without touching the DB.

Usage
─────
  # Normal load (single file)
  python seed_reference_library.py chunks/27_2025_processed.jsonl \\
      --db-url "postgresql://user:pass@localhost:5432/cosolvent"

  # Load all .jsonl files in a directory
  python seed_reference_library.py chunks/ \\
      --db-url "postgresql://user:pass@localhost:5432/cosolvent"

  # First-time setup: create table + indexes, then load
  python seed_reference_library.py chunks/ --create-table --db-url ...

  # Preview only — no DB writes
  python seed_reference_library.py chunks/ --dry-run

  # Larger batches for fast networks / powerful DBs
  python seed_reference_library.py chunks/ --batch-size 250 --db-url ...

  # DB URL from environment (recommended for CI/CD)
  export DATABASE_URL="postgresql://user:pass@localhost:5432/cosolvent"
  python seed_reference_library.py chunks/

Dependencies
────────────
  pip install "psycopg[binary]" pgvector click tqdm
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import click
import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from tqdm import tqdm


# ─── SQL ──────────────────────────────────────────────────────────────────────

# Idempotent DDL — safe to run multiple times.
# HNSW index is created on an empty table; for large re-indexes drop it first.
DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS reference_library (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id            TEXT          UNIQUE NOT NULL,
    content             TEXT          NOT NULL,
    contextual_content  TEXT          NOT NULL,
    metadata            JSONB         NOT NULL DEFAULT '{}',
    embedding           vector(1536)  NOT NULL,
    source_document     TEXT,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- GIN index enables fast metadata pre-filtering before vector similarity.
-- jsonb_path_ops is smaller and faster than the default for @> queries.
CREATE INDEX IF NOT EXISTS idx_rl_metadata
    ON reference_library USING GIN (metadata jsonb_path_ops);

-- HNSW is the recommended index for pgvector >=0.5.
-- m=16, ef_construction=64 are good defaults for 1536-dim OpenAI embeddings.
-- For recall-vs-speed tuning, adjust ef_search at query time.
CREATE INDEX IF NOT EXISTS idx_rl_embedding
    ON reference_library USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""

# xmax = 0 on a live tuple means the row was just inserted (not updated).
# This lets us distinguish inserts from updates without a separate query.
UPSERT_SQL = """
INSERT INTO reference_library
    (chunk_id, content, contextual_content, metadata, embedding, source_document)
VALUES
    (%(chunk_id)s,
     %(content)s,
     %(contextual_content)s,
     %(metadata)s,
     %(embedding)s,
     %(source_document)s)
ON CONFLICT (chunk_id) DO UPDATE SET
    content            = EXCLUDED.content,
    contextual_content = EXCLUDED.contextual_content,
    metadata           = EXCLUDED.metadata,
    embedding          = EXCLUDED.embedding,
    source_document    = EXCLUDED.source_document,
    updated_at         = now()
RETURNING
    chunk_id,
    (xmax = 0) AS was_inserted
"""


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class RunCounter:
    """Mutable counters accumulated across one or more files."""
    inserted: int   = 0
    updated:  int   = 0
    failed:   int   = 0
    skipped:  int   = 0   # dry-run only
    elapsed:  float = 0.0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.failed + self.skipped

    def __iadd__(self, other: RunCounter) -> RunCounter:
        self.inserted += other.inserted
        self.updated  += other.updated
        self.failed   += other.failed
        self.skipped  += other.skipped
        # elapsed is summed by the caller using wall-clock time
        return self

    def print(self, label: str = "") -> None:
        tag = f"[{label}] " if label else ""
        click.echo(f"\n{'─' * 46}")
        click.echo(f"  {tag}Inserted  {self.inserted:>8,}")
        click.echo(f"  {tag}Updated   {self.updated:>8,}")
        if self.failed:
            click.echo(
                click.style(f"  {tag}Failed    {self.failed:>8,}", fg="red")
            )
        if self.skipped:
            click.echo(f"  {tag}Skipped   {self.skipped:>8,}  (dry-run)")
        click.echo(f"{'─' * 46}")
        click.echo(f"  {tag}Total     {self.total:>8,}  in {self.elapsed:.1f}s")


# ─── Record validation ────────────────────────────────────────────────────────

_REQUIRED_FIELDS = frozenset({"chunk_id", "content", "contextual_content", "metadata", "embedding"})


def to_params(record: dict) -> dict:
    """
    Validate a raw JSONL record and return psycopg-ready params.

    Raises
    ------
    ValueError  if required fields are absent or types are wrong.
    """
    if missing := _REQUIRED_FIELDS - record.keys():
        raise ValueError(f"missing fields: {sorted(missing)}")

    if not isinstance(record["embedding"], list):
        raise ValueError(
            f"'embedding' must be a JSON array, got {type(record['embedding']).__name__}"
        )

    if not isinstance(record["metadata"], dict):
        raise ValueError(
            f"'metadata' must be a JSON object, got {type(record['metadata']).__name__}"
        )

    return {
        # Text fields
        "chunk_id":           record["chunk_id"],
        "content":            record["content"],
        "contextual_content": record["contextual_content"],
        # Jsonb wrapper tells psycopg3 to encode the dict as JSONB directly,
        # avoiding a double-serialisation (dict → str → JSONB).
        "metadata":           Jsonb(record["metadata"]),
        # pgvector's register_vector() teaches psycopg3 to encode list[float]
        # as the vector wire format. No manual conversion needed.
        "embedding":          record["embedding"],
        # Denormalised for cheap filtering without unwrapping JSONB.
        "source_document":    record["metadata"].get("source_document"),
    }


# ─── I/O helpers ─────────────────────────────────────────────────────────────

def iter_records(path: Path) -> Iterator[tuple[int, dict | None]]:
    """
    Yield (lineno, parsed_record) for every non-blank line in a .jsonl file.
    Yields (lineno, None) for lines that fail JSON parsing so the caller
    can count failures without stopping the iteration.
    """
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield lineno, json.loads(raw)
            except json.JSONDecodeError as exc:
                tqdm.write(f"  [warn] line {lineno}: JSON error — {exc}", file=sys.stderr)
                yield lineno, None


def fast_line_count(path: Path) -> int:
    """Count newlines in O(file_size) time without loading into memory."""
    count = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            count += chunk.count(b"\n")
    return count


# ─── Batch execution ──────────────────────────────────────────────────────────

def _flush(
    conn: psycopg.Connection,
    batch: list[dict],
    counter: RunCounter,
) -> None:
    """
    Upsert one batch inside a transaction.

    On DB error the batch is rolled back (not the entire file) and the
    failed count is incremented. The connection is left in a clean state
    so subsequent batches can continue.

    psycopg3 executemany(returning=True) creates one result set per row.
    We iterate them with nextset() to collect the was_inserted flag.
    """
    try:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, batch, returning=True)

            # Collect per-row results.  nextset() advances the cursor to the
            # next statement result; returns False when exhausted.
            while True:
                row = cur.fetchone()
                if row is not None:
                    was_inserted: bool = row[1]
                    if was_inserted:
                        counter.inserted += 1
                    else:
                        counter.updated += 1
                if not cur.nextset():
                    break

        conn.commit()

    except psycopg.Error as exc:
        conn.rollback()
        counter.failed += len(batch)
        tqdm.write(
            f"  [error] batch of {len(batch)} rolled back — {exc}",
            file=sys.stderr,
        )


# ─── Per-file seed ────────────────────────────────────────────────────────────

def seed_file(
    conn: psycopg.Connection,
    path: Path,
    batch_size: int,
    dry_run: bool,
) -> RunCounter:
    """
    Stream all records from `path` into reference_library.
    Returns a RunCounter with results for this file.
    """
    counter = RunCounter()
    t0 = time.perf_counter()

    total_lines = fast_line_count(path)
    pending: list[dict] = []

    with tqdm(
        total=total_lines,
        unit="chunk",
        desc=path.name,
        dynamic_ncols=True,
        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
    ) as bar:
        for lineno, record in iter_records(path):
            bar.update(1)

            # JSON parse failure
            if record is None:
                counter.failed += 1
                continue

            # Schema validation
            try:
                params = to_params(record)
            except ValueError as exc:
                tqdm.write(
                    f"  [skip] line {lineno} "
                    f"(chunk_id={record.get('chunk_id', '?')}): {exc}",
                    file=sys.stderr,
                )
                counter.failed += 1
                continue

            # Dry-run: count but do not accumulate
            if dry_run:
                counter.skipped += 1
                continue

            pending.append(params)

            if len(pending) >= batch_size:
                _flush(conn, pending, counter)
                pending.clear()

        # Flush the final partial batch
        if pending and not dry_run:
            _flush(conn, pending, counter)

    counter.elapsed = time.perf_counter() - t0
    return counter


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.argument(
    "source",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--db-url",
    envvar="DATABASE_URL",
    default="postgresql://localhost/cosolvent",
    show_default=True,
    help="PostgreSQL DSN.  Falls back to DATABASE_URL env var.",
)
@click.option(
    "--batch-size",
    default=100,
    show_default=True,
    type=click.IntRange(1, 1000),
    help="Rows committed per batch.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate all records without writing to the database.",
)
@click.option(
    "--create-table",
    is_flag=True,
    default=False,
    help=(
        "Run idempotent DDL before loading: creates reference_library "
        "table and indexes if they do not already exist."
    ),
)
def main(
    source: Path,
    db_url: str,
    batch_size: int,
    dry_run: bool,
    create_table: bool,
) -> None:
    """
    Load .jsonl chunks into Cosolvent's reference_library table.

    SOURCE can be a single .jsonl file or a directory. When SOURCE is a
    directory, every *.jsonl file is processed in sorted (alphabetical)
    order, which matches the naming convention used by chunk_and_embed.py.

    Records are upserted on chunk_id — re-running after regenerating chunks
    updates changed content in-place rather than duplicating rows.
    """
    # ── Resolve source files ───────────────────────────────────────────────
    if source.is_dir():
        files = sorted(source.glob("*.jsonl"))
        if not files:
            click.echo(f"No .jsonl files found in {source}", err=True)
            sys.exit(1)
        click.echo(f"Found {len(files)} file(s) in {source}/\n")
    else:
        files = [source]

    if dry_run:
        click.echo("Dry-run mode — no data will be written.\n")

    # ── Connect ────────────────────────────────────────────────────────────
    try:
        conn = psycopg.connect(db_url, autocommit=False)
        register_vector(conn)
    except psycopg.OperationalError as exc:
        click.echo(f"Connection failed: {exc}", err=True)
        sys.exit(1)

    # ── Optional DDL ───────────────────────────────────────────────────────
    if create_table:
        click.echo("Applying DDL (CREATE TABLE IF NOT EXISTS + indexes)...")
        try:
            with conn.cursor() as cur:
                cur.execute(DDL)
            conn.commit()
            click.echo("Done.\n")
        except psycopg.Error as exc:
            click.echo(f"DDL failed: {exc}", err=True)
            conn.close()
            sys.exit(1)

    # ── Seed each file ─────────────────────────────────────────────────────
    grand = RunCounter()
    wall_start = time.perf_counter()

    for f in files:
        result = seed_file(conn, f, batch_size, dry_run)
        result.print(label=f.stem)
        grand += result

    # ── Grand total (only shown for multi-file runs) ───────────────────────
    if len(files) > 1:
        grand.elapsed = time.perf_counter() - wall_start
        click.echo("\nGrand total:")
        grand.print()

    conn.close()

    # Exit 1 if any records failed (useful for CI pipelines)
    if grand.failed and not dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
