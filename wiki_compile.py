# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""wiki_compile.py — compile the wiki into a generation contract.

One curated source, three build artefacts. The wiki already emits retrieval
chunks; this emits the second artefact — the contract the population generator
reads — from pages a curator writes in the same place, in the same review
process, as everything else they curate.

What this closes: the generator's permitted values, its domain rules and its
example values live in code and in a hand-populated store, while the knowledge
they encode lives in the wiki. The two drift, silently, and the drift shows up
as a synthetic population that contradicts the reference library the same system
answers questions from.

Three page types, each one page per thing, so a page can be reviewed, cited,
superseded and linked like any other:

  type: vocabulary   one controlled term, and which participant field it applies
                     to. Compiles to the generator's permitted values, and its
                     alternative labels are emitted as retrieval synonyms.
  type: rule         one domain constraint, in one of the four categories the
                     generator implements. Compiles to a SeedRule.
  type: exemplar     realistic values for one field, with provenance. Compiles
                     to the generator's example path.
  type: axis         a dimension of real variation in the market (§6.3). Belongs
                     beside the vocabulary rather than inside a prompt.

THE SEQUENCING GATE

The review is explicit that emitting a rule the generator cannot apply is worse
than not supporting it: the rule is documented, accepted, and silently not
enforced. So every rule is checked against the categories the generator actually
implements, and an unknown category is a hard error that fails the compile — not
a warning, and not a rule quietly dropped from the output.

The list below is the contract with ClientSynth's RuleType. If a category is
added there, add it here; if one is removed there, compiles that emit it start
failing here, which is the intended direction of breakage.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent

_SCHEMAS_DIR = HERE / "schemas"
if str(_SCHEMAS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCHEMAS_DIR))
from wiki_frontmatter import derive_governance  # noqa: E402

CONTRACT_VERSION = "1.0"

# The four categories ClientSynth's RuleValidator interprets. Kept in sync by
# hand and asserted by the compiler; see the module docstring.
SUPPORTED_RULE_TYPES = ("dependency", "exclusion", "conditional_enum", "range_constraint")

PAGE_TYPES = ("vocabulary", "rule", "exemplar", "axis")


class CompileError(Exception):
    """A page that cannot be compiled. Carries the page path for the report."""

    def __init__(self, page: str, message: str):
        super().__init__(f"{page}: {message}")
        self.page = page
        self.message = message


# ── Page reading ─────────────────────────────────────────────────────────────
_FENCE = "---"


def read_page(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter, body). Tolerates a leading HTML comment."""
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
    if text.startswith("<!--"):
        end = text.find("-->")
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    if not text.startswith(_FENCE):
        return {}, text
    rest = text[len(_FENCE):].lstrip("\n")
    close = rest.find(f"\n{_FENCE}")
    if close == -1:
        return {}, text
    try:
        front = yaml.safe_load(rest[:close]) or {}
    except yaml.YAMLError:
        front = {}
    body = rest[close + len(_FENCE) + 1:].lstrip("\n")
    return (front if isinstance(front, dict) else {}), body


def iter_pages(wiki_dir: Path) -> list[tuple[Path, dict[str, Any], str]]:
    """Every markdown page under wiki_dir, excluding generated meta files."""
    skip = {"index.md", "log.md", "CONVENTIONS.md", "lint-report.md"}
    pages = []
    for path in sorted(wiki_dir.rglob("*.md")):
        if path.name in skip:
            continue
        front, body = read_page(path)
        if front:
            pages.append((path, front, body))
    return pages


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


# ── Compilers, one per page type ─────────────────────────────────────────────
def compile_vocabulary(page: str, front: dict[str, Any]) -> dict[str, Any]:
    field = front.get("field")
    if not field:
        raise CompileError(page, "a vocabulary page must name the `field` it constrains")

    preferred = front.get("preferred_label") or front.get("title")
    if not preferred:
        raise CompileError(page, "a vocabulary page must have a `preferred_label`")

    return {
        "field": str(field),
        "preferred_label": str(preferred),
        "alternative_labels": _as_list(front.get("alternative_labels")),
        "broader": _as_list(front.get("broader")),
        "narrower": _as_list(front.get("narrower")),
        "source_page": page,
    }


def compile_rule(page: str, front: dict[str, Any]) -> dict[str, Any]:
    spec = front.get("rule")
    if not isinstance(spec, dict):
        raise CompileError(page, "a rule page must carry a `rule:` mapping")

    rule_type = str(spec.get("type") or "")
    if rule_type not in SUPPORTED_RULE_TYPES:
        # The sequencing gate. Emitting this would produce a rule the generator
        # accepts and never applies.
        raise CompileError(
            page,
            f"rule type {rule_type!r} is not one the generator implements "
            f"({', '.join(SUPPORTED_RULE_TYPES)}). Emitting it would be documented "
            f"but silently unenforced.",
        )

    source_field = spec.get("source_field")
    if not source_field:
        raise CompileError(page, "a rule must name a `source_field`")

    target_fields = _as_list(spec.get("target_fields"))
    if not target_fields:
        raise CompileError(page, "a rule must name at least one entry in `target_fields`")

    config = spec.get("config")
    if not isinstance(config, dict) or not config:
        raise CompileError(page, "a rule must carry a non-empty `config`")

    severity = spec.get("severity", "error")
    if severity not in ("error", "warning"):
        raise CompileError(page, f"severity {severity!r} must be 'error' or 'warning'")

    # Emitted in ClientSynth's SeedRule shape, camelCase included, so the contract
    # drops straight into schema_definition.seed_rules with no adapter in between
    # — an adapter is one more place for the two vocabularies to diverge.
    return {
        "id": str(front.get("id") or Path(page).stem),
        "name": str(front.get("title") or Path(page).stem),
        "type": rule_type,
        "sourceField": str(source_field),
        "targetFields": target_fields,
        "config": config,
        "description": str(front.get("summary") or spec.get("description") or ""),
        "severity": severity,
        "source_page": page,
    }


def compile_exemplar(page: str, front: dict[str, Any]) -> dict[str, Any]:
    field = front.get("field")
    if not field:
        raise CompileError(page, "an exemplar page must name the `field` it gives values for")

    raw = front.get("examples")
    if not isinstance(raw, list) or not raw:
        raise CompileError(page, "an exemplar page must carry a non-empty `examples` list")

    values: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            if "value" not in item:
                raise CompileError(page, "each example must have a `value`")
            values.append({"value": item["value"], "source": str(item.get("source") or "")})
        else:
            values.append({"value": item, "source": ""})

    return {"field": str(field), "examples": values, "source_page": page}


def compile_axis(page: str, front: dict[str, Any]) -> dict[str, Any]:
    name = front.get("axis") or front.get("title")
    if not name:
        raise CompileError(page, "an axis page must have an `axis` name")

    values = _as_list(front.get("values"))
    if not values:
        raise CompileError(page, "an axis page must list the `values` it varies over")

    return {
        "axis": str(name),
        "values": values,
        "field": str(front.get("field") or ""),
        "source_page": page,
    }


_COMPILERS = {
    "vocabulary": compile_vocabulary,
    "rule": compile_rule,
    "exemplar": compile_exemplar,
    "axis": compile_axis,
}


# ── Contract assembly ────────────────────────────────────────────────────────
def compile_wiki(wiki_dir: Path, *, vertical: str, strict: bool = True) -> tuple[dict[str, Any], list[CompileError]]:
    """Compile every generation page under wiki_dir into one contract.

    Returns (contract, errors). With ``strict`` the caller is expected to treat a
    non-empty error list as a failed build; the contract is still returned so a
    report can show what did compile.
    """
    vocabulary: dict[str, list[dict[str, Any]]] = {}
    rules: list[dict[str, Any]] = []
    exemplars: dict[str, list[dict[str, Any]]] = {}
    axes: list[dict[str, Any]] = []
    errors: list[CompileError] = []
    seen_rule_ids: dict[str, str] = {}

    for path, front, _body in iter_pages(wiki_dir):
        page_type = str(front.get("type") or "").strip().lower()
        if page_type not in _COMPILERS:
            continue

        page = _rel(path, wiki_dir)

        # A generation page that reads as participant-facing would be cited as
        # reference knowledge. Derivation already classes these types as
        # generation, so this only fires when a page overrides it by hand.
        governance = derive_governance(front)
        if governance["purpose"] == "reference":
            errors.append(CompileError(
                page,
                f"a {page_type} page is generator seed material and must not be "
                f"purpose: reference — it would be cited to a participant as fact",
            ))
            continue

        try:
            compiled = _COMPILERS[page_type](page, front)
        except CompileError as exc:
            errors.append(exc)
            continue

        if page_type == "vocabulary":
            vocabulary.setdefault(compiled["field"], []).append(compiled)
        elif page_type == "rule":
            # Two rules with one id means the second silently replaces the first
            # wherever the contract is keyed by id downstream.
            previous = seen_rule_ids.get(compiled["id"])
            if previous:
                errors.append(CompileError(
                    page, f"rule id {compiled['id']!r} is already used by {previous}"
                ))
                continue
            seen_rule_ids[compiled["id"]] = page
            rules.append(compiled)
        elif page_type == "exemplar":
            exemplars.setdefault(compiled["field"], []).extend(compiled["examples"])
        else:
            axes.append(compiled)

    permitted_values = {
        field: sorted({term["preferred_label"] for term in terms})
        for field, terms in sorted(vocabulary.items())
    }

    # Alternative labels, keyed by the preferred form. §6.2: these are the
    # synonyms lexical retrieval needs, since an exact-term corpus is exactly
    # where a query using the other name for a thing finds nothing.
    synonyms = {
        term["preferred_label"]: term["alternative_labels"]
        for terms in vocabulary.values()
        for term in terms
        if term["alternative_labels"]
    }

    contract = {
        "contract_version": CONTRACT_VERSION,
        "vertical": vertical,
        "compiled_at": _dt.date.today().isoformat(),
        "supported_rule_types": list(SUPPORTED_RULE_TYPES),
        "permitted_values": permitted_values,
        "vocabulary": {field: terms for field, terms in sorted(vocabulary.items())},
        "synonyms": dict(sorted(synonyms.items())),
        "seed_rules": rules,
        "examples": {field: values for field, values in sorted(exemplars.items())},
        "persona_axes": axes,
    }
    return contract, errors


def summarise(contract: dict[str, Any]) -> str:
    return (
        f"{sum(len(v) for v in contract['vocabulary'].values())} term(s) over "
        f"{len(contract['vocabulary'])} field(s) · "
        f"{len(contract['seed_rules'])} rule(s) · "
        f"{sum(len(v) for v in contract['examples'].values())} example(s) · "
        f"{len(contract['persona_axes'])} axis/axes · "
        f"{len(contract['synonyms'])} synonym set(s)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile the wiki into a generation contract.")
    parser.add_argument("--wiki", default=str(HERE / "wiki"), help="Wiki directory to compile.")
    parser.add_argument("--vertical", default="grain", help="Vertical slug recorded in the contract.")
    parser.add_argument("-o", "--out", default=str(HERE / "outputs" / "generation_contract.json"))
    parser.add_argument("--check", action="store_true",
                        help="Compile and report without writing; exit non-zero on any error.")
    args = parser.parse_args(argv)

    wiki_dir = Path(args.wiki)
    if not wiki_dir.exists():
        print(f"[compile] no wiki at {wiki_dir}", file=sys.stderr)
        return 1

    contract, errors = compile_wiki(wiki_dir, vertical=args.vertical)

    for err in errors:
        print(f"  ERROR {err}", file=sys.stderr)

    print(f"[compile] {summarise(contract)}")

    if errors:
        print(f"[compile] FAILED — {len(errors)} page(s) did not compile.", file=sys.stderr)
        return 1

    if args.check:
        print("[compile] check passed; nothing written.")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[compile] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
