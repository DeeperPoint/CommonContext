<!-- Copyright © 2026 Mustafa Uzumeri. All rights reserved. -->

# Knowledge Slot ↔ Cosolvent Integration Notes

> **Date:** 2026-02-20
> **Context:** Discussion of how the draft `grain_trade_schema.yaml` fits into the Cosolvent roadmap, how the schema interacts with chunking and RAG, whether the architecture generalises across verticals, and the overall project organisational model.
> **Status:** Waiting for Munim's review of the cosolvent roadmap(s) before proceeding
> **Participants:** Mustafa Uzumeri, Antigravity Agent

---

## Table of Contents

1. [Organisational Model](#1-organisational-model)
2. [Where the Knowledge Slot Fits in the Roadmap](#2-where-the-knowledge-slot-fits-in-the-roadmap)
3. [Participant Role Alignment](#3-participant-role-alignment)
4. [Reference Library Table Design](#4-reference-library-table-design)
5. [How Schema, Chunking, and RAG Interact](#5-how-schema-chunking-and-rag-interact)
6. [Cross-Vertical Generalisation](#6-cross-vertical-generalisation)
7. [Architectural Gotchas](#7-architectural-gotchas)
8. [Content Inventory → Table Mapping](#8-content-inventory--table-mapping)
9. [Questions for Munim's Review](#9-questions-for-munims-review)
10. [What Can Proceed Now vs. What's Blocked](#10-what-can-proceed-now-vs-whats-blocked)

---

## 1. Organisational Model

The whitepaper concepts divide into a framework layer and independent vertical implementations:

```
A) Cosolvent Framework (DeeperPoint-maintained, open-source)
   │
   │  each vertical "starts from a version" of the framework
   │
   ├── B) Grain Trading Vertical (Sponsor X)
   │   ├── B1. Knowledge Slot: grain_trade_schema.yaml + GAFTA docs + regulatory content
   │   ├── B2. ClientSynth:    synthetic grain traders/buyers for testing & demo
   │   └── B3. Digital Twin:   A + B1 + B2 deployed together as test/demo environment
   │
   ├── B) Mental Health Vertical (Sponsor Y)
   │   ├── B1. Knowledge Slot: therapy_schema.yaml + clinical guidelines + regulations
   │   ├── B2. ClientSynth:    synthetic providers/clients for testing & demo
   │   └── B3. Digital Twin:   A + B1 + B2 deployed together
   │
   └── ...more verticals, each sponsor-owned
```

### Key Principles

- **Each vertical is sponsor-owned.** Different investor/sponsor organisations own different verticals. Multi-vertical implementations don't need integration beyond directory-level linking.
- **Verticals configure, not fork.** The framework is expressive enough (YAML config, dynamic schemas, prompt management) that verticals should not need to modify framework code.
- **ClientSynth restriction holds naturally.** Since the Digital Twin (B3) is a test/demo environment separate from production, synthetic users never contaminate a live marketplace. A production deployment is A + B1 with real users only.
- **Framework defines extension points.** Verticals plug in via marketplace config, prompt templates, Knowledge Slot content, and ClientSynth profile data — not by modifying framework code.

### What Each Layer Owns

| Layer                   | Owns                                                                                                                                                                                | Maintained By                                                      |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **A — Framework**       | `MarketplaceConfig` model, compiler, dynamic schemas, visibility engine, permission engine, vector search, document processing, admin API, communication system, deployment tooling | DeeperPoint                                                        |
| **B — Vertical config** | `marketplace.yaml`, system prompts, profile field definitions, communication rules, onboarding settings                                                                             | Vertical sponsor + developer                                       |
| **B1 — Knowledge Slot** | Domain schema YAML, converted reference documents, metadata tag vocabulary, chunking strategy config, seed data scripts                                                             | Vertical sponsor (domain expert)                                   |
| **B2 — ClientSynth**    | Persona templates, field value distributions, synthetic profile generation scripts                                                                                                  | Vertical sponsor (uses ClientSynth engine from A-adjacent tooling) |
| **B3 — Digital Twin**   | Deployment recipe (Docker Compose referencing Cosolvent image + B1 + B2 content mounts)                                                                                             | Vertical sponsor                                                   |

### Desired Project Structure (Per Vertical)

```
grain-trading-vertical/                  ← Vertical (B)
  ├── marketplace.yaml                   ← Vertical config
  ├── knowledge-slot/                    ← B1
  │   ├── schemas/grain_trade_schema.yaml
  │   ├── documents/                     ← Converted Markdown reference docs
  │   ├── seed-data/                     ← Ingestion-ready content for reference_library
  │   └── prompts/                       ← Domain Q&A system prompts
  ├── clientsynth/                       ← B2
  │   ├── persona-templates/
  │   └── generation-config.yaml
  └── docker-compose.yml                 ← B3 (references cosolvent image + mounts B1/B2)
```

---

## 2. Where the Knowledge Slot Fits in the Roadmap

The grain trade schema is the first concrete deliverable for **Cosolvent ROADMAP §16.2** ("Knowledge Slot — Reference Library"). It maps to **Track B, item B1.4** in the prioritised implementation phases.

### Current Position

```
AIKnowledgeSlotCuration                 Cosolvent
═══════════════════════                 ══════════════
Phase 1 — Foundation ✅                  Phase 0 — Hygiene
  • PDF/URL conversion tools              Phase 1 — Three-Layer + Deals
  • GAFTA Contract 27 converted           Phase 2 — Trust + Admin
  • Domain schema extracted                   │
  • Recipe documented                    Track B: B1 — Knowledge Slot
                                              │
Phase 2 — Schema Enrichment 🔲               ├── B1.4: reference_library table
  • More contracts, standards                 ├── B1.5: Metadata-filtered search
  • Merged schema                             └── consumes schema + content

Phase 3 — Ingestion Prep 🔲 ──────── BLOCKED by B1.4 (no table yet)
Phase 4 — Integration Test 🔲 ────── BLOCKED by B1.4 + B1.5 + Domain Q&A
```

**Phase 2 work (more contracts, enriching the schema) can proceed independently.** Phase 3 is blocked until Cosolvent implements the `reference_library` table.

---

## 3. Participant Role Alignment

### What Maps Cleanly

The schema's §19 (`participant_roles`) maps directly to Cosolvent's `ParticipantType` model:

| Schema Role                               | Cosolvent `role` | Example `slug`  |
| ----------------------------------------- | --------------------- | --------------- |
| `supply` (Seller)                         | `"supply"`            | `"seller"`      |
| `demand` (Buyer)                          | `"demand"`            | `"buyer"`       |
| `facilitator` (Broker / Service Provider) | `"facilitator"`       | `"facilitator"` |

### The Facilitator Subtype Problem

The schema identifies **9 facilitator subtypes**: broker, shipping agent, insurance broker, superintendent, analyst, fumigator, trade finance, customs broker, legal counsel. Each has different capabilities, GAFTA registries, and relevant clauses.

Cosolvent's `ParticipantType` is a flat structure — one entry per type with a `slug`, `name`, `role`, and `permissions`. **Conflict C3** limits participant types to 3 for MVP.

**Three options discussed:**

| Option                                               | Summary                                               | Trade-off                                                      |
| ---------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------- |
| **A — Separate types**                               | 11 total types (1 supply + 1 demand + 9 facilitators) | Cleanest model, but requires relaxing C3 significantly         |
| **B — Single facilitator with `service_type` field** | 3 types total; subtypes are profile data              | Works within limits; all facilitators share one permission set |
| **C — Grouped facilitator types**                    | 5–6 types: logistics, quality, financial, legal       | Middle ground; still needs C3 relaxed                          |

**Recommendation:** Option B for Phase 1 (works within 3-type limit), migrate to Option A later. The `service_type` would be a `multi_select` field in the facilitator's profile schema, with values drawn from the grain trade schema's subtype list.

### Cross-Vertical Note

The supply/demand/facilitator model maps cleanly to bilateral exchange markets (grain trading, manufacturing) but is more awkward for service markets (mental health: "supply" of therapy) or data markets (both sides supply and consume). The mapping works via the `ParticipantType.name` field (user-facing label) vs. `ParticipantType.role` (system-level category), but the schema should document the justification when the mapping is a stretch.

---

## 4. Reference Library Table Design

### Proposed Schema: Two Tables

**`reference_documents`** — document-level metadata:

| Column              | Type              | Notes                                                                  |
| ------------------- | ----------------- | ---------------------------------------------------------------------- |
| `id`                | UUID (PK)         |                                                                        |
| `title`             | TEXT              | e.g. "GAFTA Contract No. 27 (2025)"                                    |
| `source_authority`  | TEXT              | e.g. "GAFTA"                                                           |
| `document_type`     | TEXT              | "contract", "regulation", "guide", "standard", "research", "checklist" |
| `version`           | TEXT              | e.g. "2025 edition"                                                    |
| `source_url`        | TEXT (nullable)   |                                                                        |
| `vertical_metadata` | JSONB             | **Vertical-specific tags from the grain trade schema**                 |
| `status`            | TEXT              | "draft", "active", "superseded"                                        |
| `uploaded_by`       | UUID (FK → users) | The admin/sponsor                                                      |
| `created_at`        | TIMESTAMPTZ       |                                                                        |
| `updated_at`        | TIMESTAMPTZ       |                                                                        |

**`reference_chunks`** — chunk-level embeddings:

| Column                               | Type                                     | Notes                                        |
| ------------------------------------ | ---------------------------------------- | -------------------------------------------- |
| `id`                                 | UUID (PK)                                |                                              |
| `document_id`                        | UUID (FK → reference_documents, CASCADE) |                                              |
| `chunk_index`                        | INTEGER                                  |                                              |
| `chunk_text`                         | TEXT                                     |                                              |
| `embedding`                          | Vector(1536)                             | Same model as `ai_document_chunks`           |
| `chunk_metadata`                     | JSONB                                    | Inherited from parent + chunk-specific       |
| `section_id`                         | TEXT (nullable)                          | Clause/section identifier (e.g. "clause_18") |
| `created_at`                         | TIMESTAMPTZ                              |                                              |
| UNIQUE(`document_id`, `chunk_index`) |                                          |                                              |

### Why Two Tables

The existing `ai_document_chunks` conflates document identity with chunks. Reference documents need:
- **Document-level metadata** for filtering (what country? what commodity? what type?)
- **Chunk-level storage** for embedding search
- **Section identity** for citation (e.g. "GAFTA Contract 27, Clause 18")

### `vertical_metadata` Example (Grain Trading)

```json
{
  "origin_countries": ["Canada", "United States of America"],
  "destination_regions": ["Asia-Pacific", "Middle East", "North Africa"],
  "commodity_categories": ["wheat", "barley", "canola", "corn"],
  "document_type": "contract",
  "trade_terms": ["CIF", "CIFFO", "C&F", "C&FFO"],
  "issuing_body": "GAFTA",
  "topics": ["payment", "insurance", "quality", "weighing", "arbitration"]
}
```

The keys and allowed values would be defined by a `reference_metadata_schema` config section in `marketplace.yaml`, populated from the grain trade schema's vocabulary.

### Cross-Slot Architectural Guardrails

Three constraints (from AIKnowledgeSlotCuration ROADMAP §3):

1. **Same embedding model and dimensions** — `reference_chunks` must use `text-embedding-3-small` (1536 dims), matching `ai_document_chunks` and `profile_vectors`. Conflict C4 (embedding model lock-in) applies.

2. **Shared metadata vocabulary** — Geography, commodity categories, and certification types that appear in both participant profiles and reference documents must use the same controlled values.

3. **Composable retrieval interface** — Both `_search_document_vectors` and `search_reference_library` should return the same result shape:

```python
@dataclass
class RetrievalResult:
    source: Literal["participant_docs", "reference_library"]
    content: str
    metadata: dict[str, Any]
    score: float
    citation: str | None  # e.g. "GAFTA Contract 27, Clause 18"
```

---

## 5. How Schema, Chunking, and RAG Interact

The schema plays **three distinct roles** in the RAG pipeline:

### Role 1: Schema as Metadata Filter (Pre-Retrieval)

The schema defines the vocabulary for tagging and filtering reference documents *before* vector search runs. This is **hybrid retrieval** — currently the strongest best practice for domain-specific RAG.

```
User query: "What fumigation requirements apply to wheat shipments to Japan?"
                │
                ▼
┌──────────────────────────────────────────────────────────┐
│ Step 1: Metadata pre-filter (uses schema vocabulary)     │
│                                                          │
│  user profile → commodity_type: "wheat"                  │
│               → destination: "Japan"                     │
│  query intent → topic: "fumigation"                      │
│                                                          │
│  Narrows 500 chunks → ~30 candidates                     │
├──────────────────────────────────────────────────────────┤
│ Step 2: Vector similarity (embedding distance)           │
│                                                          │
│  Rank 30 candidates by cosine similarity to query        │
│  Return top 5                                            │
├──────────────────────────────────────────────────────────┤
│ Step 3: LLM generation with retrieved context            │
│                                                          │
│  Context = 5 chunks + citation metadata                  │
│  Generate answer with clause-level citations             │
└──────────────────────────────────────────────────────────┘
```

**Schema's value:** defines the filter dimensions. Without it, pure vector search across all reference documents returns semantically similar but contextually wrong results.

### Role 2: Schema as Chunking Guide (Ingestion-Time)

Current best practice has moved from fixed-size chunking to **structure-aware chunking**. Cosolvent's current 1000-char/200-overlap approach is fine for freeform participant documents but is **harmful for contracts and standards** because:

1. A fixed window can split a clause in half, losing the heading and context
2. Citation becomes impossible when chunks don't know what clause they came from
3. Overlap doesn't recover semantic coherence

**Schema-informed chunking** uses the schema's section structure as a guide:

```
Input: GAFTA Contract No. 27 (Markdown)
Schema: grain_trade_schema.yaml

Strategy:
  1. Parse Markdown headings → identify clause boundaries
  2. Map headings to schema sections (e.g., "## Clause 18" → schema §18 "Sampling")
  3. Chunk by clause, not by character count
  4. If clause exceeds token limit (~512 tokens), split at sub-clause boundaries
  5. Each chunk carries metadata:
     - section_id: "clause_18"
     - schema_section: "sampling"
     - topics: ["sampling", "analysis", "certificates"]
     - related_roles: ["superintendent", "analyst"]
```

**Result:** each chunk is semantically complete, self-identified, metadata-tagged, and citation-ready.

### Role 3: Schema as Reasoning Context (Generation-Time)

At generation time, a relevant **schema fragment** injected into the prompt gives the LLM structural understanding of how domain concepts relate:

```
Domain context (from grain_trade_schema):
- Quality is assessed via sampling (GAFTA Rules 124) and analysis (GAFTA Rules 130)
- Sampling must be supervised by a GAFTA-registered superintendent
- Analysis must be performed by a GAFTA-registered analyst
- Quality rejection triggers rye terms (deficiency deduction per formula)
- Buyer tolerance: ±0.5% on quality parameters
- Dispute path: GAFTA Arbitration Rules No. 125
```

This is structurally similar to what knowledge graphs do in GraphRAG — providing relational context that flat vector retrieval misses. The YAML schema serves as a lightweight, human-maintainable alternative.

### Current Best Practice Status

| Practice                                 | Status in Cosolvent | Needed                                 |
| ---------------------------------------- | ------------------- | -------------------------------------- |
| **Hybrid retrieval** (metadata + vector) | 🔲 Pure vector only  | Pre-filtering using schema vocabulary  |
| **Structure-aware chunking**             | 🔲 Fixed 1000-char   | Clause-aware for structured docs       |
| **Re-ranking**                           | 🔲 Not present       | Cross-encoder after initial retrieval  |
| **Contextual enrichment**                | 🔲 Not present       | Schema fragment injection in prompts   |
| **Citation**                             | 🔲 Not present       | `section_id` on chunks                 |
| **Metadata enrichment**                  | 🔲 Not present       | Tag chunks with schema vocabulary      |
| **Separate retrieval scopes**            | 🔲 Not present       | Reference library vs. participant docs |

---

## 6. Cross-Vertical Generalisation

### What Generalises Well

1. **YAML schema format** — the structure (entities, fields, roles, standards, exclusions) works for any vertical; only the content changes.
2. **Two-table architecture** (`reference_documents` + `reference_chunks`) — every vertical has documents and chunks.
3. **`vertical_metadata` JSONB column** — different verticals store different metadata keys; JSONB accommodates this.
4. **Composable retrieval interface** — `{source, content, metadata, score, citation}` is vertical-agnostic.
5. **Organisational model** (A/B/B1/B2/B3) — each vertical is an independent deployment.

### What Needs Attention

#### Challenge 1: Chunking Strategy Is Document-Type-Dependent

Clause-aware chunking works for contracts and standards but fails for clinical guidelines (decision trees), conversational guides (flowing text), or data sheets (tables). The chunking strategy must be **configurable per document type**, not hardcoded per vertical:

```yaml
chunking_strategies:
  contract:
    method: "structure_aware"
    boundary_markers: ["## Clause", "### Sub-clause"]
    max_chunk_tokens: 512
  guideline:
    method: "semantic"
    similarity_threshold: 0.7
    target_chunk_tokens: 400
  datasheet:
    method: "row_level"
    table_detection: true
  default:
    method: "fixed_size"
    chunk_size: 1000
    overlap: 200
```

#### Challenge 2: Metadata Filter Dimensions Are Radically Different Per Vertical

Grain trading filters on `origin_country`, `commodity_type`, `trade_terms`. Mental health filters on `jurisdiction`, `clinical_area`, `insurance_provider`. The filtering SQL is flexible enough (JSONB queries), but **user-context scoping** needs a vertical-specific mapping between profile fields and metadata keys:

```yaml
reference_metadata_schema:
  keys:
    origin_country:
      type: multi_select
      values: ["Canada", "United States"]
  user_context_mapping:
    origin_country: "country"          # profile field → metadata key
    commodity_type: "primary_crops"
```

This mapping is vertical-specific but the *mechanism* is generic.

#### Challenge 3: Schema Depth Varies By Vertical

Grain trading produces an 820-line schema from a single codified contract. A mental health vertical may produce a thinner schema from richer, less-structured documents. The curation recipe needs to acknowledge that the starting point and yield differ:

| Grain Trading                  | Mental Health                   | Manufacturing                 |
| ------------------------------ | ------------------------------- | ----------------------------- |
| Start: standard contract       | Start: clinical guideline       | Start: material specification |
| Yield: dense structured schema | Yield: thinner, more relational | Yield: heavily tabular        |

#### Challenge 4: Vocabulary Drift Between Config And Schema

The `marketplace.yaml` profile fields and the Knowledge Slot metadata must share vocabulary. If the profile says `country: "USA"` but reference docs are tagged `origin_country: "United States of America"`, user-context scoping breaks. Both should draw from shared taxonomy lists.

---

## 7. Architectural Gotchas

Six conditions for the A / B(B1, B2, B3) model to work:

### Gotcha 1: Fork or Configure?

Cosolvent is designed for "Configure" (YAML config, dynamic schemas, prompt management). If any vertical needs a feature the framework doesn't support (e.g. clause-aware chunking when only fixed-size exists), the vertical faces: wait for upstream, fork, or contribute upstream.

**Mitigation:** Cosolvent must define **stable extension points** (marketplace config, prompt templates, Knowledge Slot interface, ClientSynth API contract, chunking strategy plugins) and version them as public API.

### Gotcha 2: Framework Upgrade Path

When Cosolvent releases a new version, existing verticals decide whether to upgrade. If table schemas or config formats change, vertical content needs migration.

**Mitigation:** Semantic versioning, Alembic migrations (already in place), clear changelogs for breaking changes, config validation with helpful errors for missing new fields.

### Gotcha 3: Where Does `marketplace.yaml` Live?

Currently inside the Cosolvent repo. In the organisational model it's vertical-specific content (B), not framework code (A). The vertical project should own its `marketplace.yaml` and mount it into a Cosolvent container.

**Mitigation:** Already supported via `MARKETPLACE_CONFIG_PATH` env var. But Knowledge Slot content has **no equivalent mount point** — there's no `REFERENCE_LIBRARY_SEED_PATH` or CLI for seed data loading. This needs to be part of B1.4 implementation.

### Gotcha 4: ClientSynth Needs Marketplace Config as Input

ClientSynth profiles must conform to the vertical's `marketplace.yaml` schemas (same field names, same allowed values). The ClientSynth engine needs to read the marketplace config to generate conforming profiles.

**Mitigation:** Define the Cosolvent ↔ ClientSynth API contract (roadmap Conflict C6, Option A). ClientSynth engine is A-adjacent tooling; vertical config templates are B2.

### Gotcha 5: Digital Twin = Deployment Recipe, Not Code

B3 has no *code* to write — it's a Docker Compose file that deploys A with B1 content and B2 profiles loaded. However, the **Market Physics Scorecard** (roadmap B1.8) is what transforms the Digital Twin from a populated demo into a simulation. Until the scorecard exists, B3 is a demo tool only.

### Gotcha 6: Shared Vocabulary Must Be Explicit

Profile field options and reference metadata values must use identical controlled vocabularies. A mismatch (e.g. "USA" vs. "United States of America") breaks user-context scoping.

**Mitigation:** Establish a shared taxonomy convention. Both `marketplace.yaml` profile fields and `reference_metadata_schema` should reference a common set of allowed values, either via a shared YAML file or explicit documentation.

---

## 8. Content Inventory → Table Mapping

How currently converted documents would map to `reference_documents` rows:

| Output File                         | `title`                                              | `document_type` | Key `vertical_metadata`                                                      |
| ----------------------------------- | ---------------------------------------------------- | --------------- | ---------------------------------------------------------------------------- |
| `27_2025.md`                        | GAFTA Contract No. 27 (2025)                         | contract        | `origin_countries: [CA, US], trade_terms: [CIF, CIFFO, C&F, C&FFO]`          |
| `Shipping Agricultural Products...` | Shipping Agricultural Products in Canada             | guide           | `origin_countries: [CA], topics: [logistics, export]`                        |
| `Packing-of-Grain-in-Containers...` | Industry Standard for Packing of Grain in Containers | standard        | `topics: [containerisation, packing], issuing_body: Shipping Australia`      |
| `ctu-code-a-quick-guide...`         | CTU Code Quick Guide                                 | guide           | `topics: [containerisation, safety, packing]`                                |
| `ctu-code-checklist-english.md`     | Container Packing Checklist                          | checklist       | `topics: [containerisation, pest_control, safety]`                           |
| `university_20of_20manitoba...`     | Containerized Grain Supply Chain in Western Canada   | research        | `origin_countries: [CA], topics: [containerisation, regulation, logistics]`  |
| `10-02.md`                          | D-10-02: Canadian Grain Sampling Program             | regulation      | `origin_countries: [CA], issuing_body: CFIA, topics: [sampling, inspection]` |

---

## 9. Questions for Munim's Review

### Roadmap & Organisation

1. **Does the A / B(B1, B2, B3) model make sense?** Each vertical is sponsor-owned, starts from a Cosolvent version, and includes its own Knowledge Slot, ClientSynth, and Digital Twin.

2. **Roadmap phasing** — Should Knowledge Slot (B1.4) be pulled earlier in the Cosolvent roadmap, given that content curation is already underway? It's currently in Track B (after Phase 2).

### Participant Roles

3. **Facilitator subtype permissions** — Do different facilitator roles (superintendent vs. broker vs. customs) need different permission sets? This determines whether Conflict C3 needs early resolution.

### Knowledge Slot Design

4. **Two-table design** — Does the `reference_documents` + `reference_chunks` split make sense? Does the `vertical_metadata` JSONB approach provide enough structure?

5. **Chunking strategy** — Should the framework support pluggable chunking strategies per document type? The GAFTA contract has numbered clauses that should be chunk boundaries.

6. **Seed data loading** — The vertical project needs a way to load Knowledge Slot content (B1) into a Cosolvent instance. Should this be a CLI command, a startup hook, or an admin API endpoint?

### Vocabulary & Integration

7. **Shared taxonomy convention** — How should `marketplace.yaml` profile field values and `reference_metadata_schema` values stay in sync? Shared YAML files, or documentation convention?

8. **`reference_metadata_schema` placement** — Should this be a new top-level section in `marketplace.yaml`, or a separate config file?

---

## 10. What Can Proceed Now vs. What's Blocked

### Can Proceed Now

- **Phase 2 content work** — acquiring and converting more GAFTA contracts and referenced standards
- **Clause-aware chunking prototype** — experiment with splitting `27_2025.md` by clause boundaries
- **Metadata vocabulary formalisation** — extract controlled value lists from the schema into a formal `reference_metadata_schema` section
- **Additional web source conversion** — the `convert_url.py` pipeline is ready for more regulatory sources
- **Vertical project template** — draft the directory structure and Docker Compose template for B3

### Blocked

- **`reference_documents` / `reference_chunks` table definitions in `db_schema.py`** — needs agreement on the two-table design and finalisation of framework extension points
- **Ingestion scripts (Phase 3)** — needs the tables to exist
- **Integration testing (Phase 4)** — needs tables + retrieval function + domain Q&A mode
- **Facilitator subtype strategy** — needs Munim's input on permission differentiation
- **ClientSynth API contract** — needs alignment between Cosolvent framework team and vertical project team
- **Seed data loading mechanism** — needs framework support (CLI, startup hook, or admin API)
