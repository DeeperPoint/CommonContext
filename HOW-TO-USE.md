# How to Use CommonContext

CommonContext is the **content/curation companion** to Cosolvent. It turns raw reference
documents (contracts, standards, trade guides) into the two things a Cosolvent
marketplace needs:

1. **A domain schema** — the *structure* (participant roles + profile fields) that
   becomes a `marketplace.yaml`.
2. **A knowledge library** — the *content* (embedded text chunks) that powers the
   runtime Q&A `reference_library`.

> Both are derived from the **same** documents — read once for structure, once for
> content. To stand up and run the resulting marketplace, see
> `../Cosolvent/HOW-TO-USE.md`.

---

## 1. Where things live

| Folder | What it holds |
|---|---|
| `inputs/` | **Source-of-truth documents** (the raw PDFs / HTML you curate). |
| `outputs/` | Generated artifacts: converted Markdown (`*.md`) + embedded chunks (`*_processed.jsonl`). Regenerated on every build. |
| `schemas/` | Domain schemas (`*_schema.yaml`) — the input to Cosolvent's `configgen`. |
| `provenance/` | JSON recording where each document came from (source URL, title, fetch date). |
| `analyses/` | LLM schema-analysis proposals (for the human-review workflow). |
| `prompts/` | The LLM prompts (schema synthesis/analysis, chunk tagging, etc.). |

**You curate `inputs/`. Everything else is generated from it.**

---

## 2. Prerequisites

```bash
cd CommonContext
python3 -m venv .venv
./.venv/bin/pip install pymupdf4llm markdownify beautifulsoup4 openpyxl openai tenacity pyyaml httpx python-dotenv
```

API keys (env var, `CommonContext/.env`, or `../Cosolvent/.env` — all are searched):
```
OPENROUTER_API_KEY=sk-or-...     # required: powers everything — schema synthesis, chunk
                                 # tagging (Claude), AND embeddings (openai/text-embedding-3-small)
OPENAI_API_KEY=sk-...            # optional fallback for embeddings if you have no OpenRouter key
```
> A **single OpenRouter key** does everything, including embeddings — OpenRouter proxies
> `openai/text-embedding-3-small` (1536-dim, matching Cosolvent's reference_library). A
> direct OpenAI key is only used as a fallback. If neither key exists, schema generation
> still works and the embed step is skipped automatically.

---

## 3. The one-command build (recommended)

`build_from_inputs.py` does the whole CommonContext half from everything in `inputs/`:

```bash
cd CommonContext
.venv/bin/python build_from_inputs.py
```

Steps it runs:
1. **Clean** stale `outputs/` (so they reflect only the current inputs).
2. **Convert** every `inputs/*` file → `outputs/<name>.md`.
3. **Synthesize** one domain schema → `schemas/generated_schema.yaml`.
4. **Embed** the docs → `generated_refs.jsonl` *(only if an embedding key is present)*.

Useful flags:
| Flag | Effect |
|---|---|
| `--out-schema PATH` | Where to write the schema (default `schemas/generated_schema.yaml`) |
| `--refs-out PATH` | Where to write the knowledge export (default `generated_refs.jsonl`) |
| `--model NAME` | OpenRouter model (default `anthropic/claude-opus-4.8`) |
| `--vertical SLUG` | Force the vertical slug (default: derived from the docs) |
| `--skip-knowledge` | Schema only; skip embeddings |
| `--keep-outputs` | Don't wipe `outputs/` first |

> **Tip:** the marketplace is built from whatever is in `inputs/`. For a *machinery*
> marketplace, keep only machinery documents in `inputs/`; move others aside.

Then hand the schema to Cosolvent — or just run the cross-repo command from the Cosolvent
side, which calls this script for you:
```bash
cd ../Cosolvent && make build-from-docs
```

---

## 4. Manual / step-by-step tools

If you'd rather run each stage yourself:

```bash
cd CommonContext

# Convert documents → Markdown (batch over inputs/, or a single file)
.venv/bin/python convert_pdf.py                       # batch-convert all pending inputs/
.venv/bin/python convert_pdf.py inputs/file.pdf       # single file
.venv/bin/python convert_url.py https://example.com/page
.venv/bin/python convert_tabular.py inputs/data.csv

# Analyze a doc for schema additions (proposal for human review → analyses/)
.venv/bin/python schema_analyzer.py outputs/document.md --schema schemas/<vertical>_schema.yaml

# Embed a doc into chunks (knowledge library)  [needs OPENAI_API_KEY]
.venv/bin/python chunk_and_embed.py outputs/document.md schemas/<vertical>_schema.yaml <vertical>

# Export embedded chunks to Cosolvent's ingestion format
.venv/bin/python export_references.py outputs/*_processed.jsonl --vertical <vertical> -o refs.jsonl
```

> `schema_analyzer.py` produces *proposals* (`proposed_additions` / `proposed_refinements`)
> for a human to merge into a `schemas/*.yaml`. `build_from_inputs.py` instead synthesizes
> a **complete, ready-to-use** schema in one shot (prompt: `prompts/schema_synthesis.md`).

---

## 5. Loading the knowledge library into Cosolvent

The knowledge export (`generated_refs.jsonl`) is loaded into Cosolvent's running database:

```bash
# from the repo root (cosolvent_beta/); the ../../ below is relative to Cosolvent/backend
cd Cosolvent/backend
POSTGRES_DSN='postgresql+asyncpg://postgres:postgres@localhost:15432/cosolvent' \
    .venv/bin/python -m cli load-references \
    ../../CommonContext/generated_refs.jsonl --vertical <vertical>
```
This requires the Cosolvent stack to be running (`make up`). After loading, the
marketplace's Q&A / Knowledge Query endpoint can answer from these documents.

> **Connection gotcha:** the CLI runs from `Cosolvent/backend/` and does **not**
> auto-load `Cosolvent/.env`, so it falls back to port **5432**. The Docker stack
> publishes Postgres on **15432**, so if you have any local Postgres on 5432 the CLI
> will silently hit the wrong server (symptom: `InvalidCatalogNameError: database
> "cosolvent" does not exist`). Pass `POSTGRES_DSN=...localhost:15432/cosolvent`
> explicitly (as above), or `export` it / source the repo-root `.env` first.

---

## 6. The big picture

```
inputs/*.pdf  (you curate — the source of truth)
   │  convert
   ▼
outputs/*.md
   ├─ synthesize ─► schemas/<vertical>_schema.yaml ─► (Cosolvent configgen) ─► marketplace.yaml ─► APIs
   └─ embed ──────► generated_refs.jsonl ───────────► (Cosolvent load-references) ─► reference_library ─► Q&A
```

- Curate documents in `inputs/`.
- `build_from_inputs.py` (or `make build-from-docs` from Cosolvent) generates the schema
  and knowledge library.
- Cosolvent turns the schema into a running marketplace and ingests the knowledge library.

For standing up and running the marketplace itself, see **`../Cosolvent/HOW-TO-USE.md`**.
