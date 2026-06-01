# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Unit tests for the vertical-aware reference metadata schema."""
from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

import reference_metadata_schema as rms


# ── Grain model ───────────────────────────────────────────────────────────────

def test_grain_valid_record():
    m = rms.ReferenceMetadata(
        doc_type="contract", standard="GAFTA", topic="payment_terms",
        jurisdiction=["Canada"], product_category=["wheat"],
    )
    assert m.standard == "GAFTA"
    assert m.topic == "payment_terms"


def test_grain_general_topic_is_valid():
    """The tagging prompt emits 'general' as a fallback — it must validate."""
    m = rms.ReferenceMetadata(doc_type="contract", topic="general")
    assert m.topic == "general"
    assert m.standard is None  # Optional


def test_grain_rejects_unknown_topic():
    with pytest.raises(ValidationError):
        rms.ReferenceMetadata(doc_type="contract", topic="not_a_real_topic")


def test_grain_rejects_extra_fields():
    with pytest.raises(ValidationError):
        rms.ReferenceMetadata(doc_type="contract", topic="general", bogus="x")


def test_grain_rejects_freeform_standard_name():
    """Full org names must not validate — they should be normalised to acronyms."""
    with pytest.raises(ValidationError):
        rms.ReferenceMetadata(
            doc_type="contract", topic="general",
            standard="Grain and Feed Trade Association (GAFTA)",
        )


# ── Manufacturing model ───────────────────────────────────────────────────────

def test_manufacturing_valid_record():
    m = rms.ManufacturingReferenceMetadata(
        doc_type="specification",
        standard_body="ASTM",
        topic="mechanical_properties",
        material_class="aluminum_alloy",
        export_control_regime="EAR",
        process_type=["rolling"],
        jurisdiction=["United States"],
    )
    assert m.standard_body == "ASTM"
    assert m.material_class == "aluminum_alloy"


def test_manufacturing_optionals_default_none():
    m = rms.ManufacturingReferenceMetadata(doc_type="datasheet", topic="general")
    assert m.standard_body is None
    assert m.material_class is None
    assert m.export_control_regime is None
    assert m.process_type == []


def test_manufacturing_rejects_grain_standard_key():
    with pytest.raises(ValidationError):
        rms.ManufacturingReferenceMetadata(
            doc_type="specification", topic="general", standard="GAFTA",
        )


def test_manufacturing_rejects_unknown_material_class():
    with pytest.raises(ValidationError):
        rms.ManufacturingReferenceMetadata(
            doc_type="specification", topic="general", material_class="unobtanium",
        )


# ── Registry & YAML generation ────────────────────────────────────────────────

def test_registry_resolves_models():
    assert rms.get_model("grain") is rms.ReferenceMetadata
    assert rms.get_model("manufacturing") is rms.ManufacturingReferenceMetadata


def test_registry_unknown_vertical_raises():
    with pytest.raises(KeyError):
        rms.get_model("aerospace")


def test_generate_yaml_grain_has_enum_values():
    text = rms.generate_yaml_schema(rms.ReferenceMetadata)
    data = yaml.safe_load(text)
    fields = data["reference_metadata_schema"]["fields"]
    assert "GAFTA" in fields["standard"]["allowed_values"]
    assert "general" in fields["topic"]["allowed_values"]
    assert fields["jurisdiction"]["type"] == "array"


def test_generate_yaml_manufacturing_has_material_fields():
    text = rms.generate_yaml_schema(rms.ManufacturingReferenceMetadata)
    data = yaml.safe_load(text)
    fields = data["reference_metadata_schema"]["fields"]
    assert "standard_body" in fields
    assert "ISO" in fields["standard_body"]["allowed_values"]
    assert "ASTM" in fields["standard_body"]["allowed_values"]
    assert "DIN" in fields["standard_body"]["allowed_values"]
    assert "material_class" in fields
    assert "export_control_regime" in fields
    assert fields["process_type"]["type"] == "array"
