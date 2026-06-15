# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
Integration test: real Postgres + pgvector via Docker.

Spins up docker-compose.test.yml, runs the *actual* seed_reference_library.py
against it, and validates the metadata-filtered + vector-similarity retrieval
patterns the Cosolvent team will rely on (ROADMAP Phase 4). Also asserts the
seed is idempotent (re-running upserts rather than duplicating).

Opt-in: `pytest -m integration`. Skips cleanly if Docker is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

psycopg = pytest.importorskip("psycopg")
from pgvector.psycopg import register_vector  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.test.yml"
TEST_DB_URL = "postgresql://user:pass@127.0.0.1:5439/cosolvent"


def _compose_cmd() -> list[str] | None:
    """Return the available Docker Compose command, or None if Docker is absent."""
    if shutil.which("docker") is None:
        return None
    # Prefer the v2 plugin (`docker compose`); fall back to legacy `docker-compose`.
    try:
        subprocess.run(["docker", "compose", "version"],
                       capture_output=True, check=True)
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def _make_jsonl(path: Path) -> None:
    """Three GAFTA-style records mirroring the original integration fixture."""
    records = [
        {
            "chunk_id": "27_2025_0",
            "content": "Payment terms for UK buyers...",
            "contextual_content": "[27_2025.md] 13. PAYMENT > terms",
            "metadata": {"doc_type": "contract", "standard": "GAFTA",
                         "jurisdiction": ["UK"], "topic": "payment_terms",
                         "source_document": "27_2025.md"},
            "embedding": [0.1] * 1536,
        },
        {
            "chunk_id": "27_2025_1",
            "content": "Quality requirements in Canada...",
            "contextual_content": "[27_2025.md] 5. QUALITY > grade",
            "metadata": {"doc_type": "contract", "standard": "GAFTA",
                         "jurisdiction": ["Canada"], "topic": "quality_requirements",
                         "source_document": "27_2025.md"},
            "embedding": [0.2] * 1536,
        },
        {
            "chunk_id": "27_2025_2",
            "content": "Cross-clause payment for UK and Canada...",
            "contextual_content": "[27_2025.md] 13. PAYMENT > cross",
            "metadata": {"doc_type": "contract", "standard": "GAFTA",
                         "jurisdiction": ["Canada", "UK"], "topic": "payment_terms",
                         "source_document": "27_2025.md"},
            "embedding": [0.3] * 1536,
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture(scope="module")
def db_url(tmp_path_factory):
    compose = _compose_cmd()
    if compose is None:
        pytest.skip("Docker / Docker Compose not available")

    base = compose + ["-f", str(COMPOSE_FILE)]
    up = subprocess.run(base + ["up", "-d", "postgres"], capture_output=True, text=True)
    if up.returncode != 0:
        pytest.skip(f"Could not start test database:\n{up.stderr}")

    try:
        # Wait for readiness.
        ready = False
        for _ in range(45):
            try:
                psycopg.connect(TEST_DB_URL).close()
                ready = True
                break
            except psycopg.OperationalError:
                time.sleep(2)
        if not ready:
            pytest.skip("Test database did not become ready in time")

        # Seed via the REAL CLI (exercises DDL + register_vector ordering + upsert).
        jsonl = tmp_path_factory.mktemp("chunks") / "27_2025_processed.jsonl"
        _make_jsonl(jsonl)
        seed = subprocess.run(
            [sys.executable, str(ROOT / "seed_reference_library.py"),
             str(jsonl), "--create-table", "--db-url", TEST_DB_URL],
            capture_output=True, text=True,
        )
        assert seed.returncode == 0, f"seed failed:\nSTDOUT{seed.stdout}\nSTDERR{seed.stderr}"

        yield TEST_DB_URL, jsonl, seed.stdout
    finally:
        subprocess.run(base + ["down", "-v"], capture_output=True)


@pytest.fixture
def conn(db_url):
    url, _, _ = db_url
    with psycopg.connect(url) as connection:
        register_vector(connection)
        yield connection


def test_seed_reports_three_inserts(db_url):
    _, _, stdout = db_url
    assert "Inserted" in stdout and "3" in stdout


def test_row_count(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reference_library")
        assert cur.fetchone()[0] == 3


def test_vector_similarity_returns_closest(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id FROM reference_library ORDER BY embedding <-> %s::vector LIMIT 1",
            ([0.1] * 1536,),
        )
        assert cur.fetchone()[0] == "27_2025_0"


def test_known_gap_returns_empty(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id FROM reference_library WHERE metadata->>'topic' = %s",
            ("non_existent_topic",),
        )
        assert cur.fetchall() == []


def test_jurisdiction_jsonb_filter(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM reference_library WHERE metadata->'jurisdiction' ? 'Canada'")
        ids = {r[0] for r in cur.fetchall()}
        assert {"27_2025_1", "27_2025_2"} <= ids
        assert "27_2025_0" not in ids


def test_topic_filter(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM reference_library WHERE metadata->>'topic' = 'payment_terms'")
        ids = {r[0] for r in cur.fetchall()}
        assert ids == {"27_2025_0", "27_2025_2"}


def test_combined_filter_plus_vector_sort(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT chunk_id FROM reference_library
            WHERE metadata->'jurisdiction' ? 'UK' AND metadata->>'topic' = 'payment_terms'
            ORDER BY embedding <-> %s::vector LIMIT 10
            """,
            ([0.3] * 1536,),
        )
        ids = [r[0] for r in cur.fetchall()]
        assert ids[0] == "27_2025_2"  # closest to [0.3] among UK payment_terms


def test_seed_is_idempotent(db_url):
    """Re-running the seed upserts: row count stays 3, output reports updates."""
    url, jsonl, _ = db_url
    rerun = subprocess.run(
        [sys.executable, str(ROOT / "seed_reference_library.py"),
         str(jsonl), "--db-url", url],
        capture_output=True, text=True,
    )
    assert rerun.returncode == 0, rerun.stderr
    assert "Updated" in rerun.stdout
    with psycopg.connect(url) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM reference_library")
        assert cur.fetchone()[0] == 3
