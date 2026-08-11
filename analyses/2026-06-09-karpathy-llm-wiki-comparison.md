<!-- Copyright © 2026 Mustafa Uzumeri. All rights reserved. -->

# Analysis: Karpathy's llm-wiki vs. DeeperPoint CommonContext & mfgllmwiki

> **Date:** 2026-06-09  
> **Author:** Antigravity Agent & Mustafa Uzumeri  
> **Context:** Architectural comparison of Andrej Karpathy's compiled knowledge pattern (llm-wiki) and the DeeperPoint CommonContext dynamic grounding system.

---

## 1. Executive Summary & Verdict on Alignment

The core approaches **align almost perfectly**. 

Both frameworks reject the standard industry practice of query-time RAG (running dynamic vector searches on raw, uncurated documents on the fly) because it lacks knowledge accumulation, fails to handle contradictions cleanly, and forces the LLM to re-synthesize relationships from scratch every time. 

Instead, both architectures compile raw inputs *incrementally* at ingestion time into a **persistent, compounding knowledge base (a domain wiki)**. In this design, links, summaries, entities, and contradictions are compiled and maintained by the LLM once, and then queried repeatedly.

*   [mfgllmwiki README.md](file:///c:/Users/MustafaUzumeri/GitHub/mfgllmwiki/README.md) represents a direct implementation of Karpathy's "LLM Wiki" concept: an LLM-maintained folder of interlinked Markdown pages (`concepts`, `entities`, `sources`, `stories`) equipped with automated ingestion, semantic linting, and git version tracking.
*   [CommonContext](file:///c:/Users/MustafaUzumeri/GitHub/CommonContext/docs/DECISION-000-architecture-and-integration.md) (formerly `CommonContext`) is the platform-level integration layer. It maps this compounding Markdown wiki into SQL tables (`reference_documents` and `reference_chunks` with JSONB schemas) to ground transactional prompts and queries inside the `Cosolvent` marketplace runtime.

---

## 2. Architectural & Operational Comparison Matrix

| Dimension | Karpathy's `llm-wiki` Pattern | `mfgllmwiki` / `CommonContext` Framework | Alignment Status |
| :--- | :--- | :--- | :--- |
| **Primary Philosophy** | **Compounding Artifact**: Incrementally integrates source knowledge; resolves contradictions at ingest; doesn't re-derive from scratch on query. | **Domain Grounding Engine**: Curation pipeline organizes material into structured topics; maps Markdown files to vector/relational databases for live transactions. | **Identical**. Both prioritize compiling a persistent, interlinked knowledge database over raw retrieval. |
| **Three-Layer Model** | 1. **Raw Sources** (immutable files)<br>2. **The Wiki** (concepts, entities)<br>3. **The Schema** (`CLAUDE.md` / rules) | 1. **Raw Inputs** (PDFs, URLs, tabular)<br>2. **The Wiki** (`concepts`, `entities`, `sources`, `stories`) & Database tables<br>3. **Domain Schemas** ([manufacturing_domain_schema.yaml](file:///c:/Users/MustafaUzumeri/GitHub/mfgllmwiki/schemas/manufacturing_domain_schema.yaml) & prompts) | **Aligned**. Both isolate immutable sources from LLM-written wiki pages, using a schema config to govern structure. |
| **Ingestion (`/wiki-ingest`)** | Incremental integration, planning edits across 10–15 files, writing summaries, linking, logging. | [wiki-ingest.md](file:///c:/Users/MustafaUzumeri/GitHub/mfgllmwiki/.agents/workflows/wiki-ingest.md) compiles files, extracts specs, inserts inline wikilinks with line ranges (e.g. `[[sources/source_slug#L23-L45]]`), logs to `log.md`. | **Identical**. Both rely on an LLM proposing a multi-file integration plan, obtaining confirmation, and committing changes. |
| **Linting (`/wiki-lint`)** | Periodic checks for contradictions, stale claims, orphan pages, link gaps, and duplicates. | [wiki_lint_agent.md](file:///c:/Users/MustafaUzumeri/GitHub/mfgllmwiki/prompts/wiki_lint_agent.md) randomly audits page batches for contradictions, link gaps, and redundancies; writes code resolutions. | **Aligned**. Both run programmatic and semantic checks to preserve wiki health and keep cross-references fresh. |
| **Index & Log** | Content-based `index.md` (content directory used as primary LLM map) and chronological parseable `log.md`. | `wiki/index.md` maps topics/materials; `wiki/log.md` appends parsed, standardized edit lines. | **Identical**. Both use a structured `index.md` and chronological `log.md` to prevent context bloat and audit edits. |

---

## 3. How CommonContext Extends Karpathy's Pattern for Production

Because `CommonContext` is designed to power a live B2B marketplace platform (`Cosolvent`), it introduces several elements that go beyond Karpathy's personal/desktop workspace model:

1.  **Dual-Table SQL Grounding:** 
    While Karpathy's pattern is designed to run in Obsidian or flat directories, `CommonContext` maps files into two database tables—`reference_documents` (metadata) and `reference_chunks` (embeddings)—to support low-latency SQL filtering and hybrid RAG searches at scale (see [DECISION-004-reference-table-design.md](file:///c:/Users/MustafaUzumeri/GitHub/CommonContext/docs/DECISION-004-reference-table-design.md)).
2.  **Demand-Driven Curation (The Pull System):** 
    `CommonContext` closes the loop between live transactions and offline curation. When a query fails to match verified references, it serves an "unverified fallback" to the user and logs a signal to `knowledge_gap_signals`. This informs the curator of missing domain knowledge that has immediate business value (see [DECISION-001-pull-signal-transport.md](file:///c:/Users/MustafaUzumeri/GitHub/CommonContext/docs/DECISION-001-pull-signal-transport.md)).
3.  **Configurable, Document-Type-Specific Chunking:** 
    Rather than generic character chunking, `CommonContext` uses the YAML domain schema to parse files by actual clause boundaries (e.g. GAFTA contract clauses or ASTM specification tables) for exact citation.

---

## 4. Strengths to Draw from Karpathy to Strengthen mfgllmwiki & CommonContext

To expand and solidify our implementation, we should adopt the following four design principles from Karpathy's Gist:

### A. Filing Complex Queries & Syntheses Back Into the Wiki
*   **The Gap:** Currently, `mfgllmwiki` focuses on ingesting new pages and linting existing ones. There is no workflow for taking the result of a complex synthesis query (such as comparing two machines, or evaluating Ontario shipping regulations) and filing it back as a permanent wiki page.
*   **The Solution:** Implement a **"Query & Save"** pathway in `mfgllmwiki`'s web dashboard or as a slash command. When a user runs a comparison or multi-document analysis, the agent should structure the response as a markdown concept page (e.g. `wiki/pages/concepts/accurpress_7254_vs_rebel_pro_comparison.md`), add it to `wiki/index.md`, and write it to disk. This ensures that custom intelligence compounds instead of disappearing into chat history.

### B. Upgrading `index.md` to a Semantic Router Map
*   **The Gap:** Karpathy reads a summary-enriched `index.md` file *first* during query execution to determine which files to drill into, which works at moderate scales without needing full vector database queries. Our `wiki/index.md` is currently a catalog of categories and links, and does not include one-line summaries.
*   **The Solution:** Update the `wiki/index.md` generator to append a concise, one-line semantic summary for each page. When performing retrieval in `mfgllmwiki` or `CommonContext`, feed this index file to the LLM router agent so it can perform deterministic file routing before calling the database or executing vector searches.

### C. Multimodal Ingestion & Local Image Downloader
*   **The Gap:** Specialty manufacturing documentation (spec sheets, blueprints, tooling standards) is often highly visual or tabular. Plain-text markdown conversion can miss these layout details.
*   **The Solution:** Add local attachment downloader support in `convert_url.py` and the FastAPI ingestion web engine. When a source is fetched, save its diagrams and images locally to `wiki/Clippings/assets/`. Configure the ingestion agent to support multimodal models (e.g. `gemini-2.5-pro` or `gemini-3.5-flash`) so it can read these drawings directly to verify machine dimensions and physical attributes.

### D. Obsidian Frontmatter Integration & Presets
*   **The Gap:** The wiki files are frequently browsed in Obsidian. We can make the wiki immediately more valuable to human editors by adopting Obsidian-native plugins.
*   **The Solution:** Update [mfgllmwiki/README.md](file:///c:/Users/MustafaUzumeri/GitHub/mfgllmwiki/README.md) to document standard Obsidian configurations:
    *   **Dataview Query Presets:** Add standard markdown code blocks displaying Dataview queries (e.g. to list all pages where `status: contradicted`, or list all machine entities with their year of manufacture).
    *   **Marp Slide Presets:** Standardize heading styles so concept summaries can be converted into presentation decks instantly using Marp.
