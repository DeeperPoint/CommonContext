# CommonContext — Domain Grounding for Cosolvent Marketplaces

CommonContext is the **content/curation companion** to the [Cosolvent](https://github.com/DeeperPoint/Cosolvent) marketplace engine. It turns raw reference documents (contracts, standards, trade guides, wiki pages) into the two things a Cosolvent marketplace needs:

1. **A domain schema** — the *structure* (participant roles + profile fields) that Cosolvent's `configgen` turns into a `marketplace.yaml`.
2. **A knowledge library** — the *content* (embedded, tagged text chunks) that populates Cosolvent's runtime `reference_library` and powers grounded, cited domain Q&A.

Both are derived from the **same** curated documents — read once for structure, once for content. The tool is **vertical-agnostic**: the active demo targets machinery/manufacturing trade, and the same pipeline has been validated against a grain-trade corpus (now archived in `inputs_archive_grain/`).

> **Naming note:** this project was formerly *KnowledgeSlot* / *AIKnowledgeSlotCuration*. It has been renamed **CommonContext**. Some code and GUI strings still read "Knowledge Slot Curation Tool" — that rename is tracked in [`docs/ROADMAP-renaming-knowledgeslot-to-commoncontext.md`](docs/ROADMAP-renaming-knowledgeslot-to-commoncontext.md).

## How it fits with Cosolvent

```
inputs/*.pdf   (you curate — the source of truth)
   │  convert
   ▼
outputs/*.md   (+ provenance sidecar + YAML frontmatter)
   ├─ synthesize ─► schemas/generated_schema.yaml ─► (Cosolvent configgen) ─► marketplace.yaml ─► APIs
   └─ chunk+embed ─► generated_refs.jsonl ─────────► (Cosolvent load-references) ─► reference_library ─► Q&A
```

The reference library is separate from participant-uploaded documents: it is **sponsor-curated and authoritative**, embedded with the same model/dimensions (1536-dim `text-embedding-3-small`) as Cosolvent's store so the two never diverge. See [`HOW-TO-USE.md`](HOW-TO-USE.md) for the end-to-end runbook and [`docs/`](docs/) for the design-decision records.

## What's in the repo

```
CommonContext/
├── inputs/                     Source documents you curate (active: machinery whitepaper)
├── inputs_archive_grain/       Retired grain/GAFTA corpus (kept as a second-vertical reference)
├── outputs/                    Generated: converted *.md + embedded *_processed.jsonl
├── schemas/                    Domain schemas (configgen input) + reference-metadata tag vocab
│   ├── machinery_trade_schema.yaml / generated_schema.yaml / manufacturing_domain_schema.yaml
│   ├── grain_trade_schema.yaml                 (legacy vertical)
│   └── reference_metadata_schema.py            Vertical-aware tag vocabulary (source of truth)
├── provenance/                 JSON sidecars: source URL, title, fetch date, imputed metadata
├── prompts/                    Editable LLM templates (schema synthesis/analysis, chunk tagging, Q&A, gap detection)
├── analyses/                   LLM schema-analysis proposals (human-review workflow)
├── static/index.html           Curation Tool single-page GUI
├── migrations/add_gap_signals.sql   knowledge_gap_signals table DDL
├── scripts/, tests/, docs/
│
├── build_from_inputs.py        ★ one-command build: convert → synthesize schema → embed
├── convert_pdf.py / convert_url.py / convert_tabular.py   Raw → Markdown
├── metadata_extractor.py       LLM imputes document-level citation metadata
├── schema_analyzer.py          LLM proposes domain-schema additions (per-doc)
├── chunk_and_embed.py          Heading chunk → LLM-tag topic → embed (1536-dim) → JSONL
├── export_references.py        Map processed chunks → Cosolvent ingestion contract
├── seed_reference_library.py   Direct pgvector upsert into Cosolvent's reference_library
├── provenance.py               Provenance sidecars + Markdown frontmatter injection
├── wiki_to_provenance.py       Provenance for mfgllmwiki pages (before embedding the wiki)
├── gap_signal.py               "Curatorial pull signal" — record a knowledge gap
├── server.py                   FastAPI backend for the Curation Tool GUI (port 8400)
├── Makefile                    build / build-and-load / gui / test / convert / embed / export
├── HOW-TO-USE.md               End-to-end runbook (start here)
└── ROADMAP.md                  Development roadmap
```

## Getting Started

Requires Python 3.10+ (marker-pdf needs `>=3.10, <4.0`).

```bash
cd CommonContext
make install          # creates .venv and installs runtime + dev deps
```

API keys (env var, `CommonContext/.env`, or `../Cosolvent/.env` — all searched):

```
OPENROUTER_API_KEY=sk-or-...   # required: schema synthesis, chunk tagging, AND embeddings
OPENAI_API_KEY=sk-...          # optional fallback for embeddings only
```

A single OpenRouter key does everything — it proxies `openai/text-embedding-3-small` (1536-dim, matching Cosolvent's `reference_library`). If no embedding key is present, schema generation still works and the embed step is skipped.

## The one-command build

```bash
make build            # build_from_inputs.py: clean → convert inputs/ → synthesize schema → embed
```

This produces `schemas/generated_schema.yaml` and (if an embedding key exists) `generated_refs.jsonl`. Useful overrides: `MODEL=`, `VERTICAL=`, `OUT_SCHEMA=`, `REFS_OUT=`, `ARGS=--skip-knowledge`.

> The marketplace is built from whatever is in `inputs/`. For a machinery marketplace, keep only machinery documents in `inputs/`; move others aside.

Then load the knowledge library into a running Cosolvent stack:

```bash
make build-and-load   # build, then load generated_refs.jsonl into Cosolvent's reference_library
```

`load-references` cd's into `../Cosolvent/backend` and runs its `cli load-references` (DSN pinned to `localhost:15432` to match the Docker stack). Or run the cross-repo entry point from the Cosolvent side: `cd ../Cosolvent && make build-from-docs`.

## Manual / step-by-step tools

```bash
make convert FILE=inputs/file.pdf          # or bare `make convert` to batch inputs/
make convert-url URL=https://example.com/page
make convert-csv FILE=inputs/data.csv
make analyze FILE=outputs/document.md      # schema proposals → analyses/
make embed   FILE=outputs/document.md      # chunk + embed → outputs/<stem>_processed.jsonl
make export  VERTICAL=machinery_trade      # processed chunks → Cosolvent contract JSONL
```

`schema_analyzer.py` produces *proposals* for a human to merge; `build_from_inputs.py` synthesizes a **complete, ready-to-use** schema in one shot (`prompts/schema_synthesis.md`).

## Curation Tool GUI

```bash
make gui               # launches server.py (FastAPI) at http://localhost:8400
```

The GUI provides drag-and-drop upload, URL fetch, batch conversion, LLM schema analysis and metadata extraction, chunk-and-embed, provenance tracking, and document/schema/analysis browsers. Interactive API docs: `http://localhost:8400/docs`.

To run it in Docker, use the `/launch-docker` workflow (a Claude Code slash command / skill that builds and starts the server via `docker-compose.yml` on port 8400).

| Source type | Status | Method |
|---|---|---|
| PDF | ✅ | pymupdf4llm (fast) or marker-pdf (OCR) |
| HTML | ✅ | BeautifulSoup + markdownify |
| URL | ✅ | fetch + content extraction + markdownify |
| CSV / XLSX | ✅ | rendered as Markdown tables (`convert_tabular.py`) |
| Markdown | ✅ | direct import |
| Image (OCR) / DOCX | 🟡 Planned | — |

## The Cosolvent ingestion contract

`export_references.py` maps embedded chunks to the JSONL record Cosolvent's `load-references` ingests:

```json
{ "source_doc_id": "…", "vertical": "machinery_trade",
  "chunk_text": "…", "embedding": [/* 1536 floats */],
  "metadata": { "document_type": "…", "organization": "…", "date_issued": "…", "topic": "…" } }
```

Two prebuilt libraries ship in the repo: `generated_refs.jsonl` (machinery whitepaper) and `wiki_refs.jsonl` (the mfgllmwiki manufacturing knowledge pages, via `wiki_to_provenance.py`).

## Testing

```bash
make test              # fast unit + e2e tests (LLM/embedding APIs mocked)
make test-integration  # opt-in: real Postgres + pgvector via docker-compose.test.yml
```

Covers chunking, metadata/tag schemas, provenance round-trip, the export adapter, gap signals, cross-vertical (grain + manufacturing) pipeline runs, on-disk artifact shape, a fully-mocked end-to-end run, and a real pgvector seed + retrieval integration test.

## AI providers

- **OpenRouter** — primary for all LLM text calls (chunk tagging, schema synthesis/analysis, metadata extraction). Defaults: `google/gemini-2.5-flash` (analysis), `anthropic/claude-opus-4.8` (synthesis).
- **Embeddings** — `openai/text-embedding-3-small` (1536-dim) via OpenRouter, with a direct OpenAI fallback.

## Related Projects

| Project | Role |
|---|---|
| [Cosolvent](https://github.com/DeeperPoint/Cosolvent) | The marketplace engine that consumes the schema and knowledge library |
| [MarketForge](https://github.com/DeeperPoint/MarketForge) | Market configuration and deployment orchestration |
| [ClientSynth](https://github.com/DeeperPoint/ClientSynth) | Synthetic participant generation for testing and demos |
| mfgllmwiki | Manufacturing knowledge wiki — a source corpus for the reference library |

## Process Documentation

- [`HOW-TO-USE.md`](HOW-TO-USE.md) — end-to-end runbook (start here)
- [`recipe.md`](recipe.md) — curation process and guidelines
- [`docs/`](docs/) — architecture and design-decision records (`DECISION-000`…`006`)
- [`ROADMAP.md`](ROADMAP.md) — development roadmap

## License

Copyright © 2026 Mustafa Uzumeri. All rights reserved.
