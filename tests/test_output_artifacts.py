# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
Structural validation of any on-disk processed JSONL artifacts in outputs/.

This is a shape check (the fields and embedding dimensions a downstream
pgvector seed requires), independent of which vertical produced the file.
Schema-enum conformance of freshly produced output is covered by
test_pipeline_e2e / test_cross_vertical.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ARTIFACTS = sorted(Path("outputs").glob("*_processed.jsonl"))

REQUIRED_KEYS = {"chunk_id", "content", "contextual_content", "metadata", "embedding"}


@pytest.mark.skipif(not ARTIFACTS, reason="no processed JSONL artifacts on disk")
@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_artifact_structure(path):
    seen_ids = set()
    line_count = 0
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            line_count += 1
            rec = json.loads(raw)
            missing = REQUIRED_KEYS - rec.keys()
            assert not missing, f"{path.name}:{lineno} missing {missing}"

            assert isinstance(rec["embedding"], list), f"{path.name}:{lineno} embedding not a list"
            assert len(rec["embedding"]) == 1536, (
                f"{path.name}:{lineno} embedding dim {len(rec['embedding'])} != 1536"
            )
            assert isinstance(rec["metadata"], dict)
            assert rec["chunk_id"] not in seen_ids, f"duplicate chunk_id {rec['chunk_id']}"
            seen_ids.add(rec["chunk_id"])

    assert line_count > 0, f"{path.name} is empty"
