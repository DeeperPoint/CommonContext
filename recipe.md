<!-- Copyright © 2026 Mustafa Uzumeri. All rights reserved. -->

# Knowledge Slot Curation Recipe

> **Purpose:** A living document that captures the evolving process, tools, and insights for curating domain knowledge into the Knowledge Slot format required by the Cosolvent marketplace framework.
>
> **Status:** Draft — actively evolving as new contracts and reference documents are processed.
>
> **Date started:** 2026-02-20

---

## 1. Overview

The Knowledge Slot is a sponsor-curated reference library that sits alongside participant data in a Cosolvent marketplace deployment. It provides the domain knowledge that the AI uses to answer questions, validate compliance, support matching decisions, and generate contextual guidance.

This recipe documents **how to build that library** — from raw source documents (PDFs, spreadsheets, web pages, contracts, regulations) through conversion, schema extraction, and structuring into a format the Knowledge Slot can ingest.

### What the Knowledge Slot is NOT

- It is **not** participant data (that's the Context Slot)
- It is **not** AI model configuration (that's the Intelligence Slot)
- It is **not** a general-purpose document dump — it is a **curated, tagged, structured** collection of authoritative reference material

---

## 2. Process Steps

### Step 1 — Source Document Acquisition

Identify and obtain authoritative documents for the target vertical. For grain trading, these include:

| Source Type                 | Examples                                                | Where to Find                          |
| --------------------------- | ------------------------------------------------------- | -------------------------------------- |
| **Standard contracts**      | GAFTA Contract No. 27, No. 48, No. 100                  | GAFTA publications (members.gafta.com) |
| **Trade rules**             | GAFTA Weighing Rules No. 123, Sampling Rules No. 124    | GAFTA publications                     |
| **Grading standards**       | Canadian Grain Commission grades, USDA/FGIS standards   | Government agencies                    |
| **Regulatory requirements** | Phytosanitary rules, MRL thresholds, import regulations | Destination country agencies           |
| **Industry guides**         | Shipping best practices, storage protocols              | Industry associations                  |

**Key insight:** Start with the most comprehensive single document — a standard contract — because it references most of the other document types. The GAFTA contract alone referenced 7 additional GAFTA standards, IUA classification rules, and 5 excluded international conventions.

**Documents processed so far:**

- [x] GAFTA Contract No. 27 (2025) — Canadian and US Grain in Bulk, CIF/CIFFO/C&F/C&FFO Terms
- [ ] GAFTA Contract No. 48 — (identified as next candidate)
- [ ] GAFTA Contract No. 100 — (identified as next candidate)

**Provenance tracking:** Every document acquired — whether uploaded as a file or fetched from a URL — has its origin recorded in `provenance/`. This includes the source URL, acquisition method, HTTP headers, and timestamps. The provenance data ensures that when chunks are eventually embedded and retrieved, each chunk can cite its original authoritative source. See `provenance.py`.

### Step 2 — PDF to Markdown Conversion

**Tool:** `marker-pdf` (Python, via `.venv` virtual environment)

**Script:** `convert_pdf.py`

**Command:**
```powershell
.venv\Scripts\python.exe convert_pdf.py inputs/<filename>.pdf --output outputs/<filename>.md
```

**Environment requirements:**
- Python 3.12 virtual environment (Python 3.14 has wheel compatibility issues)
- `marker-pdf` and `pymupdf4llm` installed in `.venv`
- First run downloads ~1–2 GB of ML models (cached for subsequent runs)

**Quality observations (from GAFTA 27 conversion):**
- Excellent preservation of document structure (headings, numbered clauses, sub-clauses)
- Tables converted accurately to Markdown format
- Lists and nested items maintained
- Some OCR artifacts possible in scanned documents — review recommended
- Page headers/footers may appear inline — manual cleanup may be needed

**Alternative tool:** `pymupdf4llm` — lighter weight, no ML models, faster, but lower quality on complex layouts. Consider for simple documents.

### Step 2b — Web Page to Markdown Conversion

**Tool:** `requests` + `BeautifulSoup` + `markdownify` (all pre-installed in `.venv`)

**Script:** `convert_url.py`

**Command:**
```powershell
.venv\Scripts\python.exe convert_url.py https://example.com/page
.venv\Scripts\python.exe convert_url.py https://example.com/page -o outputs/page_name.md
.venv\Scripts\python.exe convert_url.py https://example.com/page --no-links
.venv\Scripts\python.exe convert_url.py https://example.com/page --include-images
```

**What it does:**
1. Fetches the page with a standard browser User-Agent
2. Identifies the main content area (`<main>`, `<article>`, or content-classed `<div>`)
3. Strips navigation, headers, footers, sidebars, ads, and other boilerplate
4. Converts the remaining HTML to clean Markdown with ATX headings
5. Prepends a YAML frontmatter header with the source URL and page title
6. Writes the output to `outputs/` (auto-named from URL if `-o` is not specified)

**Options:**
- `--no-links` — strip hyperlinks (useful for cleaner reference text)
- `--include-images` — preserve image references (default: images are stripped)
- `-o` / `--output` — specify output path (default: auto-generated from URL in `outputs/`)

**When to use this vs. PDF conversion:**
- Use `convert_url.py` for web-published reference material (regulations, guides, trade body pages)
- Use `convert_pdf.py` for formal documents distributed as PDFs (contracts, standards, official publications)
- **Auto-detection:** The GUI's URL Fetch automatically detects whether a URL serves an HTML page or a downloadable file (e.g. PDF). HTML pages go through the URL pipeline; downloadable files are saved to `inputs/` and converted via the file pipeline. In both cases, the source URL is recorded as provenance.

### Step 2c — Document Metadata Extraction (for local files)

When a document arrives as a local file (e.g., received by email, downloaded manually) rather than via a tracked URL, it lacks automatic provenance. The metadata extractor uses an LLM to read the converted markdown and impute structured citation metadata.

**Tool:** `metadata_extractor.py` — LLM-assisted extraction via OpenRouter

**GUI:** Click the 📋 **Metadata** button next to any converted document in the GUI.

**CLI:**
```powershell
.venv\Scripts\python.exe metadata_extractor.py outputs/<filename>.md
.venv\Scripts\python.exe metadata_extractor.py outputs/<filename>.md --model anthropic/claude-sonnet-4
```

**What gets extracted:**

| Field                | Example                                      |
| -------------------- | -------------------------------------------- |
| Title & identifier   | "GAFTA Contract No. 27 (2025 Edition)"       |
| Issuing organisation | "Grain and Feed Trade Association (GAFTA)"   |
| Author(s)            | Individual names and roles if mentioned      |
| Date of publication  | "2025" (year or full ISO date)               |
| Document type        | contract, standard, regulation, guide, etc.  |
| Geographic scope     | Jurisdictions and trade corridors            |
| Referenced standards | External documents incorporated by reference |
| Confidence notes     | What was clearly stated vs. inferred         |

**How it works:**
1. Loads the extraction prompt from `prompts/metadata_extraction.md` (editable)
2. Reads the converted Markdown and any existing provenance record
3. Sends both to an LLM via OpenRouter with structured extraction instructions
4. The LLM returns YAML metadata with citation-quality fields
5. Results are merged into the document's `provenance/` JSON record
6. The output markdown's YAML frontmatter is updated with the extracted title
7. In the GUI, results are shown in the document viewer and the Source column updates

**Key insight:** This is designed for the ~5% of documents that arrive without a URL. For URL-sourced documents, the source URL is captured automatically during fetch. Metadata extraction can still be run on URL-sourced documents to enrich their provenance with title, organization, and other structured fields.

### Step 2d — Tabular Data Conversion (CSV / Excel)

Many domain reference sources include structured tabular data — pricing schedules, compliance checklists, grading tables, port specifications, and regulatory thresholds. These are often distributed as CSV files or Excel workbooks.

**Tool:** `convert_tabular.py` — Python `csv` module (CSV) + `openpyxl` (XLSX)

**GUI:** Upload a `.csv` or `.xlsx` file via the GUI and click Convert — works identically to PDF/HTML uploads.

**CLI:**
```powershell
.venv\Scripts\python.exe convert_tabular.py inputs/data.csv
.venv\Scripts\python.exe convert_tabular.py inputs/workbook.xlsx -o outputs/custom.md
```

**What it does:**

- **CSV files** → a single GitHub-flavored Markdown table with auto-detected delimiter (comma, semicolon, tab, pipe)
- **XLSX files** → one `## SheetName` section per worksheet, each containing a Markdown table

**Output includes:**
- YAML frontmatter with `source_file`, `row_count`, `column_count` (CSV) or `sheet_count`, `total_rows` (XLSX)
- Properly escaped cell values (pipe characters, newlines)
- Provenance tracking — identical to PDF and URL sources

**When to use this:**
- Compliance checklists and regulatory tables (e.g., MRL thresholds by destination country)
- Port specifications and logistics schedules
- Grading standards in tabular form
- Pricing or tariff reference data
- Any structured reference data distributed as spreadsheets

### Step 3 — Domain Schema Extraction

After conversion, analyse the Markdown to extract a domain schema — the structured vocabulary of the vertical.

**Tool:** `schema_analyzer.py` — LLM-assisted analysis via OpenRouter

**GUI:** Click the 🔬 **Analyse** button next to any converted document in the GUI.

**CLI:**
```powershell
.venv\Scripts\python.exe schema_analyzer.py outputs/<filename>.md
.venv\Scripts\python.exe schema_analyzer.py outputs/<filename>.md --schema schemas/grain_trade_schema.yaml
.venv\Scripts\python.exe schema_analyzer.py outputs/<filename>.md --model anthropic/claude-sonnet-4
```

**How it works:**
1. Loads the analysis prompt from `prompts/schema_analysis.md` (editable)
2. Reads the converted Markdown document and the existing domain schema (auto-detected from `schemas/`)
3. Sends both to an LLM via OpenRouter with structured extraction instructions
4. The LLM returns proposed additions, refinements, roles, referenced standards, and excluded conventions
5. Results are saved as YAML to `analyses/<filename>_analysis.yaml`
6. In the GUI, results are shown in the document viewer and listed on the Analyses page

**Configuration:**

| Setting         | How to configure                             | Default                                               |
| --------------- | -------------------------------------------- | ----------------------------------------------------- |
| API key         | `OPENROUTER_API_KEY` env var or `.env` file  | Auto-discovered from `DPWebsitePublishingSystem/.env` |
| LLM model       | `OPENROUTER_MODEL` env var or `--model` flag | `google/gemini-2.0-flash-001`                         |
| Prompt template | Edit `prompts/schema_analysis.md`            | Provided with structured extraction instructions      |

**Prompt customisation:** The analysis prompt at `prompts/schema_analysis.md` is loaded at runtime and supports variable substitution (`{{DOCUMENT_CONTENT}}`, `{{EXISTING_SCHEMA}}`, etc.). To change the analysis behaviour — adjust entity categories, add vertical-specific instructions, change the output format — edit this file directly. No code changes required.

**Approach:** The prompt instructs the LLM to identify:

1. **Entities** — the major conceptual objects (goods, quantity, pricing, shipment, payment, etc.)
2. **Fields per entity** — the attributes that describe each entity (type, allowed values, defaults)
3. **Relationships** — how entities reference each other (pricing references quantity units; insurance depends on delivery terms)
4. **Participant roles** — who the parties are and what roles they play
5. **Referenced standards** — what external documents are incorporated by reference
6. **Excluded conventions** — what the source explicitly excludes (critical for AI to avoid citing)

**Output format:** YAML analysis file saved to `analyses/` (see `analyses/<filename>_analysis.yaml`). The existing production schema is maintained separately in `schemas/` (see `schemas/grain_trade_schema.yaml`).

**Why YAML:**
- Human-readable — sponsors can review and edit
- Machine-parseable — can be ingested by the Knowledge Slot system
- Matches cosolvent-beta's configuration pattern (marketplace.yaml)
- Supports comments for provenance and rationale

**Key insight:** The schema is not just a data dictionary. It includes:
- Default values from the contract (e.g., tolerance = ±5%)
- Enumerated event lists (e.g., force majeure qualifying events)
- Business rules encoded in descriptions (e.g., "buyers cannot reject a higher grade of the same colour")
- Cross-references to GAFTA clause numbers for traceability

### Step 4 — Participant Role Mapping

Map the domain's participant roles to Cosolvent's three-category model:

| Cosolvent Category | Domain Role                                                                                                                | Schema Section                           |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Supply**         | Seller / Exporter                                                                                                          | `participant_roles.supply`               |
| **Demand**         | Buyer / Importer                                                                                                           | `participant_roles.demand`               |
| **Facilitator**    | Broker, shipping agent, insurance broker, superintendent, analyst, fumigator, trade finance, customs broker, legal counsel | `participant_roles.facilitator.subtypes` |

**Key insight (from GAFTA 27):** A single grain trade contract implies **9 distinct facilitator subtypes**. This directly informs Conflict C3 in the cosolvent-beta roadmap (participant type limit). The Knowledge Slot schema should enumerate these so the marketplace knows which facilitator roles exist in the domain.

### Step 5 — Metadata Tagging Schema

Define the vertical-specific metadata tags that will be applied to reference documents when they're loaded into the Knowledge Slot's `reference_library` table.

For grain trading, the tag vocabulary includes:

| Tag                   | Purpose                 | Example Values                        |
| --------------------- | ----------------------- | ------------------------------------- |
| `origin_region`       | Where goods come from   | Canada, United States                 |
| `destination_country` | Where goods are going   | Japan, Indonesia, UK                  |
| `product_category`    | What's being traded     | Wheat, Barley, Corn, Soybeans         |
| `document_type`       | What kind of reference  | contract, regulation, standard, guide |
| `trade_corridor`      | Origin–destination pair | Canada→Japan, US→EU                   |
| `issuing_body`        | Who published it        | GAFTA, CGC, USDA, FGIS                |

This vocabulary is used for metadata-filtered vector search — the retrieval pattern described in §16.2 of the cosolvent-beta roadmap.

### Step 6 — Quality Review and Iteration

Review the extracted schema against the source document for:

- [ ] Completeness — are all major clauses represented?
- [ ] Accuracy — do field types and allowed values match the contract?
- [ ] Consistency — are naming conventions uniform?
- [ ] Traceability — can each schema section be traced to a contract clause?
- [ ] Facilitator coverage — are all service provider roles captured?

### Step 7 — Additional Document Processing (Repeat Steps 1–6)

Process additional contracts and reference documents, progressively building out the domain schema:

- Additional GAFTA contracts covering different trade configurations
- Referenced GAFTA standards (Nos. 72, 123, 124, 125, 130, 132)
- Government grading standards (Canadian Grain Commission, USDA/FGIS)
- Destination country import regulations
- Shipping and logistics reference material

Each new document may:
- Add new entities or fields to the schema
- Refine existing field definitions (more allowed values, tighter constraints)
- Introduce new facilitator subtypes
- Add new metadata tag values

---

## 3. Insights and Design Decisions

### 3.1 — Schema Format Choice

**Decision:** YAML over JSON Schema, Pydantic, or SQL DDL.

**Rationale:** The Knowledge Slot schema serves three audiences:
1. **Sponsors** who curate content — need human-readable format
2. **AI systems** that retrieve and reason — need machine-parseable format
3. **Developers** who implement the `reference_library` table — need clear field specifications

YAML serves all three. JSON Schema is too rigid for sponsor editing. Pydantic models are code-level artefacts. SQL DDL is an implementation detail.

### 3.2 — Starting with Contracts

**Decision:** Begin schema extraction from standard contracts rather than regulations or guides.

**Rationale:** A well-drafted standard contract (like GAFTA No. 27) is a comprehensive domain ontology in disguise. It defines:
- Every entity involved in a transaction
- The relationships between entities
- The rules governing the transaction
- The exceptions and edge cases
- The dispute resolution mechanics
- The external standards incorporated by reference

One contract yields more schema coverage than a dozen regulatory documents.

### 3.3 — Facilitator Enumeration

**Insight:** The GAFTA contract explicitly or implicitly references 9 facilitator subtypes. This is far more granular than the simple "facilitator" category in cosolvent-beta's current data model. The Knowledge Slot schema should capture this granularity so the AI can:
- Recommend the right type of facilitator for a deal
- Match facilitators based on role-specific capability dimensions
- Generate informed Handoff Artifacts that list the facilitator roles needed

### 3.4 — Excluded Conventions

**Insight:** What a contract **excludes** is as important as what it includes. GAFTA Contract No. 27 explicitly excludes Incoterms, CISG, and several other international conventions. The AI must know this to avoid citing excluded conventions as authoritative — a mistake that could undermine sponsor credibility.

### 3.5 — Circle Trading as Marketplace Intelligence

**Insight:** GAFTA's "circle trading" clause (§17 in the schema) describes a market phenomenon where chains of buy/sell transactions form a circle. Settlement is by invoice difference, not physical delivery. This is directly relevant to marketplace intelligence — the AI could detect potential circles and facilitate efficient settlement.

---

## 4. Tool Reference

### Document Conversion

| Tool                                         | Script               | Install                                     | Use Case                                               |
| -------------------------------------------- | -------------------- | ------------------------------------------- | ------------------------------------------------------ |
| `marker-pdf`                                 | `convert_pdf.py`     | `pip install marker-pdf` (Python 3.12 venv) | High-quality PDF conversion with layout detection      |
| `pymupdf4llm`                                | —                    | `pip install pymupdf4llm`                   | Fast, lightweight PDF conversion for simpler documents |
| `requests` + `BeautifulSoup` + `markdownify` | `convert_url.py`     | Pre-installed in `.venv`                    | Web page scraping and conversion to Markdown           |
| `csv` (stdlib) + `openpyxl`                  | `convert_tabular.py` | `pip install openpyxl`                      | CSV and Excel (.xlsx) spreadsheets to Markdown tables  |

### Schema Extraction

| Tool                    | Script                  | Configuration                    | Use Case                                      |
| ----------------------- | ----------------------- | -------------------------------- | --------------------------------------------- |
| `schema_analyzer.py`    | `schema_analyzer.py`    | `prompts/schema_analysis.md`     | LLM-assisted schema extraction via OpenRouter |
| `metadata_extractor.py` | `metadata_extractor.py` | `prompts/metadata_extraction.md` | LLM-assisted document metadata extraction     |
| OpenRouter API          | —                       | `OPENROUTER_API_KEY` env var     | LLM provider (Gemini, Claude, GPT, etc.)      |

### File Locations

| File                       | Path                               | Description                                               |
| -------------------------- | ---------------------------------- | --------------------------------------------------------- |
| Source documents           | `inputs/`                          | Raw source files (PDF, HTML, CSV, XLSX, Markdown)         |
| Markdown outputs           | `outputs/`                         | Converted Markdown files (from all supported input types) |
| Domain schemas             | `schemas/`                         | YAML schema files extracted from contracts                |
| Analysis results           | `analyses/`                        | LLM-generated schema proposals                            |
| Provenance records         | `provenance/`                      | Source URL and acquisition metadata (JSON per doc)        |
| Analysis prompt            | `prompts/schema_analysis.md`       | Editable LLM prompt template                              |
| Metadata prompt            | `prompts/metadata_extraction.md`   | Editable LLM prompt for document metadata                 |
| Schema analyzer            | `schema_analyzer.py`               | LLM-assisted schema extraction engine                     |
| Metadata extractor         | `metadata_extractor.py`            | LLM-assisted document metadata extraction                 |
| Provenance tracker         | `provenance.py`                    | Records source URL and metadata for every document        |
| PDF/HTML conversion script | `convert_pdf.py`                   | marker-pdf / pymupdf4llm / markdownify wrapper            |
| URL conversion script      | `convert_url.py`                   | Web page scraper and Markdown converter                   |
| Tabular conversion script  | `convert_tabular.py`               | CSV and Excel (.xlsx) to Markdown table converter         |
| FastAPI server             | `server.py`                        | GUI backend wrapping all tools                            |
| GUI interface              | `static/index.html`                | Single-page web application                               |
| Docker packaging           | `Dockerfile`, `docker-compose.yml` | Container packaging for deployment (local dev unchanged)  |
| This recipe                | `recipe.md`                        | Process documentation (this file)                         |

---

## 5. Relationship to Other Projects

| Project                       | Relationship                                                                                                                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **cosolvent-beta**            | The Knowledge Slot (§16.2) will be implemented here. This project curates the *content* that populates it.                                                                                                               |
| **CosolventAI**               | The original roadmap that first described the Slots Architecture (§21). Concepts from its Knowledge Slot design inform this work.                                                                                        |
| **DPWebsitePublishingSystem** | The whitepaper (`tm-reference_CL4_V4.md`) provides the theoretical foundation — §5.13 (Curating Authoritative Information), §6.6 (AI-Curated Authoritative Information), §4.13 (Authoritative Information Availability). |
| **GPSimAI**                   | A potential vertical consumer of Knowledge Slot content — grain and pulse trading.                                                                                                                                       |

---

## 6. Open Questions

1. **Schema versioning:** How should the domain schema evolve as new contracts are processed? Should it be additive-only, or can fields be refined?
2. **Cross-contract conflicts:** What happens when two GAFTA contracts define the same entity differently (e.g., different tolerance rules for different trade routes)?
3. **Metadata tag standardisation:** Should tag values come from a controlled vocabulary, or free-text with AI normalisation?
4. **Chunking strategy:** When loading reference documents into the `reference_library` table, what chunking strategy preserves clause-level coherence?
5. **Multi-vertical schemas:** Should the schema format support inheritance (a base grain trading schema extended by specific trade corridor schemas)?
