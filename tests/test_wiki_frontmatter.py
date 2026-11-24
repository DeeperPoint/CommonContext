# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""The wiki page frontmatter contract, and the derivation that makes it adoptable.

The derivation tests matter more than the validation ones. A contract that only
holds for pages written after it was published governs nothing: the corpus that
exists is the corpus that reaches retrieval. So most of what follows pins down
how a page that declares none of the four axes is read.
"""
from __future__ import annotations

import pytest

from wiki_frontmatter import (
    EDITORIAL_STANDINGS,
    EVIDENCE_CLASSES,
    GOVERNANCE_FIELDS,
    OWNERSHIP_LAYERS,
    PURPOSES,
    derive_governance,
    is_citable,
    load_schema,
    validate_frontmatter,
)


# ── The published contract ───────────────────────────────────────────────────
def test_schema_declares_the_four_axes_with_the_same_vocabularies_as_the_module():
    """The JSON file is the contract; the module must not drift from it."""
    props = load_schema()["properties"]
    expected = {
        "ownership_layer": OWNERSHIP_LAYERS,
        "editorial_standing": EDITORIAL_STANDINGS,
        "evidence_class": EVIDENCE_CLASSES,
        "purpose": PURPOSES,
    }
    for field, vocabulary in expected.items():
        assert field in props, f"{field} missing from the published schema"
        assert tuple(props[field]["enum"]) == vocabulary


def test_title_and_type_are_required():
    assert validate_frontmatter({}) != []
    assert validate_frontmatter({"title": "T", "type": "concept"}) == []


def test_off_vocabulary_axis_value_is_rejected():
    errors = validate_frontmatter({"title": "T", "type": "concept", "purpose": "whatever"})
    assert any("purpose" in e for e in errors)


def test_status_is_not_constrained_to_the_editorial_vocabulary():
    """Two wikis use `status` with different meanings.

    One writes draft/reviewed/signed_off and means review state; the other
    writes `status: active` on a catalogue page and means the catalogue is live.
    Pinning the key to one reading would be the name collision the contract
    exists to prevent, so `editorial_standing` carries review state instead.
    """
    assert validate_frontmatter({"title": "Catalogue", "type": "concept", "status": "active"}) == []


# ── Derivation: pages that declare nothing ───────────────────────────────────
def test_a_bare_page_resolves_every_axis():
    gov = derive_governance({"title": "T", "type": "concept"})
    assert set(gov) == set(GOVERNANCE_FIELDS)
    assert gov["ownership_layer"] == "upstream"
    assert gov["editorial_standing"] == "draft"
    assert gov["purpose"] == "reference"


def test_scenario_pages_are_demo_invented_and_generation_only():
    """The case the purpose axis exists for.

    A scenario is a fictional composite. It can be well written and signed off
    and still describe no real person, so editorial standing cannot keep it out
    of a participant-facing citation. Purpose can.
    """
    gov = derive_governance({"title": "Background checks", "type": "scenario", "status": "signed_off"})
    assert gov["editorial_standing"] == "signed_off"
    assert gov["evidence_class"] == "demo_invented"
    assert gov["purpose"] == "generation"
    assert not is_citable(gov)


def test_a_page_citing_sources_is_source_backed():
    gov = derive_governance({"title": "T", "type": "concept", "sources": ["trc_2015"]})
    assert gov["evidence_class"] == "source_backed"
    assert is_citable(gov)


def test_a_page_citing_nothing_is_interpretive():
    assert derive_governance({"title": "T", "type": "concept"})["evidence_class"] == "interpretive"


@pytest.mark.parametrize(
    "review_status,expected",
    [("signed_off", "signed_off"), ("approved", "signed_off"), ("reviewed", "reviewed"),
     ("public_sources", "draft"), ("", "draft")],
)
def test_editorial_standing_reads_the_second_wikis_review_status(review_status, expected):
    fm = {"title": "T", "type": "layer", "review_status": review_status}
    assert derive_governance(fm)["editorial_standing"] == expected


# ── Derivation: provenance tags ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "tags,expected",
    [
        (["W", "W"], "source_backed"),
        (["I", "I", "W"], "interpretive"),
        (["D"], "demo_invented"),
        # Ties break toward the more cautious class — a page half demo-invented
        # is demo-invented, never averaged into source-backed.
        (["W", "D"], "demo_invented"),
        (["W", "I"], "interpretive"),
    ],
)
def test_evidence_class_follows_provenance_tags(tags, expected):
    fm = {"title": "T", "type": "concept", "provenance": [{"section": "s", "tag": t} for t in tags]}
    assert derive_governance(fm)["evidence_class"] == expected


def test_an_explicit_axis_beats_derivation():
    fm = {"title": "T", "type": "scenario", "purpose": "reference", "evidence_class": "source_backed"}
    gov = derive_governance(fm)
    assert gov["purpose"] == "reference"
    assert gov["evidence_class"] == "source_backed"
    assert is_citable(gov)


def test_ownership_layer_defaults_to_upstream_not_local():
    """A page that forgot to declare itself is shared material.

    Reading it as twin-local would licence edits upstream never agreed to.
    """
    assert derive_governance({"title": "T", "type": "concept"})["ownership_layer"] == "upstream"
    assert derive_governance(
        {"title": "T", "type": "concept", "ownership_layer": "local"}
    )["ownership_layer"] == "local"


# ── The citability policy ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "gov,citable",
    [
        ({"purpose": "reference", "evidence_class": "source_backed"}, True),
        ({"purpose": "reference", "evidence_class": "interpretive"}, True),
        ({"purpose": "reference", "evidence_class": "provisional"}, True),
        ({"purpose": "both", "evidence_class": "source_backed"}, True),
        ({"purpose": "generation", "evidence_class": "source_backed"}, False),
        ({"purpose": "reference", "evidence_class": "demo_invented"}, False),
    ],
)
def test_is_citable(gov, citable):
    assert is_citable(gov) is citable
