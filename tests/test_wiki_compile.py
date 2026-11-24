# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""Compiling the wiki into the population generator's contract.

The most important test here is the sequencing gate. The review is explicit that
emitting a rule the generator cannot apply is worse than not supporting the
category at all, because the rule is documented, accepted and silently never
enforced. So an unknown rule type must fail the build, not warn.
"""
from __future__ import annotations

import json

import pytest

from wiki_compile import SUPPORTED_RULE_TYPES, CompileError, compile_wiki, main


def write_page(wiki, rel, front, body="Prose.\n"):
    import yaml

    path = wiki / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    return path


@pytest.fixture
def wiki(tmp_path):
    return tmp_path / "wiki"


def compile_one(wiki, rel, front, body="Prose.\n"):
    write_page(wiki, rel, front, body)
    return compile_wiki(wiki, vertical="manufacturing")


# ── Vocabulary ───────────────────────────────────────────────────────────────
def test_a_vocabulary_page_becomes_a_permitted_value(wiki):
    contract, errors = compile_one(wiki, "vocab/milling.md", {
        "title": "3-axis milling", "type": "vocabulary",
        "field": "processes", "preferred_label": "3-axis milling",
    })
    assert errors == []
    assert contract["permitted_values"]["processes"] == ["3-axis milling"]


def test_alternative_labels_become_retrieval_synonyms(wiki):
    """An exact-term corpus is exactly where a query using the other name for a
    thing finds nothing at all."""
    contract, errors = compile_one(wiki, "vocab/milling.md", {
        "title": "3-axis milling", "type": "vocabulary", "field": "processes",
        "preferred_label": "3-axis milling",
        "alternative_labels": ["3 axis mill", "vertical milling"],
    })
    assert errors == []
    assert contract["synonyms"]["3-axis milling"] == ["3 axis mill", "vertical milling"]


def test_a_vocabulary_page_without_a_field_fails(wiki):
    _, errors = compile_one(wiki, "vocab/x.md", {"title": "x", "type": "vocabulary"})
    assert len(errors) == 1
    assert "field" in errors[0].message


def test_terms_group_under_their_field(wiki):
    write_page(wiki, "vocab/a.md", {"title": "turning", "type": "vocabulary", "field": "processes"})
    write_page(wiki, "vocab/b.md", {"title": "milling", "type": "vocabulary", "field": "processes"})
    write_page(wiki, "vocab/c.md", {"title": "Inconel 718", "type": "vocabulary", "field": "materials"})
    contract, errors = compile_wiki(wiki, vertical="manufacturing")
    assert errors == []
    assert contract["permitted_values"]["processes"] == ["milling", "turning"]
    assert contract["permitted_values"]["materials"] == ["Inconel 718"]


# ── Rules, and the sequencing gate ───────────────────────────────────────────
VALID_RULE = {
    "title": "certifications by headcount", "type": "rule",
    "rule": {
        "type": "conditional_enum",
        "source_field": "headcount",
        "target_fields": ["certifications"],
        "config": {"conditions": [{"when": {"gt": 500}, "allow": ["AS9100D"]}]},
    },
}


def test_a_rule_page_compiles_to_the_generators_shape(wiki):
    """Emitted in SeedRule's own shape, camelCase included, so the contract drops
    into schema_definition.seed_rules with no adapter to drift."""
    contract, errors = compile_one(wiki, "rules/certs.md", VALID_RULE)
    assert errors == []
    rule = contract["seed_rules"][0]
    assert rule["type"] == "conditional_enum"
    assert rule["sourceField"] == "headcount"
    assert rule["targetFields"] == ["certifications"]
    assert rule["severity"] == "error"


def test_an_unsupported_rule_type_fails_the_build(wiki):
    """THE sequencing gate.

    A rule the generator does not implement must not reach the contract. If it
    did, a curator would write a constraint, see it accepted, and get records
    violating it — with nothing anywhere reporting a problem.
    """
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "type": "temporal_window"}}
    contract, errors = compile_one(wiki, "rules/bad.md", bad)
    assert len(errors) == 1
    assert "temporal_window" in errors[0].message
    assert contract["seed_rules"] == [], "the rule must not be emitted"


@pytest.mark.parametrize("rule_type", SUPPORTED_RULE_TYPES)
def test_every_supported_rule_type_compiles(wiki, rule_type):
    page = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "type": rule_type}}
    contract, errors = compile_one(wiki, f"rules/{rule_type}.md", page)
    assert errors == []
    assert contract["seed_rules"][0]["type"] == rule_type


def test_the_contract_records_which_rule_types_it_was_built_against(wiki):
    """So a consumer can tell whether it is reading a contract from a compiler
    that knew about the categories it implements."""
    contract, _ = compile_wiki(wiki, vertical="manufacturing")
    assert contract["supported_rule_types"] == list(SUPPORTED_RULE_TYPES)


def test_a_rule_missing_its_target_fails(wiki):
    bad = {**VALID_RULE, "rule": {k: v for k, v in VALID_RULE["rule"].items() if k != "target_fields"}}
    _, errors = compile_one(wiki, "rules/bad.md", bad)
    assert len(errors) == 1


def test_a_rule_with_an_empty_config_fails(wiki):
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "config": {}}}
    _, errors = compile_one(wiki, "rules/bad.md", bad)
    assert "config" in errors[0].message


def test_a_bad_severity_fails(wiki):
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "severity": "critical"}}
    _, errors = compile_one(wiki, "rules/bad.md", bad)
    assert "severity" in errors[0].message


def test_duplicate_rule_ids_fail(wiki):
    """Otherwise the second silently replaces the first anywhere downstream keys
    the contract by id."""
    write_page(wiki, "rules/a.md", {**VALID_RULE, "id": "shared"})
    write_page(wiki, "rules/b.md", {**VALID_RULE, "id": "shared"})
    contract, errors = compile_wiki(wiki, vertical="manufacturing")
    assert len(errors) == 1
    assert "already used" in errors[0].message
    assert len(contract["seed_rules"]) == 1


# ── Exemplars ────────────────────────────────────────────────────────────────
def test_exemplars_compile_with_provenance(wiki):
    contract, errors = compile_one(wiki, "exemplars/lead.md", {
        "title": "lead times", "type": "exemplar", "field": "lead_time_days",
        "examples": [{"value": 21, "source": "source_cgc"}, {"value": 35}],
    })
    assert errors == []
    assert contract["examples"]["lead_time_days"][0] == {"value": 21, "source": "source_cgc"}
    assert contract["examples"]["lead_time_days"][1]["source"] == ""


def test_bare_scalar_examples_are_accepted(wiki):
    contract, errors = compile_one(wiki, "exemplars/lead.md", {
        "title": "lead times", "type": "exemplar", "field": "lead_time_days",
        "examples": [21, 35],
    })
    assert errors == []
    assert [e["value"] for e in contract["examples"]["lead_time_days"]] == [21, 35]


def test_an_exemplar_page_with_no_examples_fails(wiki):
    _, errors = compile_one(wiki, "exemplars/x.md", {
        "title": "x", "type": "exemplar", "field": "f", "examples": [],
    })
    assert len(errors) == 1


def test_exemplars_for_one_field_merge_across_pages(wiki):
    write_page(wiki, "exemplars/a.md", {"title": "a", "type": "exemplar", "field": "f", "examples": [1]})
    write_page(wiki, "exemplars/b.md", {"title": "b", "type": "exemplar", "field": "f", "examples": [2]})
    contract, errors = compile_wiki(wiki, vertical="manufacturing")
    assert errors == []
    assert len(contract["examples"]["f"]) == 2


# ── Persona axes ─────────────────────────────────────────────────────────────
def test_an_axis_page_compiles(wiki):
    contract, errors = compile_one(wiki, "axes/scale.md", {
        "title": "scale", "type": "axis", "axis": "scale",
        "values": ["sole operator", "small shop", "mid", "enterprise"],
        "field": "headcount",
    })
    assert errors == []
    assert contract["persona_axes"][0]["values"][0] == "sole operator"


def test_an_axis_without_values_fails(wiki):
    _, errors = compile_one(wiki, "axes/x.md", {"title": "x", "type": "axis", "axis": "x"})
    assert len(errors) == 1


# ── Governance ───────────────────────────────────────────────────────────────
def test_a_generation_page_marked_reference_is_rejected(wiki):
    """§6.4: without a purpose axis, seed material gets cited to a participant as
    reference knowledge. A page that overrides its own classification by hand is
    the one case derivation cannot catch, so the compiler catches it."""
    page = {**VALID_RULE, "purpose": "reference"}
    contract, errors = compile_one(wiki, "rules/leaky.md", page)
    assert len(errors) == 1
    assert "participant" in errors[0].message
    assert contract["seed_rules"] == []


def test_ordinary_pages_are_ignored(wiki):
    """The wiki is mostly concept, layer and source pages. Compiling is additive:
    it reads the page types that opt in and leaves everything else alone."""
    write_page(wiki, "concepts/a.md", {"title": "a", "type": "concept"})
    write_page(wiki, "layers/b.md", {"title": "b", "type": "layer"})
    write_page(wiki, "sources/c.md", {"title": "c", "type": "source"})
    contract, errors = compile_wiki(wiki, vertical="manufacturing")
    assert errors == []
    assert contract["seed_rules"] == []
    assert contract["permitted_values"] == {}


def test_generated_meta_files_are_skipped(wiki):
    write_page(wiki, "index.md", {"title": "Index", "type": "vocabulary", "field": "f"})
    contract, errors = compile_wiki(wiki, vertical="manufacturing")
    assert errors == []
    assert contract["permitted_values"] == {}


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_check_mode_exits_nonzero_on_a_bad_rule(wiki, capsys):
    bad = {**VALID_RULE, "rule": {**VALID_RULE["rule"], "type": "nope"}}
    write_page(wiki, "rules/bad.md", bad)
    assert main(["--wiki", str(wiki), "--check"]) == 1


def test_check_mode_writes_nothing(wiki, tmp_path):
    write_page(wiki, "rules/ok.md", VALID_RULE)
    out = tmp_path / "contract.json"
    assert main(["--wiki", str(wiki), "--check", "-o", str(out)]) == 0
    assert not out.exists()


def test_writing_the_contract(wiki, tmp_path):
    write_page(wiki, "rules/ok.md", VALID_RULE)
    out = tmp_path / "nested" / "contract.json"
    assert main(["--wiki", str(wiki), "-o", str(out), "--vertical", "manufacturing"]) == 0

    contract = json.loads(out.read_text(encoding="utf-8"))
    assert contract["vertical"] == "manufacturing"
    assert contract["contract_version"]
    assert len(contract["seed_rules"]) == 1
