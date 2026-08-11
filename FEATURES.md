<!--Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.-->

# CommonContext — Product Feature Sheet

> **AI-powered curation tooling for building sponsor-managed reference libraries in Cosolvent marketplace deployments.**

| Icon | Meaning |
|:---:|---|
| ✅ | **Implemented** — working in the current codebase |
| 🔜 | **Planned** — on the development roadmap, not yet built |

---

## Document Ingestion & Conversion

| | Feature | Description |
|:---:|---|---|
| ✅ | **PDF Conversion** | PDF → clean Markdown via pymupdf4llm (fast mode) or marker-pdf (OCR mode). Supports image extraction from embedded figures. |
| ✅ | **HTML Conversion** | HTML → Markdown via BeautifulSoup + markdownify with content extraction and link handling. |
| ✅ | **URL Fetching** | Enter a URL to fetch and convert any web page. Smart auto-detection routes HTML pages vs. downloadable files (e.g., PDFs) to the correct pipeline. |
| ✅ | **CSV & Excel Conversion** | Spreadsheets (.csv, .xlsx) rendered as Markdown tables with full provenance tracking. |
| ✅ | **Markdown Direct Import** | Markdown files imported without conversion — metadata and provenance still tracked. |
| ✅ | **Batch Conversion** | Convert all pending source files in one click — process an entire document backlog at once. |
| ✅ | **YAML Frontmatter Injection** | Every output Markdown includes `source_url` metadata for downstream chunking and citation. |
| 🔜 | **Image / OCR Ingestion** | Direct image-to-text conversion via Pillow + OCR pipeline for scanned documents and certificates. |
| 🔜 | **DOCX Conversion** | Microsoft Word → Markdown via python-docx. |

---

## Schema Intelligence

| | Feature | Description |
|:---:|---|---|
| ✅ | **LLM-Assisted Schema Extraction** | Converted documents are analysed by an LLM (via OpenRouter) to extract structured domain schemas — entities, relationships, controlled vocabularies, and classification hierarchies. |
| ✅ | **Editable Prompt Templates** | The schema analysis prompt lives in `prompts/schema_analysis.md` — edit the file to tune extraction behaviour, output format, or domain-specific instructions. No code changes required. |
| ✅ | **Schema Proposals** | LLM-generated schema proposals saved to `analyses/` for human review before merging into the canonical schema. |
| ✅ | **Domain Schema Repository** | Extracted schemas stored as YAML in `schemas/` — structured vocabularies, entity definitions, participant role mappings, and standards inventories. |
| ✅ | **Participant Role Mapping** | Domain-specific roles (e.g., GAFTA trade roles) mapped to Cosolvent's `supply` / `demand` / `facilitator` categories. |
| ✅ | **Referenced Standards Inventory** | Standards incorporated by reference in source documents (e.g., ISO, GAFTA rules) identified and catalogued as candidates for future ingestion. |
| 🔜 | **Schema Merging** | Cross-document schema analysis: identify common entities, resolve conflicts, and note configuration-dependent variations when processing multiple contracts or standards. |
| 🔜 | **Multi-Vertical Schema Inheritance** | Base trading schema extended by corridor-specific or vertical-specific schemas — reuse common entities across deployments. |

---

## Provenance & Metadata

| | Feature | Description |
|:---:|---|---|
| ✅ | **Provenance Tracking** | Every document records source URL, acquisition method (upload / URL fetch), and timestamps in a structured JSON record. |
| ✅ | **LLM-Assisted Metadata Extraction** | For locally-uploaded files without a source URL, the LLM imputes organisation, author, publication date, and document type from the document content. |
| ✅ | **Editable Metadata Prompt** | The metadata extraction prompt lives in `prompts/metadata_extraction.md` — customisable per vertical. |
| ✅ | **Provenance API** | Programmatic access to provenance records for downstream citation and chunking workflows. |

---

## Web GUI

| | Feature | Description |
|:---:|---|---|
| ✅ | **Single-Page Application** | Browser-based curation interface served at `localhost:8400` — no installation beyond Python. |
| ✅ | **Drag-and-Drop File Upload** | Upload PDFs, HTML files, and Markdown documents directly via the browser. |
| ✅ | **URL Fetch Interface** | Enter a URL and convert the page in one step. |
| ✅ | **Document Viewer** | Preview converted Markdown content with provenance info bar (source URL, acquisition date, document type). |
| ✅ | **Schema Browser** | View and navigate domain-specific YAML schemas within the GUI. |
| ✅ | **Analysis Browser** | View and compare LLM-generated schema proposals side-by-side. |
| ✅ | **One-Click Batch Processing** | Process all pending source files from the GUI. |
| ✅ | **One-Click Launcher** | `launch-gui.bat` (Windows) opens the GUI with a single double-click. |

---

## API & CLI

| | Feature | Description |
|:---:|---|---|
| ✅ | **FastAPI Backend** | Full REST API powering both the GUI and programmatic access. |
| ✅ | **OpenAPI Documentation** | Interactive Swagger UI at `/docs` and ReDoc at `/redoc`. |
| ✅ | **CLI Scripts** | Original command-line scripts remain available for automation: `convert_pdf.py`, `convert_url.py`, `convert_tabular.py`, `schema_analyzer.py`, `metadata_extractor.py`. |
| ✅ | **Docker Packaging** | `Dockerfile` + `docker-compose.yml` for containerised deployment. Local development workflow unchanged. |
| ✅ | **Configurable AI Provider** | LLM model and API key configurable via environment variables (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`). Default: Gemini 2.0 Flash via OpenRouter. |

---

## Cosolvent Integration Readiness

| | Feature | Description |
|:---:|---|---|
| ✅ | **Vertical-Agnostic Design** | The curation tooling works for any Cosolvent marketplace deployment — not locked to a single industry. |
| ✅ | **Cosolvent-Compatible Metadata Schema** | Vertical-specific tag vocabularies designed to map directly to the Cosolvent `reference_metadata_schema` configuration. |
| ✅ | **Process Recipe** | Documented end-to-end workflow (`recipe.md`) for curating content for any new vertical. |
| 🔜 | **Chunking for Reference Library** | Clause-level coherent chunking strategy that preserves document structure while staying within embedding model context limits. |
| 🔜 | **Metadata-Tagged Chunks** | Each document chunk tagged with vertical-specific metadata for pre-filtered vector search in Cosolvent. |
| 🔜 | **Embedding Generation** | Generate embeddings for reference chunks using the same model as Cosolvent's participant embeddings — ensuring cross-collection similarity search. |
| 🔜 | **Seed Data Scripts** | Scripts to load curated content directly into Cosolvent's `reference_library` table. |
| 🔜 | **Domain Q&A System Prompts** | Vertical-specific system prompts for the Cosolvent chatbot's "domain knowledge" mode. |
| 🔜 | **Curatorial Pull Signal** | Gap detection prompt and signal schema — when users ask questions the reference library can't answer, a structured signal alerts the curator to the specific knowledge gap. |
| 🔜 | **Staleness Detection** | Periodic automated scanning of reference documents for indicators of change or supersession — source URL monitoring, LLM-assisted web search, and age-based review thresholds. |

---

## Content Inventory (Grain Trading Vertical)

| | Document | Source | Status |
|:---:|---|---|---|
| ✅ | GAFTA Contract No. 27 (2025) | PDF from GAFTA | Converted & schema extracted |
| 🔜 | GAFTA Contract No. 48 | TBD | Not yet acquired |
| 🔜 | GAFTA Contract No. 100 | TBD | Not yet acquired |
| 🔜 | GAFTA Weighing Rules No. 123 | Referenced in Contract 27 | Not yet acquired |
| 🔜 | GAFTA Sampling Rules No. 124 | Referenced in Contract 27 | Not yet acquired |
| 🔜 | GAFTA Arbitration Rules No. 125 | Referenced in Contract 27 | Not yet acquired |
| 🔜 | Canadian Grain Commission grading standards | CGC website | Identified |
| 🔜 | USDA/FGIS grain grading standards | USDA website | Identified |

---

## Architecture Summary

| Component | Technology |
|---|---|
| **Language** | Python 3.10+ |
| **API Framework** | FastAPI |
| **PDF Processing** | pymupdf4llm (fast) · marker-pdf (OCR) |
| **HTML Processing** | BeautifulSoup · markdownify |
| **Tabular Processing** | openpyxl (Excel) · csv (CSV) |
| **AI Provider** | OpenRouter (configurable model) |
| **Schema Format** | YAML |
| **Provenance Format** | JSON |
| **Containerisation** | Docker / Docker Compose |
| **Frontend** | Single-page HTML/CSS/JS |
| **License** | Copyright © 2026 Mustafa Uzumeri |

---

## Scope Boundaries

CommonContext is the **content preparation and curation tooling** for a Cosolvent marketplace's reference library. It does not:

- **Host the reference library at runtime** — that is Cosolvent's `reference_library` table (§16.2)
- **Serve domain Q&A** — that is Cosolvent's chatbot in "domain knowledge" mode
- **Store participant documents** — those follow Cosolvent's three-layer privacy model, architecturally separate from reference material

The sponsor curates content here; Cosolvent serves it to participants.

---

## Ecosystem

| Project | Role |
|---|---|
| **Cosolvent** | Matching engine that hosts the `reference_library` table and serves domain Q&A |
| **MarketForge** | Market configuration and deployment orchestration |
| **ClientSynth** | Synthetic participant generation for testing and demos |
