# AI Knowledge Slot Curation

Tools and methods to collect and curate information for the Knowledge Slot in Cosolvent marketplace deployments.

## Overview

The Knowledge Slot is a sponsor-curated reference library that provides domain knowledge for AI-powered features in a Cosolvent marketplace, including:

- Answering participant questions
- Validating compliance with contracts and regulations
- Supporting matching decisions with contextual guidance
- Generating reports and summaries

This repository contains a **GUI application** and **CLI scripts** for building and maintaining the Knowledge Slot. The tool is **vertical-agnostic** — it works for any Cosolvent marketplace deployment.

## Repository Structure

```
AIKnowledgeSlotCuration/
├── .venv/                    # Python virtual environment (created locally)
├── inputs/                   # Raw source documents (PDFs, HTML, etc.)
├── outputs/                  # Converted Markdown files
├── schemas/                  # Domain-specific YAML schemas
├── analyses/                 # LLM-generated schema analysis results
├── provenance/               # Source URL and acquisition metadata (JSON)
├── prompts/                  # Editable LLM prompt templates
│   └── schema_analysis.md    # Prompt for schema extraction (edit to tune)
├── static/                   # GUI web interface
│   └── index.html            # Single-page application
├── docs/                     # Integration notes and analysis
├── server.py                 # FastAPI backend (wraps CLI scripts)
├── schema_analyzer.py        # LLM-assisted schema extraction (OpenRouter)
├── metadata_extractor.py     # LLM-assisted document metadata extraction
├── provenance.py             # Source URL and provenance tracking
├── convert_pdf.py            # PDF/HTML → Markdown conversion
├── convert_url.py            # Web page → Markdown conversion
├── launch-gui.bat            # One-click GUI launcher (Windows)
├── requirements.txt          # Python dependencies
├── recipe.md                 # Process documentation and guidelines
├── ROADMAP.md                # Development roadmap
└── README.md                 # This file
```

## Getting Started

### Prerequisites

- Python 3.12 (required by `marker-pdf`)
- pip (Python package installer)

### Setup

1. **Create virtual environment:**
   ```bash
   python -m venv .venv
   ```

2. **Activate virtual environment:**
   ```bash
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### GUI (Recommended)

**Double-click `launch-gui.bat`** or run:
```bash
.venv\Scripts\python.exe server.py
```

The GUI opens at **http://localhost:8400** and provides:

- **File Upload** — Drag-and-drop PDFs, HTML files, and Markdown files
- **URL Fetch** — Enter a URL to fetch and convert a web page
- **Batch Conversion** — Convert all pending files in one click
- **Schema Analysis** — LLM-assisted domain schema extraction from converted documents (via OpenRouter)
- **Metadata Extraction** — LLM imputes organization, author, date, document type for locally-uploaded files
- **Provenance Tracking** — Every document records its source URL and acquisition metadata for citation
- **Document Viewer** — Preview converted Markdown content with provenance info bar
- **Schema Browser** — View domain-specific YAML schemas
- **Analysis Browser** — View and compare LLM-generated schema proposals

#### Supported Source Types

| Type        | Status    | Method                                   |
| ----------- | --------- | ---------------------------------------- |
| PDF         | ✅ Ready   | pymupdf4llm (fast) or marker-pdf (OCR)   |
| HTML        | ✅ Ready   | BeautifulSoup + markdownify              |
| URL         | ✅ Ready   | Fetch + content extraction + markdownify |
| Markdown    | ✅ Ready   | Direct import (no conversion)            |
| Image (OCR) | 🟡 Planned | Pillow + OCR pipeline                    |
| DOCX        | 🟡 Planned | python-docx conversion                   |

### CLI Scripts

The original CLI scripts remain available for automation and scripting:

#### Convert PDF Documents

```bash
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf -o outputs/document.md
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf --extract-images
.venv\Scripts\python.exe convert_pdf.py --fast   # Batch mode, all pending files
```

#### Convert Web Pages

```bash
.venv\Scripts\python.exe convert_url.py https://example.com/page
.venv\Scripts\python.exe convert_url.py https://example.com/page -o outputs/page_name.md
```

**Options:**
- `--no-links` — Strip hyperlinks from the output
- `--include-images` — Preserve image references

## API Reference

When the server is running, interactive API docs are available at:

- **Swagger UI:** http://localhost:8400/docs
- **ReDoc:** http://localhost:8400/redoc

Key endpoints:

| Endpoint                 | Method | Description                              |
| ------------------------ | ------ | ---------------------------------------- |
| `/api/status`            | GET    | Health check and stats                   |
| `/api/documents`         | GET    | List all documents                       |
| `/api/upload`            | POST   | Upload a file for conversion             |
| `/api/convert/file`      | POST   | Convert a specific file                  |
| `/api/convert/url`       | POST   | Fetch and convert a URL                  |
| `/api/convert/batch`     | POST   | Convert all pending files                |
| `/api/document/{name}`   | GET    | Get converted document content           |
| `/api/schemas`           | GET    | List domain schemas                      |
| `/api/analyse`           | POST   | Analyse a document for schema extraction |
| `/api/analyses`          | GET    | List saved analysis results              |
| `/api/analysis/{name}`   | GET    | Get a specific analysis result           |
| `/api/provenance`        | GET    | List all provenance records              |
| `/api/provenance/{stem}` | GET    | Get provenance for a specific document   |
| `/api/extract-metadata`  | POST   | Extract document-level metadata via LLM  |

### Schema Analysis Configuration

The schema analysis feature uses OpenRouter to send converted documents to an LLM for structured domain analysis.

| Setting              | How to configure                                                                                            | Default                       |
| -------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **API key**          | `OPENROUTER_API_KEY` env var, or in any `.env` file (auto-discovered from `DPWebsitePublishingSystem/.env`) | — (required)                  |
| **LLM model**        | `OPENROUTER_MODEL` env var                                                                                  | `google/gemini-2.0-flash-001` |
| **Prompt template**  | Edit `prompts/schema_analysis.md`                                                                           | Provided                      |
| **Output directory** | `analyses/`                                                                                                 | —                             |

The analysis prompt is loaded from `prompts/schema_analysis.md` at runtime. Edit this file to adjust the analysis behaviour, output format, or domain-specific instructions — no code changes required.

## Process Documentation

For detailed information on the curation process, tools, and best practices, see:

- [Knowledge Slot Curation Recipe](recipe.md)
- [ROADMAP](ROADMAP.md)

## License

Copyright © 2026 Mustafa Uzumeri. All rights reserved.
