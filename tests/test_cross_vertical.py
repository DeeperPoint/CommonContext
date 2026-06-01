# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
Cross-vertical validation (ROADMAP Phase 5): the *same* pipeline code path
processes both the grain and the specialty-manufacturing verticals, and each
produces output that validates against its own reference metadata schema.

The manufacturing source here is a synthetic sample spec (real ASTM/ISO/DIN
standards are paywalled); it is representative enough to prove the tooling is
vertical-agnostic.
"""
from __future__ import annotations

import json
import shutil

import provenance as prov
import chunk_and_embed as ce
from reference_metadata_schema import ReferenceMetadata, ManufacturingReferenceMetadata


def _stage(tmp_path, monkeypatch, fixture_path, stem, extracted_metadata):
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(exist_ok=True)
    prov_dir = tmp_path / "prov"
    prov_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(ce, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(prov, "PROVENANCE_DIR", prov_dir)

    md = tmp_path / f"{stem}.md"
    shutil.copy(fixture_path, md)
    prov.recordProvenance(outputStem=stem)
    rec = prov.getProvenance(stem)
    rec["extracted_metadata"] = extracted_metadata
    (prov_dir / f"{stem}.json").write_text(json.dumps(rec), encoding="utf-8")
    return md


async def test_grain_and_manufacturing_share_one_pipeline(
    tmp_path, monkeypatch, patched_pipeline, fixtures_dir
):
    # ── Grain run ─────────────────────────────────────────────────────────────
    grain_md = _stage(
        tmp_path, monkeypatch, fixtures_dir / "sample_grain.md", "sample_grain",
        {
            "document_metadata": {"document_type": "contract"},
            "issuing_organization": {"name": "GAFTA"},
            "geographic_scope": {"jurisdictions": ["Canada"]},
        },
    )
    patched_pipeline["topic_map"].update({"payment": "payment_terms"})
    grain_out = await ce.process_document(
        str(grain_md), "schemas/grain_trade_schema.yaml", vertical="grain"
    )
    grain_records = [json.loads(l) for l in open(grain_out, encoding="utf-8")]

    # ── Manufacturing run (same function, different vertical) ─────────────────
    mfg_md = _stage(
        tmp_path, monkeypatch,
        fixtures_dir / "manufacturing" / "ASTM-B209-AL6061-sample.md",
        "ASTM-B209-AL6061-sample",
        {
            "document_metadata": {"document_type": "specification"},
            "issuing_organization": {"name": "ASTM International"},
            "geographic_scope": {"jurisdictions": ["United States"]},
            "material": {
                "material_class": "aluminum_alloy",
                "export_control_regime": "EAR",
                "process_type": ["rolling", "heat_treatment"],
            },
        },
    )
    patched_pipeline["topic_map"].update({
        "tensile": "mechanical_properties",
        "composition": "chemical_composition",
        "heat treatment": "heat_treatment",
    })
    mfg_out = await ce.process_document(
        str(mfg_md), "schemas/manufacturing_metadata_schema.yaml", vertical="manufacturing"
    )
    mfg_records = [json.loads(l) for l in open(mfg_out, encoding="utf-8")]

    assert grain_records and mfg_records

    # Each vertical's output validates against ITS OWN schema...
    for r in grain_records:
        ReferenceMetadata.model_validate(r["metadata"])
    for r in mfg_records:
        ManufacturingReferenceMetadata.model_validate(r["metadata"])

    # ...and cross-validation fails, proving the schemas are genuinely distinct.
    assert "standard" in grain_records[0]["metadata"]
    assert "standard" not in mfg_records[0]["metadata"]
    assert "material_class" in mfg_records[0]["metadata"]
    assert "material_class" not in grain_records[0]["metadata"]

    # Manufacturing doc-level fields were mapped from provenance.
    assert mfg_records[0]["metadata"]["standard_body"] == "ASTM"
    assert mfg_records[0]["metadata"]["material_class"] == "aluminum_alloy"
    assert mfg_records[0]["metadata"]["export_control_regime"] == "EAR"
