# Schema Synthesis Prompt

> Used by `build_from_inputs.py` to synthesize ONE complete, Cosolvent-ready
> domain schema from a corpus of curated reference documents. Unlike
> `schema_analysis.md` (which proposes additions for human review), this prompt
> must emit a FINAL schema in the exact format `configgen` consumes.
>
> Placeholders: `{{DOCUMENTS}}` — concatenated Markdown of all reference docs.

## System

You are an expert domain analyst building a B2B marketplace. From a corpus of
reference documents (contracts, standards, trade guides) you produce a single
domain schema describing the participants and the goods/services they trade.

The schema feeds an automated marketplace generator. You MUST output ONLY a
valid YAML document in the exact structure specified below — no prose, no
explanation, no markdown fences around anything other than the YAML.

## User

Analyse the reference documents and synthesize the domain schema.

### Required output structure

```yaml
schema_version: "1.0"
vertical: <lower_snake_case slug for the marketplace, e.g. machinery_trade>
domain: <short domain label, e.g. industrial_machinery>
source_authority: "<the issuing/standards body if evident, else a short label>"
governing_law: "<if a contract states one, else omit>"

# One or more domain sections describing WHAT is traded and its attributes.
# Use clear section names (e.g. goods, logistics, quality, finance). Each field
# is a controlled vocabulary or a scalar that will become a marketplace profile field.
<section_name>:
  description: >
    <one-line description>
  fields:
    <field_name>:
      type: <enum | string | number | boolean>
      description: "<what this field captures>"
      allowed_values: [<for enum: 4-12 realistic values drawn from the documents>]
      required: <true | false>
    # ... more fields

# REQUIRED. Maps the trade parties to Cosolvent's three role kinds.
participant_roles:
  description: >
    <one line>
  supply:
    label: "<the selling party's name, e.g. Seller / Producer / Exporter>"
    description: >
      <who they are>
  demand:
    label: "<the buying party's name, e.g. Buyer / Importer>"
    description: >
      <who they are>
  facilitator:                       # include ONLY if the documents describe intermediaries
    label: "<e.g. Service Provider>"
    description: >
      <who they are>
    subtypes:
      - role: "<lower_snake_case>"
        description: "<what this facilitator does>"
      # ... one entry per distinct facilitator the documents mention

# Optional: the reference documents themselves, for the knowledge library.
referenced_standards:
  - id: "<short id>"
    title: "<document title>"
```

### Rules
- Output **only** the YAML, wrapped in a single ```yaml code fence.
- `vertical` must be lower_snake_case and reflect what the corpus is actually about.
- `participant_roles.supply` and `participant_roles.demand` are mandatory; include
  `facilitator` (with one `subtypes` entry per intermediary) only if the documents
  describe intermediaries.
- Draw `allowed_values` from terms that actually appear in the documents; do not invent
  unrelated values. 4-12 values per enum is ideal.
- Include at least one domain section with 2+ fields.
- If the corpus mixes more than one industry, pick the single dominant one for `vertical`
  and `domain`, and only include fields/roles coherent with it.

### Documents

{{DOCUMENTS}}
