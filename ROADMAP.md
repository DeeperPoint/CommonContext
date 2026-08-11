<!-- Copyright © 2026 Mustafa Uzumeri. All rights reserved. -->

# CommonContext Roadmap

> **Purpose:** Curate, structure, and prepare domain knowledge for a Cosolvent marketplace deployment — producing both the *domain schema* (→ `marketplace.yaml`) and the *knowledge library* (→ `reference_library`).
>
> **Naming:** This project was formerly *CommonContext* / *CommonContext*; it is now **CommonContext**. The "Knowledge Slot" term below refers to the Cosolvent architectural slot this content populates. Rename tracked in [`docs/ROADMAP-renaming-commoncontext-to-commoncontext.md`](docs/ROADMAP-renaming-commoncontext-to-commoncontext.md).
>
> **Relationship to other projects:**
> - **Cosolvent** — Consumes both outputs: `configgen` turns the schema into `marketplace.yaml`, and `load-references` ingests the knowledge library into the `reference_library` pgvector table. That table, grounded domain Q&A, and the gap-signal store are now **implemented** on the Cosolvent side (see the Status Update).
> - **mfgllmwiki** — A source corpus. `wiki_to_provenance.py` maps wiki-page frontmatter into provenance sidecars so wiki pages can be embedded into the library (`wiki_refs.jsonl`).
> - **Whitepaper** — The theoretical foundation (Authoritative Information Availability; Curating and Distributing Authoritative Information; AI-Curated Authoritative Information). Canonical copy lives in the DeeperPoint wiki/publishing repos.
>
> **Date:** 2026-02-20 (original); revised 2026-03-14; status-refreshed 2026-07-21
> **Author:** Mustafa Uzumeri

---

## Status Update — 2026-07-21

This roadmap was written against an early-2026 snapshot (grain/GAFTA vertical, before the CommonContext→CommonContext rename). Much of Phases 1–3 has since shipped and the primary demo vertical has moved to **machinery/manufacturing**. The accurate operational references are now [`HOW-TO-USE.md`](HOW-TO-USE.md) and the `Makefile`. Highlights:

| Area | Original status | Now |
|---|---|---|
| **Ingestion pipeline (Phase 3)** | Planned | ✅ Built — heading-based chunking, LLM topic-tagging against a controlled vocab, 1536-dim embeddings, and a Cosolvent export contract: `chunk_and_embed.py` → `export_references.py`. Design captured in `docs/DECISION-004` (reference-table) and `docs/DECISION-005` (chunking/tagging). |
| **One-command build** | — | ✅ `build_from_inputs.py` / `make build`: convert `inputs/` → synthesize schema → embed → `generated_refs.jsonl`. Also emits a **domain schema** for Cosolvent `configgen` (a second output beyond the knowledge library). |
| **Seed / load into Cosolvent** | Planned | ✅ `seed_reference_library.py` (direct pgvector upsert, idempotent) and Cosolvent's `load-references` CLI (`make build-and-load`). |
| **Cosolvent-side `reference_library` + Q&A + gap store** | 🔲 Not yet implemented | ✅ Implemented in Cosolvent (`reference_library` table, `/api/ai/knowledge` grounded Q&A with citations, `knowledge_gap_signals`). The §6 dependency table below is updated accordingly. |
| **Gap / pull signals** | Prompt 🔲 | ✅ `gap_signal.py` + `prompts/gap_detection.md` + `migrations/add_gap_signals.sql`; covered by `test_gap_signal.py`. |
| **Embedding provider** | OpenAI via `llm_client.py` | 🟡 Now `openai/text-embedding-3-small` via **OpenRouter** (single key does LLM + embeddings), with a direct-OpenAI fallback. |
| **Second vertical** | Grain only | ✅ Cross-vertical proven: **machinery_trade** + **manufacturing** are the active corpora (mfgllmwiki embedded via `wiki_to_provenance.py` → `wiki_refs.jsonl`); grain moved to `inputs_archive_grain/`. `test_cross_vertical.py` runs both. |
| **Test suite** | — | ✅ 11 test modules incl. a real pgvector integration test (`docker-compose.test.yml`). |
| **Curation Tool** | GUI (`server.py`) | ✅ Still current; now also launchable in Docker via the `/launch-docker` workflow (port 8400). |

**Still ahead:** broadening the reference corpus (Phase 2), the sponsor-facing curation UX and pull-signal queue (§5 Q5, `docs/DECISION-001`), staleness detection (§2.9, `docs/DECISION-002`), and full cross-collection retrieval testing (Phase 4). Naming cleanup of residual "Knowledge Slot" strings in code/UI is tracked in the rename doc.

Section markers below (✅/🟡) reflect this update; the original phase text is retained for context.

---

## 1. What is the Knowledge Slot?

The Knowledge Slot is a **sponsor-curated reference library** that provides domain knowledge to a Cosolvent marketplace deployment. It is one of five architectural "slots" in the Cosolvent framework:

| Slot                  | What it holds                                      | Who curates it      | Source                            |
| --------------------- | -------------------------------------------------- | ------------------- | --------------------------------- |
| **Context Slot**      | Participant-supplied documents (uploads, profiles) | Participants        | Three-layer privacy model         |
| **Intelligence Slot** | AI model configuration, provider routing, prompts  | Admin / Developer   | `llm_client.py`, `system_prompts` |
| **Knowledge Slot**    | Sponsor-curated domain reference material          | Marketplace sponsor | `reference_library` table         |
| **Agent Slot**        | Brokerage agent configuration (personas, rules)    | Admin               | Future implementation             |
| **MCP Slot**          | External data source / tool connectivity           | Admin               | Future implementation             |

### Terminology Evolution

The concept has evolved through several iterations:

| Stage                      | Term                                 | Where it appeared                                  | What it meant                                                                                                        |
| -------------------------- | ------------------------------------ | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Early CosolventAI**      | "Industry Context"                   | `industry_context_service` in CosolventAI codebase | General RAG over ingested documents — no separation between participant docs and reference docs                      |
| **CosolventAI Roadmap**    | "Knowledge Slot"                     | §21 (Slots Architecture)                           | Architecturally distinct store for sponsor-curated, domain-authoritative reference material                          |
| **Cosolvent Roadmap** | "Knowledge Slot (Reference Library)" | §16.2                                              | Implementation specification: `reference_library` table, metadata-filtered vector search, document curation workflow |
| **This project**           | "Knowledge Slot Curation"            | CommonContext repo                       | The process and tooling for preparing content to populate the Knowledge Slot                                         |

The key architectural distinction: **participant documents** (Context Slot) follow the three-layer privacy model and are self-service. **Reference documents** (Knowledge Slot) are sponsor-curated, progressively built, and authoritative. The two never mix in retrieval.

---

## 2. Design Principles (from CosolventAI §21 and Cosolvent §16.2)

### 2.1 — Separation from Participant Documents

Reference documents are stored in a dedicated `reference_library` table, distinct from participant-uploaded files (`ai_document_chunks`). This separation ensures:
- Reference material is not contaminated by participant uploads
- Participant privacy controls do not apply to reference material (it is sponsor-curated, not user-submitted)
- Retrieval pipelines can scope queries to one or both stores

### 2.2 — Vertical-Specific Metadata Schema

The tag vocabulary for reference documents is defined by the vertical deployment, not hardcoded. The framework provides a `reference_metadata_schema` (analogous to `MarketDefinition` for participant fields) that the admin configures.

Examples by vertical:

| Vertical                    | Metadata Tags                                                                                                                                            |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Agricultural trade**      | `origin_region`, `destination_country`, `product_category`, `document_type` (regulation / contract / guide / standard), `trade_corridor`, `issuing_body` |
| **Remote mental health**    | `jurisdiction`, `insurance_provider`, `service_type`, `clinical_area`, `license_type`, `regulatory_body`                                                 |
| **Specialty manufacturing** | `material_class`, `standard_body` (ISO / ASTM / DIN), `export_control_regime`, `process_type`                                                            |

### 2.3 — Document Curation Workflow

Admin can upload, tag (using the vertical's metadata schema), describe, and version reference documents. The sponsor progressively builds this library over time. Documents are chunked, embedded, and immediately available for retrieval.

### 2.4 — Metadata-Filtered Vector Search

Retrieval uses metadata pre-filters *before* vector similarity ranking, in a single query. This avoids physical partitioning while achieving context-appropriate scoping:

```sql
SELECT chunk_text, source_document, metadata
FROM reference_library
WHERE destination_countries && ARRAY[$user_country]
  AND product_categories && ARRAY[$user_interests]
  AND document_type = ANY($relevant_types)
ORDER BY embedding <=> $query_embedding
LIMIT $k;
```

Documents can carry multiple tags (a guide to Incoterms is tagged with every destination country it applies to), and cross-corridor queries work naturally.

### 2.5 — Automatic User-Context Scoping

The system injects the participant's metadata (country, role, product interests, active deal corridors) as implicit retrieval filters. The user doesn't type "show me Philippines regulations" — they just ask their question, and the system scopes retrieval based on what it already knows about them.

### 2.6 — Domain Q&A Integration

The chatbot supports a "domain knowledge" mode where it answers from the reference library, distinct from participant-to-participant messaging or deal-scoped conversation. Answers are sourced — each response cites which reference documents informed the answer.

### 2.7 — Vertical-Supplied Prompts

The Knowledge Slot's chat behaviour is configured via `system_prompts`: the vertical deployment defines the persona (e.g., "You are a trade advisor specialising in Asia-Pacific grain imports"), the citation style, and the scope boundaries ("only answer from reference material; say 'I don't have this information' otherwise").

### 2.8 — Demand-Driven Curation (Pull Signals)

The reference library is progressively built not just through proactive ingestion, but actively guided by user queries that fall outside the current envelope. When a user asks a question the Knowledge Slot cannot answer, the system gracefully falls back (e.g., to external synthesis) and simultaneously fires a "Curatorial Pull Signal" to the sponsor dashboard. This highlights specific, high-value knowledge gaps obstructing potential transactions, directing the sponsor's curation efforts exactly where they are needed most.

> **Design details:** See `docs/DECISION-001-pull-signal-transport.md` for the open decision on how signals flow between Cosolvent and CommonContext.

### 2.9 — Staleness Detection

Reference documents are periodically checked for indicators of change or supersession. The system alerts the curator rather than attempting automatic updates, preserving the sponsor's editorial authority over the reference library. Three detection strategies are employed: source URL monitoring (for documents fetched from the web), LLM-assisted web search (for all documents), and age-based review thresholds.

> **Design details:** See `docs/DECISION-002-staleness-detection.md`.

---

## 3. Cross-Slot Architectural Guardrails

Three design constraints must be observed to preserve the path to cross-slot intelligence:

1. **Same embedding model and dimensions across all vector stores.** The `reference_library` table and `participant_embeddings` table must use the same embedding model. If they diverge, cross-collection similarity search becomes impossible without re-embedding.

2. **Shared metadata vocabulary.** Concepts that appear in both participant profiles and reference documents — geography, product categories, certification types — should use the same controlled vocabulary. Both `MarketDefinition` and `reference_metadata_schema` should draw from shared taxonomy lists.

3. **Composable retrieval interface.** The retrieval layer should return results as `{source, content, metadata, score}` tuples regardless of which table they came from. The interface should accept a source parameter (participants, reference_library, or both) so that future callers can request merged, cross-collection results.

---

## 4. What This Project Produces

This project curates the **content** side of the Knowledge Slot — the reference documents, domain schemas, and metadata that a marketplace sponsor would load into the `reference_library` table.

### 4.1 — Deliverables

| Deliverable                        | Format           | Description                                                           | Status                              |
| ---------------------------------- | ---------------- | --------------------------------------------------------------------- | ----------------------------------- |
| **Converted reference documents**  | Markdown         | Source documents (PDF, HTML, CSV, XLSX) converted to clean Markdown   | `outputs/27_2025.md` ✅              |
| **Domain schema**                  | YAML             | Structured vocabulary extracted from reference documents              | `schemas/grain_trade_schema.yaml` ✅ |
| **Schema analysis results**        | YAML             | LLM-generated proposals for schema additions and refinements          | `analyses/` ✅                       |
| **Analysis prompt template**       | Markdown         | Editable LLM prompt for schema extraction                             | `prompts/schema_analysis.md` ✅      |
| **Provenance metadata**            | JSON             | Source URL, acquisition method, and timestamps for every document     | `provenance/` ✅                     |
| **Metadata extraction prompt**     | Markdown         | Editable LLM prompt for document metadata extraction                  | `prompts/metadata_extraction.md` ✅  |
| **Metadata tag vocabulary**        | YAML (in schema) | Vertical-specific tags for the `reference_metadata_schema`            | Embedded in schema ✅                |
| **Participant role map**           | YAML (in schema) | GAFTA roles mapped to Cosolvent supply/demand/facilitator categories  | In schema §19 ✅                     |
| **Referenced standards inventory** | YAML (in schema) | Standards incorporated by reference — candidates for future ingestion | In schema §20 ✅                     |
| **Process recipe**                 | Markdown         | Documented workflow for curating additional content                   | `recipe.md` ✅                       |
| **Gap detection prompt**           | Markdown         | Editable LLM prompt instructing the model to declare missing context and format a pull signal | `prompts/gap_detection.md` 🔲 |

### 4.2 — Current Content Inventory

> **🟡 Vertical pivot (2026-07):** the **active** demo corpus is now **machinery/manufacturing** — `inputs/global_machinery_marketplace_whitepaper.pdf` → `schemas/generated_schema.yaml` + `generated_refs.jsonl`, plus the mfgllmwiki pages → `wiki_refs.jsonl`. The grain corpus below has been retired to `inputs_archive_grain/` and is kept as a proven second vertical (`test_cross_vertical.py`). The grain table is preserved for historical reference.

**Grain Trading Vertical (Agricultural Commodity Trade) — archived:**

| Document                                    | Source         | Status                         | Output                                                  |
| ------------------------------------------- | -------------- | ------------------------------ | ------------------------------------------------------- |
| GAFTA Contract No. 27 (2025)                | PDF from GAFTA | ✅ Converted & schema extracted | `outputs/27_2025.md`, `outputs/grain_trade_schema.yaml` |
| GAFTA Contract No. 48                       | TBD            | 🔲 Not yet acquired             | —                                                       |
| GAFTA Contract No. 100                      | TBD            | 🔲 Not yet acquired             | —                                                       |
| GAFTA Weighing Rules No. 123                | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| GAFTA Sampling Rules No. 124                | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| GAFTA Arbitration Rules No. 125             | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| GAFTA Methods of Analysis No. 130           | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| GAFTA Fumigation Rules No. 132              | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| GAFTA Insurance Terms No. 72                | TBD            | 🔲 Referenced in Contract 27    | —                                                       |
| Canadian Grain Commission grading standards | CGC website    | 🔲 Identified                   | —                                                       |
| USDA/FGIS grain grading standards           | USDA website   | 🔲 Identified                   | —                                                       |

---

## 5. Roadmap Phases

### Phase 1 — Foundation (Current)

**Goal:** Establish tooling and process; produce first domain schema from a reference contract.

- [x] Set up PDF-to-Markdown conversion pipeline (`marker-pdf`)
- [x] Set up URL-to-Markdown conversion pipeline (`convert_url.py`)
- [x] Convert first reference document (GAFTA Contract No. 27)
- [x] Extract domain schema from converted document
- [x] Map participant roles to Cosolvent categories
- [x] Document the curation process (`recipe.md`)
- [x] Create project roadmap (this file)
- [x] Build web GUI for document ingestion and conversion (`server.py` + `static/index.html`)
- [x] Add LLM-assisted schema analysis via OpenRouter (`schema_analyzer.py`)
- [x] Create editable prompt template for schema extraction (`prompts/schema_analysis.md`)
- [x] Add Analyses page to GUI for reviewing LLM-generated schema proposals
- [x] Add provenance tracking — source URL, acquisition method, timestamps recorded for every document (`provenance.py`)
- [x] Smart URL detection — URL fetch auto-detects HTML vs. downloadable files (e.g. PDFs) and routes to the correct pipeline
- [x] YAML frontmatter injection — every output markdown includes `source_url` for downstream chunking
- [x] LLM-assisted metadata extraction — imputes org, author, date, doc type for locally-uploaded files (`metadata_extractor.py`)
- [x] Editable metadata extraction prompt (`prompts/metadata_extraction.md`)
- [x] CSV and Excel (.xlsx) tabular data conversion — renders spreadsheets as Markdown tables with full provenance (`convert_tabular.py`)
- [x] Docker packaging — `Dockerfile` + `docker-compose.yml` for deployment; local development workflow unchanged

### Phase 2 — Schema Enrichment

**Goal:** Process additional contracts and standards to broaden and refine the domain schema.

- [ ] Acquire additional GAFTA contracts (No. 48, No. 100) covering different trade configurations (FOB terms, specific commodities)
- [ ] Convert and run schema analysis on additional contracts (using GUI or CLI)
- [ ] Review LLM-generated proposals in `analyses/` and merge approved additions into `schemas/grain_trade_schema.yaml`
- [ ] Merge schemas — identify common entities, resolve conflicts, note configuration-dependent variations
- [ ] Process referenced GAFTA standards (Nos. 72, 123, 124, 125, 130, 132)
- [ ] Add government grading standards (Canadian Grain Commission, USDA/FGIS)
- [ ] Define metadata tag vocabulary for grain trading vertical

### Phase 3 — Ingestion Preparation ✅ (largely complete)

**Goal:** Prepare content in the format required by the Cosolvent `reference_library` table.

- [x] Define chunking strategy that preserves clause-level coherence (`chunk_and_embed.py`; `docs/DECISION-005`)
- [x] Tag each document chunk with vertical-specific metadata (LLM topic-tagging vs `reference_metadata_schema.py` vocab)
- [x] Leverage provenance metadata (source URL, source type, document title) from `provenance/` as chunk-level citation data
- [x] Generate embeddings for reference document chunks (1536-dim `text-embedding-3-small` via OpenRouter)
- [x] Create seed data scripts for the `reference_library` table (`seed_reference_library.py`; Cosolvent `load-references`; `export_references.py` adapter)
- [x] Write domain Q&A system prompts (`prompts/qa_system.md`, `prompts/qa_system_manufacturing.md`)
- [x] Define the `reference_metadata_schema` configuration (grain **and** manufacturing; `reference_metadata_schema.py`)
- [x] Define database schema for `knowledge_gap_signals` (`migrations/add_gap_signals.sql`)

### Phase 4 — Integration Testing 🟡 (in progress)

**Goal:** Validate that curated content works correctly when loaded into a Cosolvent instance.

- [x] Load curated content into a Cosolvent test instance (real pgvector seed via `test_db_integration.py` + `docker-compose.test.yml`)
- [x] Verify metadata-filtered vector search returns relevant results (covered by the integration test)
- [ ] Test domain Q&A with grain trading questions
- [ ] Verify user-context scoping (e.g., a buyer in Japan gets Japan-relevant regulations)
- [ ] Test cross-collection retrieval (reference library + participant data)
- [ ] Validate facilitator role recommendations based on schema
- [ ] Test the "Curatorial Pull" loop: Intentionally query missing information, verify the fallback response, verify the generation of a curation signal, ingest the missing document, and verify the updated response.

### Phase 5 — Additional Verticals (Future)

**Goal:** Demonstrate that the curation process generalises beyond grain trading.

- [ ] Identify a second vertical (e.g., remote mental health, specialty manufacturing)
- [ ] Apply the curation recipe to the new vertical's reference documents
- [ ] Extract a domain schema for the new vertical
- [ ] Validate that the same tooling and process works across verticals

---

## 6. Dependencies

| Dependency                         | Project        | Status                        | Impact                                           |
| ---------------------------------- | -------------- | ----------------------------- | ------------------------------------------------ |
| `reference_library` table schema   | Cosolvent | ✅ Implemented (§16.2)          | Ingestion contract now targets the live table    |
| `reference_metadata_schema` config | Cosolvent | 🟡 Metadata-filtered retrieval works; per-vertical tag vocab lives here (`reference_metadata_schema.py`) | Phase 3 metadata tagging done on this side |
| Domain Q&A chat mode               | Cosolvent | ✅ Implemented — `/api/ai/knowledge` grounded Q&A with citations | Phase 4 testing unblocked |
| Embedding model choice             | Cosolvent | ✅ `text-embedding-3-small` (1536) — matched on both sides | Embeddings match; do not diverge the model |
| Knowledge gap signals              | Cosolvent | ✅ `knowledge_gap_signals` table + admin `/gaps` | Enables the pull-signal loop (§2.8) |
| Composable retrieval interface     | Cosolvent | 🔲 Not yet implemented         | Phase 4 cross-collection testing depends on this |

---

## 7. Relationship to Whitepaper Concepts

The Knowledge Slot operationalises several whitepaper concepts:

| Whitepaper Section                                          | Concept                                                                   | How Knowledge Slot Addresses It                                                               |
| ----------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| §4.13 — Authoritative Information Availability              | Fragmented, hard-to-find reference material thins markets                 | Centralises authoritative documents in a searchable, AI-accessible library                    |
| §5.13 — Curating and Distributing Authoritative Information | Reference library creation, contextual delivery, cross-reference mapping  | The curation workflow + metadata-filtered retrieval + user-context scoping                    |
| §6.6 — AI-Curated Authoritative Information                 | RAG over reference library, cross-reference mapping, natural language Q&A | Domain Q&A mode, vertical-supplied prompts, citation-backed answers                           |
| §5.7 — Reducing Information Asymmetry                       | Reference libraries as an intervention                                    | Shared access to authoritative standards reduces knowledge imbalance between buyer and seller |
| §5.11 — Simplifying Regulatory Compliance                   | Compliance databases, automated checking                                  | Reference library tagged by jurisdiction enables compliance-aware retrieval                   |

---

## 8. Open Questions

1. **Schema versioning:** How should the domain schema evolve as new contracts are processed? Additive-only, or refinement allowed?
2. **Cross-contract conflicts:** What happens when two GAFTA contracts define the same entity differently (e.g., different tolerance rules for FOB vs. CIF terms)?
3. **Chunking strategy:** What chunking approach preserves clause-level coherence while staying within embedding model context limits?
4. **Multi-vertical schema inheritance:** Should schema formats support inheritance (a base trading schema extended by corridor-specific schemas)?
5. **Sponsor curation UX:** What does the admin workflow look like for a non-technical sponsor uploading and tagging documents, and how do they manage the Curatorial Pull Signal queue to address high-value knowledge gaps?
6. **Update monitoring:** ~~How should the system handle updates to reference documents?~~ → Addressed by `docs/DECISION-002-staleness-detection.md` (periodic automated scanning with curator-facing alerts).

> **Note:** Additional open design decisions are tracked in `docs/DECISION-*.md`. See `docs/DECISION-000-architecture-and-integration.md` for the foundational architecture specification and a status summary of all pending questions.
