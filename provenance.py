# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Provenance Tracking for Knowledge Slot Documents

Records the origin, acquisition method, and metadata for every document
that enters the curation pipeline. Each output document gets a JSON
sidecar file in provenance/ that captures:

  - source_url: where the document was obtained (if applicable)
  - source_type: how it was acquired (url_html, url_download, file_upload, direct_import)
  - original_filename: the filename as received or downloaded
  - content_type: HTTP Content-Type header (for URL-sourced documents)
  - fetched_at: ISO timestamp of acquisition
  - converted_at: ISO timestamp of conversion
  - document_title: extracted title (for HTML pages)
  - notes: free-text field for additional context

This provenance data is designed to survive all the way through to
embedding and retrieval: when Cosolvent chunks and embeds these documents,
each chunk can cite its authoritative source URL.

Usage:
    from provenance import recordProvenance, getProvenance, injectFrontmatter

    # Record provenance when a document is acquired
    recordProvenance(
        outputStem="27_2025",
        sourceUrl="https://members.gafta.com/contracts/27_2025.pdf",
        sourceType="url_download",
        originalFilename="27_2025.pdf",
        contentType="application/pdf",
    )

    # Read provenance for a document
    prov = getProvenance("27_2025")

    # Ensure markdown output has YAML frontmatter with provenance
    injectFrontmatter("outputs/27_2025.md", prov)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("curation.provenance")

# ── Configuration ──────────────────────────────────────────────────────────

PROVENANCE_DIR = Path("provenance")
PROVENANCE_DIR.mkdir(exist_ok=True)


# ── Data Model ─────────────────────────────────────────────────────────────

def _defaultRecord() -> dict[str, Any]:
    """Return a blank provenance record with all fields."""
    return {
        "source_url": None,
        "source_type": None,       # url_html | url_download | file_upload | direct_import
        "original_filename": None,
        "content_type": None,       # HTTP Content-Type (for URL sources)
        "http_headers": {},         # Selected HTTP response headers
        "document_title": None,     # Extracted page/document title
        "fetched_at": None,         # When the source was fetched/uploaded
        "converted_at": None,       # When the conversion completed
        "output_filename": None,    # The .md filename in outputs/
        "file_size_bytes": None,    # Size of the converted output
        "conversion_method": None,  # e.g. "marker-pdf", "pymupdf4llm", "markdownify", "direct_copy"
        "notes": None,              # Free-text field
    }


# ── Public API ─────────────────────────────────────────────────────────────

def recordProvenance(
    outputStem: str,
    sourceUrl: str | None = None,
    sourceType: str | None = None,
    originalFilename: str | None = None,
    contentType: str | None = None,
    httpHeaders: dict[str, str] | None = None,
    documentTitle: str | None = None,
    conversionMethod: str | None = None,
    outputFilename: str | None = None,
    fileSizeBytes: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record provenance metadata for a converted document.

    Args:
        outputStem: The stem name of the output file (e.g. "27_2025").
        sourceUrl: The origin URL where the document was obtained.
        sourceType: How it was acquired (url_html, url_download, file_upload, direct_import).
        originalFilename: The filename as received or downloaded.
        contentType: HTTP Content-Type header value.
        httpHeaders: Selected HTTP response headers to preserve.
        documentTitle: Extracted page or document title.
        conversionMethod: Tool used for conversion.
        outputFilename: The output .md filename.
        fileSizeBytes: Size of the output file.
        notes: Free-text notes.

    Returns:
        The complete provenance record dict.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Load existing record if it exists (allows incremental updates)
    existing = getProvenance(outputStem)
    if existing is None:
        record = _defaultRecord()
        record["fetched_at"] = now
    else:
        record = existing

    # Update fields (only overwrite with non-None values)
    updates = {
        "source_url": sourceUrl,
        "source_type": sourceType,
        "original_filename": originalFilename,
        "content_type": contentType,
        "http_headers": httpHeaders,
        "document_title": documentTitle,
        "conversion_method": conversionMethod,
        "output_filename": outputFilename or f"{outputStem}.md",
        "file_size_bytes": fileSizeBytes,
        "notes": notes,
        "converted_at": now,
    }

    for key, value in updates.items():
        if value is not None:
            record[key] = value

    # Save
    provenancePath = PROVENANCE_DIR / f"{outputStem}.json"
    provenancePath.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Provenance recorded: %s", provenancePath)

    return record


def getProvenance(outputStem: str) -> dict[str, Any] | None:
    """Retrieve the provenance record for a document.

    Args:
        outputStem: The stem name of the output file.

    Returns:
        The provenance dict, or None if not found.
    """
    provenancePath = PROVENANCE_DIR / f"{outputStem}.json"
    if not provenancePath.exists():
        return None

    return json.loads(provenancePath.read_text(encoding="utf-8"))


def listProvenance() -> list[dict[str, Any]]:
    """List all provenance records.

    Returns:
        List of provenance dicts with the stem name added.
    """
    records = []
    for f in sorted(PROVENANCE_DIR.glob("*.json")):
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            record["_stem"] = f.stem
            records.append(record)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read provenance file %s: %s", f, e)
    return records


def deleteProvenance(outputStem: str) -> bool:
    """Delete a provenance record.

    Args:
        outputStem: The stem name of the output file.

    Returns:
        True if deleted, False if not found.
    """
    provenancePath = PROVENANCE_DIR / f"{outputStem}.json"
    if provenancePath.exists():
        provenancePath.unlink()
        return True
    return False


# ── Frontmatter Injection ─────────────────────────────────────────────────

def injectFrontmatter(markdownPath: str | Path, provenance: dict[str, Any]) -> None:
    """Ensure a markdown file has YAML frontmatter with provenance metadata.

    If the file already has frontmatter (between --- delimiters), the
    provenance fields are merged into it. If not, frontmatter is prepended.

    This is critical for chunking: when the document is later split into
    chunks for embedding, each chunk inherits the frontmatter metadata,
    ensuring the source URL is available for citation.

    Args:
        markdownPath: Path to the markdown file.
        provenance: The provenance record dict.
    """
    mdPath = Path(markdownPath)
    if not mdPath.exists():
        return

    content = mdPath.read_text(encoding="utf-8")

    # Build the frontmatter fields we want to ensure are present
    fmFields = {}
    if provenance.get("source_url"):
        fmFields["source_url"] = provenance["source_url"]
    if provenance.get("document_title"):
        fmFields["title"] = provenance["document_title"]
    if provenance.get("source_type"):
        fmFields["source_type"] = provenance["source_type"]
    if provenance.get("fetched_at"):
        fmFields["fetched_at"] = provenance["fetched_at"]
    if provenance.get("original_filename"):
        fmFields["original_filename"] = provenance["original_filename"]
    if provenance.get("conversion_method"):
        fmFields["conversion_method"] = provenance["conversion_method"]

    if not fmFields:
        return  # Nothing to inject

    # Check if file already has frontmatter
    fmMatch = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)

    if fmMatch:
        # Parse existing frontmatter and merge
        existingFm = fmMatch.group(1)
        existingLines = existingFm.strip().split("\n")
        existingKeys = set()
        for line in existingLines:
            if ":" in line:
                key = line.split(":", 1)[0].strip()
                existingKeys.add(key)

        # Add missing fields
        newLines = list(existingLines)
        for key, value in fmFields.items():
            if key not in existingKeys:
                # Quote strings that contain special YAML characters
                if isinstance(value, str) and any(c in value for c in ":#{}[]"):
                    newLines.append(f'{key}: "{value}"')
                else:
                    newLines.append(f"{key}: {value}")

        newFm = "\n".join(newLines)
        content = f"---\n{newFm}\n---\n" + content[fmMatch.end():]

    else:
        # Prepend new frontmatter
        fmLines = []
        for key, value in fmFields.items():
            if isinstance(value, str) and any(c in value for c in ":#{}[]"):
                fmLines.append(f'{key}: "{value}"')
            else:
                fmLines.append(f"{key}: {value}")

        frontmatter = "---\n" + "\n".join(fmLines) + "\n---\n\n"
        content = frontmatter + content

    mdPath.write_text(content, encoding="utf-8")
    logger.info("Frontmatter injected: %s", mdPath)
