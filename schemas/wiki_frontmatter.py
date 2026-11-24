# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""Read and enforce the wiki page frontmatter contract.

`wiki_page_frontmatter.schema.json` is the published contract. This module is how
the rest of the toolchain consumes it: it validates a page's frontmatter against
the schema, and — the part that matters in practice — *derives* the four
governance axes for pages written before the contract existed.

Derivation is what makes the contract adoptable. The two wikis in the programme
hold several hundred pages between them and use different local vocabularies:
one writes `status` + W/D/I `provenance`, the other writes `review_status`,
`share` and a typed folder. Requiring an edit to every page before any of this
works would have meant the contract never landed. Instead every axis has a
defined reading for a page that declares nothing, taken from what the page
already says.

The axes, and why each is separate:

  ownership_layer     who may edit the page (upstream shared wiki | local twin)
  editorial_standing  how far it moved through review (draft|reviewed|signed_off)
  evidence_class      what kind of claim it makes (source_backed|interpretive|
                      demo_invented|provisional)
  purpose             what it is FOR (reference: may be cited to a participant |
                      generation: seed material that must not be | both)

`purpose` is the one a reader tends to think is redundant. It is not: a scenario
page is curated, carefully written, often signed off — and is a fictional
composite. Editorial standing says it is good work. Only `purpose` says it must
never be quoted to a participant as fact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent / "wiki_page_frontmatter.schema.json"

GOVERNANCE_FIELDS = ("ownership_layer", "editorial_standing", "evidence_class", "purpose")

OWNERSHIP_LAYERS = ("upstream", "local")
EDITORIAL_STANDINGS = ("draft", "reviewed", "signed_off")
EVIDENCE_CLASSES = ("source_backed", "interpretive", "demo_invented", "provisional")
PURPOSES = ("reference", "generation", "both")

_ENUMS: dict[str, tuple[str, ...]] = {
    "ownership_layer": OWNERSHIP_LAYERS,
    "editorial_standing": EDITORIAL_STANDINGS,
    "evidence_class": EVIDENCE_CLASSES,
    "purpose": PURPOSES,
}

# Page types whose content exists to seed generation, not to be quoted back to a
# participant. A scenario is the motivating case: a fictional composite, written
# to illustrate a situation, describing no real person or employer.
_GENERATION_TYPES = {
    "scenario",
    "scenarios",
    "exemplar",
    "exemplars",
    "vocabulary",
    "rule",
    "rules",
    "persona",
    "axis",
    "axes",
}

# Page types that are a record of an external document, so source-backed by
# construction unless the page says otherwise.
_SOURCE_TYPES = {"source", "sources", "reference", "references"}

_PROVENANCE_TO_EVIDENCE = {"W": "source_backed", "D": "demo_invented", "I": "interpretive"}

# Ties break toward the more cautious class: a page half demo-invented is treated
# as demo-invented, never averaged into source-backed.
_EVIDENCE_CAUTION_ORDER = ("demo_invented", "provisional", "interpretive", "source_backed")


def load_schema() -> dict[str, Any]:
    """The published frontmatter contract, as a dict."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ── Derivation ───────────────────────────────────────────────────────────────
def _page_type(fm: dict) -> str:
    return str(fm.get("type") or "").strip().lower()


def _declared(fm: dict, field: str) -> str | None:
    """An explicitly declared axis value, if it is in the controlled vocabulary."""
    value = fm.get(field)
    if isinstance(value, str) and value in _ENUMS[field]:
        return value
    return None


def derive_ownership_layer(fm: dict) -> str:
    """Repository ownership. Upstream unless the page claims otherwise.

    Defaulting to upstream is the safe reading: a page in the shared wiki that
    forgot to declare itself is shared material, and treating shared material as
    twin-local would licence edits that upstream never agreed to.
    """
    return _declared(fm, "ownership_layer") or "upstream"


def derive_editorial_standing(fm: dict) -> str:
    """How far through review. Reads `status`, then `review_status`, else draft."""
    explicit = _declared(fm, "editorial_standing")
    if explicit:
        return explicit

    status = str(fm.get("status") or "").strip().lower()
    if status in EDITORIAL_STANDINGS:
        return status

    # The second wiki records review state as prose rather than an enum.
    review = str(fm.get("review_status") or "").strip().lower()
    if review in {"signed_off", "approved", "sign_off"}:
        return "signed_off"
    if review in {"reviewed", "peer_reviewed"}:
        return "reviewed"

    # "public_sources" means built from published material and not yet read by a
    # reviewer — which is a draft, however carefully it was written.
    return "draft"


def derive_evidence_class(fm: dict) -> str:
    """What kind of claim the page makes.

    Preference order: an explicit declaration, then the page's own W/D/I
    provenance tags, then its type, then whether it cites anything at all.
    """
    explicit = _declared(fm, "evidence_class")
    if explicit:
        return explicit

    mix: dict[str, int] = {}
    for item in fm.get("provenance") or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag", "")).upper()[:1]
        klass = _PROVENANCE_TO_EVIDENCE.get(tag)
        if klass:
            mix[klass] = mix.get(klass, 0) + 1
    if mix:
        top = max(mix.values())
        tied = [k for k, v in mix.items() if v == top]
        for candidate in _EVIDENCE_CAUTION_ORDER:
            if candidate in tied:
                return candidate

    ptype = _page_type(fm)
    if ptype in _GENERATION_TYPES:
        # Illustrative material. It describes nothing real, whoever signed it off.
        return "demo_invented"
    if ptype in _SOURCE_TYPES:
        return "source_backed"

    if fm.get("sources") or fm.get("source_url"):
        return "source_backed"
    return "interpretive"


def derive_purpose(fm: dict) -> str:
    """Whether the page may be cited to a participant, or only seeds generation."""
    explicit = _declared(fm, "purpose")
    if explicit:
        return explicit
    if _page_type(fm) in _GENERATION_TYPES:
        return "generation"
    return "reference"


def derive_governance(fm: dict) -> dict[str, str]:
    """All four axes resolved for one page, declared or derived."""
    return {
        "ownership_layer": derive_ownership_layer(fm),
        "editorial_standing": derive_editorial_standing(fm),
        "evidence_class": derive_evidence_class(fm),
        "purpose": derive_purpose(fm),
    }


def is_citable(governance: dict[str, str]) -> bool:
    """Whether a chunk carrying this governance may be quoted to a participant.

    Generation-only material never is. Nor is anything demo-invented: the point
    of the class is that it describes nothing real.
    """
    return governance.get("purpose") != "generation" and governance.get("evidence_class") != "demo_invented"


# ── Validation ───────────────────────────────────────────────────────────────
def _validate_with_jsonschema(fm: dict) -> list[str] | None:
    """Full schema validation, when the library is installed. None if it is not."""
    try:
        import jsonschema
    except ImportError:
        return None
    validator = jsonschema.Draft202012Validator(load_schema())
    return [
        f"{'/'.join(str(p) for p in err.path) or '(root)'}: {err.message}"
        for err in sorted(validator.iter_errors(fm), key=lambda e: list(e.path))
    ]


def _validate_builtin(fm: dict) -> list[str]:
    """Dependency-free fallback: required fields and controlled vocabularies.

    These are everything the schema actually constrains beyond JSON types, so a
    checkout without `jsonschema` still enforces the part that governs retrieval.
    """
    errors: list[str] = []
    for field in ("title", "type"):
        value = fm.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field}: required, must be a non-empty string")

    for field, allowed in _ENUMS.items():
        value = fm.get(field)
        if value is not None and value not in allowed:
            errors.append(f"{field}: {value!r} is not one of {list(allowed)}")

    # `status` is intentionally unconstrained — see the schema's note on it. Two
    # wikis use the key with different meanings, and forcing one reading on the
    # other is the collision this contract exists to prevent.
    for item in fm.get("provenance") or []:
        if isinstance(item, dict) and str(item.get("tag", "")).upper()[:1] not in {"W", "D", "I"}:
            errors.append(f"provenance: tag {item.get('tag')!r} is not one of ['W', 'D', 'I']")

    return errors


def validate_frontmatter(fm: dict) -> list[str]:
    """Validate one page's frontmatter. Empty list means it conforms."""
    if not isinstance(fm, dict):
        return ["(root): frontmatter is not a mapping"]
    via_library = _validate_with_jsonschema(fm)
    return via_library if via_library is not None else _validate_builtin(fm)
