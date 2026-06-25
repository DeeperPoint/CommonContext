# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Literal, Optional, Type

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ReferenceMetadata(BaseModel):
    """
    Reference Metadata Schema for the Grain Trading Vertical.

    This model defines the exact field names and enum values for the Knowledge Slot's
    reference documents (contracts, regulations, standards, etc.). It acts as the
    single source of truth for the gap detection prompt, Q&A prompts, and the
    `reference_library` table in Cosolvent.
    """

    model_config = ConfigDict(
        use_enum_values=True,
        extra="forbid",
        json_schema_extra={
            "description": "Metadata attached to each document and vector chunk in the Knowledge Slot reference library."
        }
    )

    doc_type: Literal[
        "contract",
        "standard",
        "regulation",
        "guide",
        "report",
        "specification",
        "legislation",
        "policy",
        "manual",
        "article",
        "other"
    ] = Field(
        description="The type of the reference document."
    )

    standard: Optional[Literal[
        "GAFTA",
        "CGC",
        "USDA",
        "FGIS",
        "IUA",
        "ICC",
        "ISO"
    ]] = Field(
        default=None,
        description="The standard body or framework this document belongs to."
    )

    topic: Literal[
        "goods",
        "quantity",
        "pricing",
        "delivery_terms",
        "brokerage",
        "quality_requirements",
        "shipment",
        "appropriation",
        "payment_terms",
        "duties_and_taxes",
        "discharge",
        "weighing",
        "sampling_and_analysis",
        "insurance",
        "force_majeure",
        "default",
        "insolvency",
        "dispute_resolution",
        "circle_trading",
        "notices",
        # Catch-all emitted by the tagging prompt when no specific topic matches.
        # Kept in the enum so real pipeline output validates against this schema.
        "general",
    ] = Field(
        description="Specific topic or clause theme. Used to semantically tag chunks."
    )

    jurisdiction: List[str] = Field(
        default_factory=list,
        description="Countries or regions the document applies to."
    )

    product_category: List[str] = Field(
        default_factory=list,
        description="Grain commodities this document covers."
    )


class ManufacturingReferenceMetadata(BaseModel):
    """
    Reference Metadata Schema for the Specialty Manufacturing Vertical.

    Demonstrates that the same Knowledge Slot tooling generalises to a second
    vertical (ROADMAP Phase 5). The tag vocabulary follows ROADMAP §2.2:
    `material_class`, `standard_body` (ISO / ASTM / DIN), `export_control_regime`,
    `process_type`. Manufacturing reference content starts from material
    specifications and yields a heavily tabular schema (DECISION-000 §6).
    """

    model_config = ConfigDict(
        use_enum_values=True,
        extra="forbid",
        json_schema_extra={
            "description": "Metadata attached to each document and vector chunk in the specialty manufacturing Knowledge Slot reference library."
        }
    )

    doc_type: Literal[
        "specification",
        "standard",
        "datasheet",
        "test_method",
        "drawing",
        "regulation",
        "guide",
        "report",
        "manual",
        "certificate",
        "other",
    ] = Field(
        description="The type of the reference document."
    )

    # Renamed from `standard` to `standard_body` per ROADMAP §2.2 manufacturing tags.
    standard_body: Optional[Literal[
        "ISO",
        "ASTM",
        "DIN",
        "EN",
        "JIS",
        "SAE",
        "ANSI",
        "MIL",
    ]] = Field(
        default=None,
        description="The standards body or framework this document belongs to (ISO / ASTM / DIN / ...)."
    )

    topic: Literal[
        "chemical_composition",
        "mechanical_properties",
        "dimensional_tolerance",
        "surface_finish",
        "heat_treatment",
        "testing_inspection",
        "marking_certification",
        "packaging_handling",
        "storage_shelf_life",
        "process_requirements",
        "safety_handling",
        "general",
    ] = Field(
        description="Specific topic or clause theme. Used to semantically tag chunks."
    )

    material_class: Optional[Literal[
        "aluminum_alloy",
        "carbon_steel",
        "stainless_steel",
        "titanium_alloy",
        "nickel_alloy",
        "copper_alloy",
        "polymer",
        "composite",
        "ceramic",
        "other",
    ]] = Field(
        default=None,
        description="Primary material class the document specifies."
    )

    export_control_regime: Optional[Literal[
        "EAR",
        "ITAR",
        "EU_dual_use",
        "none",
    ]] = Field(
        default=None,
        description="Export control regime governing the material or process, if any."
    )

    process_type: List[str] = Field(
        default_factory=list,
        description="Manufacturing processes the document covers (machining, casting, forging, additive, welding, heat_treatment, coating)."
    )

    jurisdiction: List[str] = Field(
        default_factory=list,
        description="Countries or regions the document applies to."
    )


# ── Vertical registry ────────────────────────────────────────────────────────
# Maps a vertical name to its metadata model and the output YAML filename.
# This is what makes the curation tooling vertical-agnostic: the same pipeline
# selects a model here rather than hardcoding grain fields.

VERTICALS: dict[str, Type[BaseModel]] = {
    "grain": ReferenceMetadata,
    "manufacturing": ManufacturingReferenceMetadata,
}

_YAML_FILENAMES = {
    "grain": "reference_metadata_schema.yaml",
    "manufacturing": "manufacturing_metadata_schema.yaml",
}


def get_model(vertical: str = "grain") -> Type[BaseModel]:
    """Return the pydantic metadata model for a vertical."""
    if vertical not in VERTICALS:
        raise KeyError(
            f"Unknown vertical {vertical!r}. Known verticals: {sorted(VERTICALS)}"
        )
    return VERTICALS[vertical]


def get_allowed_topics(vertical: str = "grain") -> list[str]:
    """Return the exact allowed `topic` enum values for a vertical.

    Used to constrain the chunk-tagging LLM so it can only emit valid topics —
    the single source of truth is the pydantic model, not the prompt text.
    """
    from typing import get_args, get_type_hints

    model = get_model(vertical)
    hints = get_type_hints(model)
    return list(get_args(hints["topic"]))


def generate_yaml_schema(model: Type[BaseModel] = ReferenceMetadata) -> str:
    """Generates the YAML configuration for the Cosolvent system.

    Accepts any vertical's metadata model so the same generator serves every
    vertical. Defaults to the grain model for backward compatibility.
    """
    schema_dict = model.model_json_schema()

    output = {
        "schema_version": "1.0",
        "reference_metadata_schema": {
            "fields": {}
        }
    }

    fields = output["reference_metadata_schema"]["fields"]

    for field_name, field_info in schema_dict.get("properties", {}).items():
        base_type = field_info.get("type", "string")

        # Pydantic encodes Optional[Literal] with anyOf containing type 'null'.
        if "anyOf" in field_info:
            for item in field_info["anyOf"]:
                if item.get("type") == "string":
                    if "enum" in item:
                         base_type = "enum"
                         fields[field_name] = {
                             "type": "enum",
                             "allowed_values": item["enum"],
                             "description": field_info.get("description", "")
                         }
                    else:
                         fields[field_name] = {
                             "type": "string",
                             "description": field_info.get("description", "")
                         }
                    break
        elif "enum" in field_info:
             fields[field_name] = {
                 "type": "enum",
                 "allowed_values": field_info["enum"],
                 "description": field_info.get("description", "")
             }
        else:
             fields[field_name] = {
                 "type": base_type,
                 "description": field_info.get("description", "")
             }
             if base_type == "array":
                 items = field_info.get("items", {})
                 fields[field_name]["item_type"] = items.get("type", "string")

    return yaml.dump(output, sort_keys=False, default_flow_style=False)


def _write_yaml(vertical: str) -> Path:
    """Generate and write the YAML schema for a vertical. Returns the path."""
    model = get_model(vertical)
    yaml_content = generate_yaml_schema(model)
    output_path = Path(__file__).parent / _YAML_FILENAMES[vertical]
    with output_path.open("w", encoding="utf-8") as f:
        f.write("# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.\n")
        f.write("#\n")
        f.write("# This file is auto-generated by reference_metadata_schema.py. DO NOT EDIT MANUALLY.\n")
        f.write(f"# Vertical: {vertical}\n")
        f.write("# It defines the tag vocabulary for the Cosolvent `reference_library` table\n")
        f.write("# and is part of the Knowledge Slot vertical configuration.\n\n")
        f.write(yaml_content)
    return output_path


if __name__ == "__main__":
    # Generate the YAML for one vertical (default grain) or all of them.
    #   python reference_metadata_schema.py            -> grain
    #   python reference_metadata_schema.py manufacturing
    #   python reference_metadata_schema.py --all
    args = sys.argv[1:]
    if args and args[0] == "--all":
        targets = list(VERTICALS)
    elif args:
        targets = [args[0]]
    else:
        targets = ["grain"]

    for vertical in targets:
        path = _write_yaml(vertical)
        print(f"Generated YAML schema for '{vertical}' at {path}")
