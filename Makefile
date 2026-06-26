SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Paths & venv ──────────────────────────────────────────────────────
PY  := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

# ── Overridable build settings ────────────────────────────────────────
OUT_SCHEMA  ?= schemas/generated_schema.yaml
REFS_OUT    ?= generated_refs.jsonl
MODEL       ?=
VERTICAL    ?=
ARGS        ?=

# ── Per-file (manual / step-by-step) tool args ────────────────────────
FILE   ?=                              # a single input or output file
URL    ?=                              # a web page to convert
SCHEMA ?=                              # schema for analyze/embed (defaults to OUT_SCHEMA)
IN     ?= outputs/*_processed.jsonl    # embedded chunks to export
FULL   ?=                             # set FULL=1 to use marker-pdf (ML/OCR)

# ── Cross-repo (loading the knowledge library into Cosolvent) ─────────
COSOLVENT_DIR ?= ../Cosolvent
# The Docker stack publishes Postgres on 15432; the host CLI otherwise defaults
# to 5432 and silently hits the wrong server. Pin the DSN here.
POSTGRES_DSN  ?= postgresql+asyncpg://postgres:postgres@localhost:15432/cosolvent

# GUI (Knowledge Slot Curation Tool)
GUI_HOST ?= 127.0.0.1
GUI_PORT ?= 8400

.PHONY: help venv install build build-schema build-and-load gui \
	test test-unit test-integration clean clean-all load-references \
	convert convert-url convert-csv analyze embed export

help: ## Show available commands
	@echo "CommonContext Make Targets"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' Makefile | awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────

venv: ## Create the Python virtual environment (.venv)
	python3 -m venv .venv

install: venv ## Install runtime + dev dependencies into .venv
	$(PIP) install -r requirements.txt
	@[ -f requirements-dev.txt ] && $(PIP) install -r requirements-dev.txt || true

# ── Build (the core workflow) ─────────────────────────────────────────

build: ## Convert inputs/ -> schema (+ knowledge library). Override MODEL=, VERTICAL=, ARGS=
	$(PY) build_from_inputs.py \
		--out-schema $(OUT_SCHEMA) \
		--refs-out $(REFS_OUT) \
		$(if $(MODEL),--model $(MODEL),) \
		$(if $(VERTICAL),--vertical $(VERTICAL),) \
		$(ARGS)

build-schema: ## Build the domain schema only (skip embeddings / knowledge library)
	$(MAKE) build ARGS="--skip-knowledge $(ARGS)"

build-and-load: build load-references ## Build, then load the knowledge library into a running Cosolvent

# ── Load knowledge library into Cosolvent (needs its stack: make up) ──

load-references: ## Load generated_refs.jsonl into Cosolvent's reference_library (DSN pinned to :15432)
	@if [ ! -f "$(REFS_OUT)" ]; then \
		echo "No $(REFS_OUT) — run 'make build' first (and ensure an embedding key is set)."; exit 1; \
	fi
	@vert="$(VERTICAL)"; \
	if [ -z "$$vert" ] && [ -f "$(OUT_SCHEMA)" ]; then \
		vert=$$(grep -E '^vertical:' "$(OUT_SCHEMA)" | head -1 | sed 's/^vertical:[[:space:]]*//'); \
	fi; \
	echo "Loading $(REFS_OUT) into Cosolvent (vertical=$${vert:-<from records>}) via $(POSTGRES_DSN)"; \
	cd $(COSOLVENT_DIR)/backend && POSTGRES_DSN='$(POSTGRES_DSN)' .venv/bin/python -m cli load-references \
		../../CommonContext/$(REFS_OUT) $${vert:+--vertical $$vert}

# ── GUI ───────────────────────────────────────────────────────────────

gui: ## Launch the Knowledge Slot Curation Tool GUI (http://$(GUI_HOST):$(GUI_PORT))
	@echo "Knowledge Slot Curation Tool -> http://$(GUI_HOST):$(GUI_PORT)"
	HOST=$(GUI_HOST) PORT=$(GUI_PORT) $(PY) server.py

# ── Tests ─────────────────────────────────────────────────────────────

test: test-unit ## Alias for the fast unit tests

test-unit: ## Run fast tests (excludes the Docker/pgvector integration tests)
	$(PYTEST) -m "not integration"

test-integration: ## Run integration tests (requires a live Postgres/pgvector container)
	$(PYTEST) -m integration

# ── Manual / step-by-step tools (HOW-TO-USE §4) ──────────────────────
# These mirror the per-file scripts. `make build` does all of this in one shot
# for the whole inputs/ folder; reach for these to process or debug one file.

convert: ## Convert docs -> Markdown: batch all of inputs/, or one FILE= (set FULL=1 for OCR)
	$(PY) convert_pdf.py $(FILE) $(if $(FULL),--full,)

convert-url: ## Convert a web page to Markdown (needs: URL=https://… ; requires the 'requests' package)
	@[ -n "$(URL)" ] || { echo "Set URL=… e.g. make convert-url URL=https://example.com/page"; exit 1; }
	$(PY) convert_url.py "$(URL)"

convert-csv: ## Convert a CSV/XLSX file to a Markdown table (needs: FILE=inputs/data.csv)
	@[ -n "$(FILE)" ] || { echo "Set FILE=… e.g. make convert-csv FILE=inputs/data.csv"; exit 1; }
	$(PY) convert_tabular.py "$(FILE)"

analyze: ## Analyze a converted doc for schema proposals (needs: FILE=outputs/doc.md ; opt SCHEMA=, MODEL=)
	@[ -n "$(FILE)" ] || { echo "Set FILE=outputs/<doc>.md"; exit 1; }
	$(PY) schema_analyzer.py "$(FILE)" $(if $(SCHEMA),--schema $(SCHEMA),) $(if $(MODEL),--model $(MODEL),)

embed: ## Embed one doc into chunks (needs: FILE=outputs/doc.md ; opt SCHEMA=, VERTICAL=)
	@[ -n "$(FILE)" ] || { echo "Set FILE=outputs/<doc>.md"; exit 1; }
	$(PY) chunk_and_embed.py "$(FILE)" "$(if $(SCHEMA),$(SCHEMA),$(OUT_SCHEMA))" $(VERTICAL)

export: ## Export embedded chunks to Cosolvent format (needs: VERTICAL= ; opt IN=, REFS_OUT=)
	@[ -n "$(VERTICAL)" ] || { echo "Set VERTICAL=… (slug stamped on every record)"; exit 1; }
	$(PY) export_references.py $(IN) --vertical $(VERTICAL) -o $(REFS_OUT)

# ── Housekeeping ──────────────────────────────────────────────────────

clean: ## Remove generated outputs/ (regenerated on next build)
	rm -rf outputs/*.md outputs/*_processed.jsonl

clean-all: clean ## Also remove the generated schema, refs export, and caches
	rm -f $(REFS_OUT) $(OUT_SCHEMA)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
