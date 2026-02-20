# AI Knowledge Slot Curation

Tools and methods to collect and curate information for the Knowledge Slot in Cosolvent marketplace deployments.

## Overview

The Knowledge Slot is a sponsor-curated reference library that provides domain knowledge for AI-powered features in a Cosolvent marketplace, including:

- Answering participant questions
- Validating compliance with contracts and regulations
- Supporting matching decisions with contextual guidance
- Generating reports and summaries

This repository contains scripts and documentation for building and maintaining the Knowledge Slot.

## Repository Structure

```
AIKnowledgeSlotCuration/
├── .venv/                    # Python virtual environment (created locally)
├── inputs/                   # Raw source documents (PDFs, etc.)
├── outputs/                  # Converted Markdown files and extracted schemas
├── convert_pdf.py            # PDF to Markdown conversion script
├── convert_url.py            # Web page to Markdown conversion script
├── recipe.md                 # Process documentation and guidelines
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
   python -m pip install marker-pdf beautifulsoup4 requests markdownify
   ```

## Usage

### Convert PDF Documents

Use `convert_pdf.py` to convert PDF files to Markdown. The script preserves document structure, tables, and lists.

**Basic usage:**
```bash
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf
```

**Specify output path:**
```bash
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf -o outputs/document.md
```

**Extract images:**
```bash
.venv\Scripts\python.exe convert_pdf.py inputs/document.pdf --extract-images
```

### Convert Web Pages

Use `convert_url.py` to convert web pages to Markdown. The script strips navigation, headers, footers, and other boilerplate, preserving only the main content.

**Basic usage:**
```bash
.venv\Scripts\python.exe convert_url.py https://example.com/page
```

**Specify output path:**
```bash
.venv\Scripts\python.exe convert_url.py https://example.com/page -o outputs/page_name.md
```

**Options:**
- `--no-links` — Strip hyperlinks from the output
- `--include-images` — Preserve image references

## Process Documentation

For detailed information on the curation process, tools, and best practices, see:

- [Knowledge Slot Curation Recipe](recipe.md)

## License

Copyright © 2026 Mustafa Uzumeri. All rights reserved.
