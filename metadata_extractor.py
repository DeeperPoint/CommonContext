# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Document Metadata Extractor

Uses an LLM (via OpenRouter) to extract document-level citation metadata
from converted Markdown content. This is designed for the common case where
a document arrives as a local file (e.g. received by email) with no
automatic URL provenance.

The LLM reads the converted content and imputes:
  - Organization/issuing body
  - Author(s)
  - Title, subtitle, identifier
  - Date of publication
  - Document type (contract, standard, regulation, etc.)
  - Geographic scope / jurisdiction
  - Referenced standards

The extracted metadata is merged into the document's provenance record
in provenance/, so it is available when chunks are later embedded and
retrieved for citation.

Usage (CLI):
    .venv/Scripts/python.exe metadata_extractor.py outputs/27_2025.md

Usage (from server):
    from metadata_extractor import extractMetadata
    result = await extractMetadata("outputs/27_2025.md")
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("curation.metadata_extractor")

# ── Configuration ──────────────────────────────────────────────────────────

PROMPT_DIR = Path("prompts")
PROMPT_FILE = PROMPT_DIR / "metadata_extraction.md"

# Reuse OpenRouter infrastructure from schema_analyzer
from schema_analyzer import (  # noqa: E402
    _discoverApiKey,
    _callOpenRouter,
    _extractYaml,
    DEFAULT_MODEL,
)

from provenance import recordProvenance, getProvenance, injectFrontmatter


# ── Prompt Loading ─────────────────────────────────────────────────────────

def _loadPromptTemplate() -> str:
    """Load the metadata extraction prompt from the template file."""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"Metadata extraction prompt not found at: {PROMPT_FILE}\n"
            "This file should have been created during setup."
        )
    return PROMPT_FILE.read_text(encoding="utf-8")


def _extractSection(template: str, header: str) -> str:
    """Extract a section from the prompt template by its ## header."""
    pattern = rf"## {header}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, template, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _buildPrompt(
    documentContent: str,
    documentFilename: str,
    existingProvenance: str,
) -> tuple[str, str]:
    """Build the system and user prompts with variable substitution.

    Returns:
        (systemPrompt, userPrompt) tuple.
    """
    template = _loadPromptTemplate()

    def _sub(text: str) -> str:
        text = text.replace("{{DOCUMENT_CONTENT}}", documentContent)
        text = text.replace("{{DOCUMENT_FILENAME}}", documentFilename)
        text = text.replace(
            "{{EXISTING_PROVENANCE}}",
            existingProvenance or "_No existing provenance record._",
        )
        return text

    systemPrompt = _sub(_extractSection(template, "SYSTEM"))
    userPrompt = _sub(_extractSection(template, "USER"))

    return systemPrompt, userPrompt


# ── Metadata Parsing ──────────────────────────────────────────────────────

def _parseMetadataYaml(yamlText: str) -> dict[str, Any]:
    """Parse the YAML metadata into a structured dict.

    Falls back to returning the raw text if YAML parsing fails.
    """
    try:
        import yaml
        parsed = yaml.safe_load(yamlText)
        if isinstance(parsed, dict):
            return parsed
        return {"raw_metadata": yamlText}
    except Exception:
        return {"raw_metadata": yamlText}


# ── Main Extraction Function ──────────────────────────────────────────────

async def extractMetadata(
    documentPath: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Extract document-level citation metadata from a converted document.

    Args:
        documentPath: Path to the converted Markdown file.
        model: Optional OpenRouter model override.

    Returns:
        Dict with keys: metadata (parsed YAML dict), rawYaml, rawResponse,
        documentFilename, model, provenanceUpdated.
    """
    docPath = Path(documentPath)
    if not docPath.exists():
        raise FileNotFoundError(f"Document not found: {documentPath}")

    documentContent = docPath.read_text(encoding="utf-8", errors="replace")
    documentFilename = docPath.name
    outputStem = docPath.stem

    # Load existing provenance if available
    existingProv = getProvenance(outputStem)
    existingProvStr = ""
    if existingProv:
        existingProvStr = json.dumps(existingProv, indent=2, ensure_ascii=False)

    # Build prompts
    systemPrompt, userPrompt = _buildPrompt(
        documentContent, documentFilename, existingProvStr,
    )

    # Call LLM
    rawResponse = await _callOpenRouter(systemPrompt, userPrompt, model)

    # Extract and parse YAML
    rawYaml = _extractYaml(rawResponse)
    metadata = _parseMetadataYaml(rawYaml)

    # Merge extracted metadata into provenance record
    _mergeIntoProvenance(outputStem, metadata)

    # Re-inject frontmatter with updated provenance
    updatedProv = getProvenance(outputStem)
    if updatedProv:
        injectFrontmatter(docPath, updatedProv)

    return {
        "metadata": metadata,
        "rawYaml": rawYaml,
        "rawResponse": rawResponse,
        "documentFilename": documentFilename,
        "model": model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
        "provenanceUpdated": True,
    }


def _mergeIntoProvenance(outputStem: str, metadata: dict[str, Any]) -> None:
    """Merge LLM-extracted metadata into the provenance record.

    Maps the structured metadata fields into the provenance format.
    """
    docMeta = metadata.get("document_metadata", {})
    orgMeta = metadata.get("issuing_organization", {})
    subjectMeta = metadata.get("subject_matter", {})

    # Build a summary title
    title = docMeta.get("title")
    identifier = docMeta.get("identifier")
    if title and identifier:
        docTitle = f"{title} ({identifier})"
    elif title:
        docTitle = title
    elif identifier:
        docTitle = identifier
    else:
        docTitle = None

    # Build a notes field with key metadata
    notesParts = []
    if docMeta.get("document_type"):
        notesParts.append(f"Type: {docMeta['document_type']}")
    if docMeta.get("version"):
        notesParts.append(f"Version: {docMeta['version']}")
    if docMeta.get("date_published"):
        notesParts.append(f"Published: {docMeta['date_published']}")
    if orgMeta.get("name"):
        notesParts.append(f"Issuer: {orgMeta['name']}")
    if subjectMeta.get("description"):
        notesParts.append(f"Summary: {subjectMeta['description']}")

    # Infer a plausible source URL from org website if available
    orgWebsite = orgMeta.get("website")

    # Update provenance — merge, don't overwrite existing URL
    existingProv = getProvenance(outputStem)
    existingUrl = existingProv.get("source_url") if existingProv else None

    recordProvenance(
        outputStem=outputStem,
        sourceUrl=existingUrl or orgWebsite,  # Only set URL if none exists
        documentTitle=docTitle,
        notes=" | ".join(notesParts) if notesParts else None,
    )

    # Store the full extracted metadata in the provenance JSON
    # by updating the file directly (recordProvenance doesn't have
    # an arbitrary field, so we append it)
    from provenance import PROVENANCE_DIR
    provPath = PROVENANCE_DIR / f"{outputStem}.json"
    if provPath.exists():
        record = json.loads(provPath.read_text(encoding="utf-8"))
        record["extracted_metadata"] = metadata
        provPath.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Extracted metadata merged into provenance: %s", provPath)


# ── CLI Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="Extract document metadata from a converted Markdown file.",
    )
    parser.add_argument("document", help="Path to the converted Markdown file")
    parser.add_argument("--model", help="OpenRouter model override")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = asyncio.run(extractMetadata(args.document, model=args.model))

    print(f"\n{'='*60}")
    print(f"  Document: {result['documentFilename']}")
    print(f"  Model:    {result['model']}")
    print(f"{'='*60}\n")
    print(result["rawYaml"])
    print(f"\n{'='*60}")
    print("  Provenance updated: ✓")
    print(f"{'='*60}")
