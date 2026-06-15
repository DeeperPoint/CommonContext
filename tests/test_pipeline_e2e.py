# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
End-to-end test of the chunk → tag → embed → JSONL pipeline with the two paid
external services (OpenRouter, OpenAI) replaced by deterministic fakes
(see conftest.patched_pipeline). Proves the pipeline produces schema-valid,
frontmatter-free output without network access.
"""
from __future__ import annotations

import json
import shutil

import provenance as prov
import chunk_and_embed as ce
from reference_metadata_schema import ReferenceMetadata

GRAIN_SCHEMA = "schemas/grain_trade_schema.yaml"


def _write_grain_provenance(stem: str):
    prov.recordProvenance(outputStem=stem)
    # Inject an extracted_metadata block as metadata_extractor would.
    rec = prov.getProvenance(stem)
    rec["extracted_metadata"] = {
        "document_metadata": {"document_type": "contract"},
        "issuing_organization": {"name": "Grain and Feed Trade Association (GAFTA)"},
        "geographic_scope": {"jurisdictions": ["Canada", "United States"]},
    }
    (prov.PROVENANCE_DIR / f"{stem}.json").write_text(
        json.dumps(rec), encoding="utf-8"
    )


async def test_pipeline_produces_schema_valid_output(
    tmp_path, monkeypatch, patched_pipeline, fixtures_dir
):
    # Redirect outputs/ and provenance/ into the tmp sandbox.
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    monkeypatch.setattr(ce, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path / "prov")
    (tmp_path / "prov").mkdir()

    # Stage the fixture as outputs/sample_grain.md (stem drives provenance lookup).
    md = tmp_path / "sample_grain.md"
    shutil.copy(fixtures_dir / "sample_grain.md", md)
    _write_grain_provenance("sample_grain")

    # Map chunk content to deterministic topics so we assert real tagging wiring.
    patched_pipeline["topic_map"].update({
        "payment": "payment_terms",
        "arbitration": "dispute_resolution",
        "goods": "goods",
    })

    out_path = await ce.process_document(str(md), GRAIN_SCHEMA, vertical="grain")
    records = [json.loads(l) for l in open(out_path, encoding="utf-8")]

    assert records, "pipeline produced no chunks"

    # 1. Frontmatter must never appear as chunk content (regression guard).
    for r in records:
        assert "source_url" not in r["content"]
        assert not r["content"].lstrip().startswith("---")

    # 2. Every record matches the DECISION-005 structure.
    for i, r in enumerate(records):
        assert r["chunk_id"] == f"sample_grain_{i}"
        assert set(r.keys()) == {
            "chunk_id", "content", "contextual_content", "metadata", "embedding"
        }
        assert isinstance(r["embedding"], list) and len(r["embedding"]) == 1536
        assert all(isinstance(x, float) for x in r["embedding"][:5])
        assert r["contextual_content"].startswith("[sample_grain.md]")

    # 3. Metadata validates against the grain reference schema (strict, extra-forbid).
    for r in records:
        ReferenceMetadata.model_validate(r["metadata"])

    # 4. The free-form org name was normalised to the enum acronym.
    assert all(r["metadata"]["standard"] == "GAFTA" for r in records)

    # 5. Deterministic topic tagging propagated.
    topics = {r["metadata"]["topic"] for r in records}
    assert "payment_terms" in topics
    assert "dispute_resolution" in topics

    # 6. Embeddings were requested exactly once (batched), one vector per chunk.
    assert len(patched_pipeline["embed_calls"]) == 1
    assert patched_pipeline["embed_calls"][0]["n"] == len(records)


async def test_off_vocabulary_topic_is_coerced(
    tmp_path, monkeypatch, patched_pipeline, fixtures_dir
):
    """A topic the schema doesn't allow must be coerced to 'general'."""
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    monkeypatch.setattr(ce, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path / "prov")
    (tmp_path / "prov").mkdir()

    md = tmp_path / "sample_grain.md"
    shutil.copy(fixtures_dir / "sample_grain.md", md)

    # Make the fake tagger emit a value outside the grain topic enum.
    patched_pipeline["default_topic"]["value"] = "totally_made_up_topic"

    out_path = await ce.process_document(str(md), GRAIN_SCHEMA, vertical="grain")
    records = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    assert records
    assert all(r["metadata"]["topic"] == "general" for r in records)
    for r in records:
        ReferenceMetadata.model_validate(r["metadata"])


async def test_pipeline_unknown_org_yields_null_standard(
    tmp_path, monkeypatch, patched_pipeline, fixtures_dir
):
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    monkeypatch.setattr(ce, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(prov, "PROVENANCE_DIR", tmp_path / "prov")
    (tmp_path / "prov").mkdir()

    md = tmp_path / "sample_grain.md"
    shutil.copy(fixtures_dir / "sample_grain.md", md)
    # No provenance record at all → defaults, standard=None.

    out_path = await ce.process_document(str(md), GRAIN_SCHEMA, vertical="grain")
    records = [json.loads(l) for l in open(out_path, encoding="utf-8")]
    assert all(r["metadata"]["standard"] is None for r in records)
    assert all(r["metadata"]["doc_type"] == "other" for r in records)
    for r in records:
        ReferenceMetadata.model_validate(r["metadata"])
