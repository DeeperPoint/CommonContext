# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Knowledge Slot Curation Server

FastAPI backend that wraps the existing conversion tools (convert_pdf.py,
convert_url.py) and exposes them via a web GUI. Designed to be vertical-
agnostic — the same interface works for any market vertical's Knowledge
Slot content curation.

Usage:
    .venv/Scripts/python.exe server.py
    # Opens at http://localhost:8400
"""

from __future__ import annotations

import logging
import os
import mimetypes
import shutil
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests as http_requests
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from provenance import (
    recordProvenance, getProvenance, listProvenance, injectFrontmatter,
)
from chunk_and_embed import process_document

# ── Configuration ──────────────────────────────────────────────────────────

INPUT_DIR = Path("inputs")
OUTPUT_DIR = Path("outputs")
SCHEMA_DIR = Path("schemas")
STATIC_DIR = Path("static")
ANALYSIS_DIR = Path("analyses")

INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
SCHEMA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
ANALYSIS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("curation.server")
logging.basicConfig(level=logging.INFO)


# ── Supported Source Types ─────────────────────────────────────────────────

class SourceType(str, Enum):
    """Source document types the curation tool can ingest."""
    PDF = "pdf"
    URL = "url"
    HTML = "html"
    CSV = "csv"
    XLSX = "xlsx"
    IMAGE = "image"       # Future: OCR / vision extraction
    DOCX = "docx"         # Future: Word document conversion
    MARKDOWN = "markdown"  # Direct markdown import (no conversion needed)


# Map file extensions to source types
EXTENSION_MAP: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".html": SourceType.HTML,
    ".htm": SourceType.HTML,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
    ".tif": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".bmp": SourceType.IMAGE,
    ".docx": SourceType.DOCX,
    ".csv": SourceType.CSV,
    ".xlsx": SourceType.XLSX,
    ".md": SourceType.MARKDOWN,
}

# Source types that are implemented now
IMPLEMENTED_TYPES = {
    SourceType.PDF, SourceType.HTML, SourceType.URL, SourceType.MARKDOWN,
    SourceType.CSV, SourceType.XLSX,
}


# ── Data Models ────────────────────────────────────────────────────────────

class DocumentRecord(BaseModel):
    """Metadata for an ingested document."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    sourceType: SourceType
    sourceUrl: str | None = None
    inputPath: str | None = None
    outputPath: str | None = None
    status: str = "pending"  # pending | converting | done | error
    errorMessage: str | None = None
    convertedAt: str | None = None
    fileSize: int | None = None
    outputSize: int | None = None


class ConvertUrlRequest(BaseModel):
    """Request to convert a URL to markdown."""
    url: str
    includeLinks: bool = True
    includeImages: bool = False


class ConvertFileRequest(BaseModel):
    """Options for file conversion."""
    fast: bool = True
    extractImages: bool = False


class AnalyseRequest(BaseModel):
    """Request to analyse a document for schema extraction."""
    documentPath: str
    schemaPath: str | None = None
    model: str | None = None


class MetadataExtractRequest(BaseModel):
    """Request to extract document-level citation metadata via LLM."""
    documentPath: str
    model: str | None = None


class ChunkAndEmbedRequest(BaseModel):
    """Request to process document into chunks, tag, and embed into JSONL."""
    documentPath: str
    schemaPath: str
    vertical: str = "grain"


# ── FastAPI App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Knowledge Slot Curation Tool",
    description="Ingest and convert reference documents for any Cosolvent marketplace vertical.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Routes ─────────────────────────────────────────────────────────────

@app.get("/api/status")
async def getStatus() -> dict[str, Any]:
    """Health check and system status."""
    inputFiles = list(INPUT_DIR.iterdir()) if INPUT_DIR.exists() else []
    outputFiles = list(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.exists() else []
    schemaFiles = list(SCHEMA_DIR.glob("*.yaml")) + list(SCHEMA_DIR.glob("*.yml"))

    return {
        "status": "ok",
        "inputCount": len([f for f in inputFiles if f.is_file()]),
        "outputCount": len([f for f in outputFiles if f.is_file()]),
        "schemaCount": len(schemaFiles),
        "supportedTypes": [t.value for t in SourceType],
        "implementedTypes": [t.value for t in IMPLEMENTED_TYPES],
    }


@app.get("/api/documents")
async def listDocuments() -> list[dict[str, Any]]:
    """List all documents — inputs, outputs, and pending conversions."""
    documents: list[dict[str, Any]] = []

    # Scan output directory for completed conversions
    if OUTPUT_DIR.exists():
        for outputFile in sorted(OUTPUT_DIR.iterdir()):
            if not outputFile.is_file() or outputFile.suffix != ".md":
                continue

            # Find matching input file
            inputFile = _findMatchingInput(outputFile.stem)
            sourceType = _inferSourceType(inputFile) if inputFile else SourceType.MARKDOWN

            # Look up provenance for source URL
            prov = getProvenance(outputFile.stem)

            documents.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, str(outputFile))),
                "filename": outputFile.stem,
                "sourceType": sourceType.value,
                "sourceUrl": prov.get("source_url") if prov else None,
                "inputPath": str(inputFile) if inputFile else None,
                "outputPath": str(outputFile),
                "status": "done",
                "fileSize": inputFile.stat().st_size if inputFile else None,
                "outputSize": outputFile.stat().st_size,
                "convertedAt": datetime.fromtimestamp(
                    outputFile.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })

    # Find pending input files (no matching output)
    if INPUT_DIR.exists():
        for inputFile in sorted(INPUT_DIR.iterdir()):
            if not inputFile.is_file():
                continue
            ext = inputFile.suffix.lower()
            if ext not in EXTENSION_MAP:
                continue

            outputFile = OUTPUT_DIR / f"{inputFile.stem}.md"
            if outputFile.exists():
                continue  # Already in the completed list

            sourceType = EXTENSION_MAP.get(ext, SourceType.PDF)
            isImplemented = sourceType in IMPLEMENTED_TYPES

            prov = getProvenance(inputFile.stem)

            documents.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, str(inputFile))),
                "filename": inputFile.stem,
                "sourceType": sourceType.value,
                "sourceUrl": prov.get("source_url") if prov else None,
                "inputPath": str(inputFile),
                "outputPath": None,
                "status": "pending" if isImplemented else "unsupported",
                "fileSize": inputFile.stat().st_size,
                "outputSize": None,
                "convertedAt": None,
            })

    return documents


@app.post("/api/upload")
async def uploadFile(
    file: UploadFile = File(...),
    sourceUrl: str | None = Query(None, description="Origin URL where this file was obtained"),
) -> dict[str, Any]:
    """Upload a file for conversion. Optionally record its source URL."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    sourceType = EXTENSION_MAP.get(ext)

    if sourceType is None:
        supportedExts = ", ".join(sorted(EXTENSION_MAP.keys()))
        raise HTTPException(
            400,
            f"Unsupported file type: {ext}. Supported: {supportedExts}",
        )

    # Save to inputs directory
    destPath = INPUT_DIR / file.filename
    if destPath.exists():
        # Add a suffix to avoid overwriting
        stem = destPath.stem
        destPath = INPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{ext}"

    with open(destPath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    isImplemented = sourceType in IMPLEMENTED_TYPES

    # Record provenance for the uploaded file
    recordProvenance(
        outputStem=destPath.stem,
        sourceUrl=sourceUrl,
        sourceType="file_upload",
        originalFilename=file.filename,
    )

    return {
        "filename": destPath.name,
        "sourceType": sourceType.value,
        "inputPath": str(destPath),
        "fileSize": destPath.stat().st_size,
        "status": "pending" if isImplemented else "unsupported",
        "message": (
            f"Uploaded {destPath.name}. Ready for conversion."
            if isImplemented
            else f"Uploaded {destPath.name}. {sourceType.value} conversion not yet implemented."
        ),
    }


@app.post("/api/convert/file")
async def convertFile(
    filename: str = Query(..., description="Name of the file in inputs/ to convert"),
    fast: bool = Query(True, description="Use fast PDF mode (pymupdf4llm)"),
    extractImages: bool = Query(False, description="Extract images (full PDF mode only)"),
) -> dict[str, Any]:
    """Convert a file from inputs/ to markdown in outputs/."""
    inputPath = INPUT_DIR / filename
    if not inputPath.exists():
        raise HTTPException(404, f"File not found: {filename}")

    ext = inputPath.suffix.lower()
    sourceType = EXTENSION_MAP.get(ext)

    if sourceType not in IMPLEMENTED_TYPES:
        raise HTTPException(
            501,
            f"Conversion for {sourceType.value if sourceType else ext} not yet implemented",
        )

    outputPath = OUTPUT_DIR / f"{inputPath.stem}.md"
    conversionMethod = None

    try:
        # Import the conversion functions from existing scripts
        if sourceType == SourceType.PDF:
            from convert_pdf import convertFile as doConvertFile
            doConvertFile(inputPath, outputPath, fast=fast, extractImages=extractImages)
            conversionMethod = "pymupdf4llm" if fast else "marker-pdf"

        elif sourceType in (SourceType.HTML,):
            from convert_pdf import convertHtmlToMarkdown
            convertHtmlToMarkdown(inputPath, outputPath)
            conversionMethod = "markdownify"

        elif sourceType == SourceType.CSV:
            from convert_tabular import convertCsvToMarkdown
            convertCsvToMarkdown(inputPath, outputPath)
            conversionMethod = "csv_stdlib"

        elif sourceType == SourceType.XLSX:
            from convert_tabular import convertXlsxToMarkdown
            convertXlsxToMarkdown(inputPath, outputPath)
            conversionMethod = "openpyxl"

        elif sourceType == SourceType.MARKDOWN:
            # Direct copy — no conversion needed
            shutil.copy2(inputPath, outputPath)
            conversionMethod = "direct_copy"

        # Record provenance and inject frontmatter
        existingProv = getProvenance(inputPath.stem)
        prov = recordProvenance(
            outputStem=inputPath.stem,
            sourceUrl=existingProv.get("source_url") if existingProv else None,
            sourceType=existingProv.get("source_type", "file_upload") if existingProv else "file_upload",
            originalFilename=inputPath.name,
            conversionMethod=conversionMethod,
            outputFilename=outputPath.name,
            fileSizeBytes=outputPath.stat().st_size,
        )
        injectFrontmatter(outputPath, prov)

        return {
            "status": "done",
            "inputPath": str(inputPath),
            "outputPath": str(outputPath),
            "outputSize": outputPath.stat().st_size,
            "convertedAt": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("Conversion failed for %s", filename)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "inputPath": str(inputPath),
                "errorMessage": str(e),
            },
        )


@app.post("/api/convert/url")
async def convertUrl(req: ConvertUrlRequest) -> dict[str, Any]:
    """Fetch a URL and convert its content to markdown.

    Smart content detection: if the URL serves a downloadable file (PDF, etc.),
    it is downloaded to inputs/ and converted via the file pipeline. If it
    serves HTML, it goes through the URL-to-markdown pipeline. In both cases,
    the source URL is recorded as provenance.
    """
    try:
        # Step 1: Probe the URL to determine content type
        contentType, responseHeaders = _probeUrlContentType(req.url)
        isPdf = (
            "application/pdf" in contentType
            or req.url.lower().rstrip("/").endswith(".pdf")
        )
        isDownloadable = isPdf  # Extend later for DOCX, etc.

        if isDownloadable:
            # Download the file to inputs/, then convert via file pipeline
            result = await _downloadAndConvertUrl(req.url, contentType, responseHeaders)
        else:
            # HTML page — use the URL-to-markdown pipeline
            from convert_url import convertUrlToMarkdown, generateOutputFilename
            convertUrlToMarkdown(
                req.url,
                outputPath=None,
                includeLinks=req.includeLinks,
                includeImages=req.includeImages,
            )
            outputPath = generateOutputFilename(req.url, str(OUTPUT_DIR))

            # Record provenance
            prov = recordProvenance(
                outputStem=outputPath.stem,
                sourceUrl=req.url,
                sourceType="url_html",
                originalFilename=outputPath.name,
                contentType=contentType,
                httpHeaders=_selectHeaders(responseHeaders),
                conversionMethod="markdownify",
                outputFilename=outputPath.name,
                fileSizeBytes=outputPath.stat().st_size if outputPath.exists() else None,
            )
            # Frontmatter is already injected by convert_url.py
            # but we ensure provenance fields are complete
            injectFrontmatter(outputPath, prov)

            result = {
                "status": "done",
                "sourceUrl": req.url,
                "outputPath": str(outputPath),
                "outputSize": outputPath.stat().st_size if outputPath.exists() else 0,
                "convertedAt": datetime.now(timezone.utc).isoformat(),
                "detectedType": "html",
            }

        return result

    except Exception as e:
        logger.exception("URL conversion failed for %s", req.url)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "sourceUrl": req.url,
                "errorMessage": str(e),
            },
        )


@app.get("/api/document/{filename}")
async def getDocument(filename: str) -> dict[str, Any]:
    """Get the markdown content of a converted document."""
    outputPath = OUTPUT_DIR / f"{filename}.md"
    if not outputPath.exists():
        # Try exact filename
        outputPath = OUTPUT_DIR / filename
        if not outputPath.exists():
            raise HTTPException(404, f"Document not found: {filename}")

    content = outputPath.read_text(encoding="utf-8", errors="replace")
    return {
        "filename": outputPath.stem,
        "content": content,
        "size": len(content),
        "lines": content.count("\n") + 1,
    }


@app.get("/api/schemas")
async def listSchemas() -> list[dict[str, Any]]:
    """List available domain schemas."""
    schemas: list[dict[str, Any]] = []
    for schemaFile in sorted(SCHEMA_DIR.glob("*.yaml")) + sorted(SCHEMA_DIR.glob("*.yml")):
        content = schemaFile.read_text(encoding="utf-8", errors="replace")
        schemas.append({
            "filename": schemaFile.name,
            "path": str(schemaFile),
            "size": schemaFile.stat().st_size,
            "lines": content.count("\n") + 1,
        })
    return schemas


@app.delete("/api/document/{filename}")
async def deleteDocument(filename: str) -> dict[str, str]:
    """Delete an output document."""
    outputPath = OUTPUT_DIR / f"{filename}.md"
    if not outputPath.exists():
        outputPath = OUTPUT_DIR / filename
    if outputPath.exists():
        outputPath.unlink()
        return {"status": "deleted", "filename": filename}
    raise HTTPException(404, f"Document not found: {filename}")


@app.post("/api/convert/batch")
async def convertBatch(
    fast: bool = Query(True, description="Use fast PDF mode"),
) -> dict[str, Any]:
    """Convert all pending files in inputs/ to markdown."""
    from convert_pdf import findPendingFiles, convertFile as doConvertFile

    pending = findPendingFiles(INPUT_DIR, OUTPUT_DIR)
    results: list[dict[str, Any]] = []

    for inputPath in pending:
        outputPath = OUTPUT_DIR / f"{inputPath.stem}.md"
        try:
            ext = inputPath.suffix.lower()
            conversionMethod = (
                "pymupdf4llm" if fast and ext == ".pdf" else
                "marker-pdf" if ext == ".pdf" else
                "markdownify" if ext in (".html", ".htm") else
                "direct_copy" if ext == ".md" else
                "unknown"
            )
            doConvertFile(inputPath, outputPath, fast=fast)

            # Record provenance
            existingProv = getProvenance(inputPath.stem)
            prov = recordProvenance(
                outputStem=inputPath.stem,
                sourceUrl=existingProv.get("source_url") if existingProv else None,
                sourceType=existingProv.get("source_type", "file_upload") if existingProv else "file_upload",
                originalFilename=inputPath.name,
                conversionMethod=conversionMethod,
                outputFilename=outputPath.name,
                fileSizeBytes=outputPath.stat().st_size,
            )
            injectFrontmatter(outputPath, prov)

            results.append({
                "filename": inputPath.name,
                "status": "done",
                "outputPath": str(outputPath),
            })
        except Exception as e:
            results.append({
                "filename": inputPath.name,
                "status": "error",
                "errorMessage": str(e),
            })

    return {
        "totalPending": len(pending),
        "converted": sum(1 for r in results if r["status"] == "done"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


# ── Schema Analysis Routes ─────────────────────────────────────────────────

@app.post("/api/analyse")
async def analyseDocumentEndpoint(req: AnalyseRequest) -> dict[str, Any]:
    """Analyse a converted document for domain schema extraction via LLM."""
    try:
        from schema_analyzer import analyseDocument
        result = await analyseDocument(
            documentPath=req.documentPath,
            schemaPath=req.schemaPath,
            model=req.model,
        )
        return result

    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        # API key missing or LLM error
        return JSONResponse(
            status_code=503,
            content={"status": "error", "errorMessage": str(e)},
        )
    except Exception as e:
        logger.exception("Analysis failed for %s", req.documentPath)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "errorMessage": str(e)},
        )


@app.get("/api/analyses")
async def listAnalyses() -> list[dict[str, Any]]:
    """List saved analysis results."""
    analyses: list[dict[str, Any]] = []
    if ANALYSIS_DIR.exists():
        for f in sorted(ANALYSIS_DIR.glob("*.yaml")) + sorted(ANALYSIS_DIR.glob("*.yml")):
            analyses.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "createdAt": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    return analyses


# ── Metadata Extraction Routes ────────────────────────────────────────────

@app.post("/api/extract-metadata")
async def extractMetadataEndpoint(req: MetadataExtractRequest) -> dict[str, Any]:
    """Extract document-level citation metadata from a converted document.

    Uses an LLM to impute organization, author, date, document type, and
    identifiers from the document content. Results are merged into the
    provenance record.
    """
    try:
        from metadata_extractor import extractMetadata
        result = await extractMetadata(
            documentPath=req.documentPath,
            model=req.model,
        )
        return result

    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "errorMessage": str(e)},
        )
    except Exception as e:
        logger.exception("Metadata extraction failed for %s", req.documentPath)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "errorMessage": str(e)},
        )

@app.post("/api/chunk-and-embed")
async def chunkAndEmbedEndpoint(req: ChunkAndEmbedRequest) -> dict[str, Any]:
    """Process a markdown document into tagged, embedded chunks.

    Exports a JSONL file with semantic context ready for vector db insertion.
    """
    try:
        from chunk_and_embed import process_document
        outfile_path = await process_document(
            markdown_path=req.documentPath,
            schema_path=req.schemaPath,
            vertical=req.vertical,
        )
        return {"status": "success", "processedFile": outfile_path}

    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "errorMessage": str(e)},
        )
    except Exception as e:
        logger.exception("Chunk and Embed failed for %s", req.documentPath)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "errorMessage": str(e)},
        )

@app.get("/api/analysis/{filename}")
async def getAnalysis(filename: str) -> dict[str, Any]:
    """Read a specific analysis result."""
    analysisPath = ANALYSIS_DIR / filename
    if not analysisPath.exists():
        analysisPath = ANALYSIS_DIR / f"{filename}_analysis.yaml"
    if not analysisPath.exists():
        raise HTTPException(404, f"Analysis not found: {filename}")

    content = analysisPath.read_text(encoding="utf-8", errors="replace")
    return {
        "filename": analysisPath.name,
        "content": content,
        "size": len(content),
        "lines": content.count("\n") + 1,
    }


# ── Provenance API ─────────────────────────────────────────────────────────

@app.get("/api/provenance")
async def listProvenanceEndpoint() -> list[dict[str, Any]]:
    """List all provenance records."""
    return listProvenance()


@app.get("/api/provenance/{stem}")
async def getProvenanceEndpoint(stem: str) -> dict[str, Any]:
    """Get the provenance record for a specific document."""
    prov = getProvenance(stem)
    if prov is None:
        raise HTTPException(404, f"No provenance record for: {stem}")
    return prov


# ── Helpers ────────────────────────────────────────────────────────────────

def _probeUrlContentType(url: str) -> tuple[str, dict[str, str]]:
    """Send a HEAD request to determine the URL's content type.

    Falls back to GET with stream if HEAD is not supported.

    Returns:
        (content_type, headers_dict)
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = http_requests.head(url, headers=headers, timeout=15, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "text/html")
        return ct.split(";")[0].strip().lower(), dict(resp.headers)
    except Exception:
        # HEAD failed — try GET with stream to read just headers
        try:
            resp = http_requests.get(url, headers=headers, timeout=15, stream=True)
            ct = resp.headers.get("Content-Type", "text/html")
            resp.close()
            return ct.split(";")[0].strip().lower(), dict(resp.headers)
        except Exception:
            # If all probing fails, assume HTML
            return "text/html", {}


async def _downloadAndConvertUrl(
    url: str, contentType: str, responseHeaders: dict[str, str],
) -> dict[str, Any]:
    """Download a file from a URL, save to inputs/, convert, and record provenance."""
    from convert_pdf import convertFile as doConvertFile

    # Determine filename from URL path or Content-Disposition
    parsed = urlparse(url)
    urlFilename = Path(parsed.path).name if parsed.path else "download"

    # Check Content-Disposition header for a better filename
    contentDisp = responseHeaders.get("Content-Disposition", "")
    if "filename=" in contentDisp:
        import re as _re
        match = _re.search(r'filename="?([^"\s;]+)"?', contentDisp)
        if match:
            urlFilename = match.group(1)

    if not Path(urlFilename).suffix:
        # Infer extension from content type
        extMap = {"application/pdf": ".pdf", "application/msword": ".docx"}
        ext = extMap.get(contentType, ".pdf")
        urlFilename = f"{urlFilename}{ext}"

    # Download to inputs/
    inputPath = INPUT_DIR / urlFilename
    if inputPath.exists():
        stem = inputPath.stem
        inputPath = INPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{inputPath.suffix}"

    logger.info("Downloading %s → %s", url, inputPath)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    resp = http_requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    inputPath.write_bytes(resp.content)

    # Convert
    outputPath = OUTPUT_DIR / f"{inputPath.stem}.md"
    doConvertFile(inputPath, outputPath, fast=True)

    # Record provenance with the source URL
    prov = recordProvenance(
        outputStem=inputPath.stem,
        sourceUrl=url,
        sourceType="url_download",
        originalFilename=urlFilename,
        contentType=contentType,
        httpHeaders=_selectHeaders(responseHeaders),
        conversionMethod="pymupdf4llm",
        outputFilename=outputPath.name,
        fileSizeBytes=outputPath.stat().st_size,
    )
    injectFrontmatter(outputPath, prov)

    return {
        "status": "done",
        "sourceUrl": url,
        "inputPath": str(inputPath),
        "outputPath": str(outputPath),
        "outputSize": outputPath.stat().st_size,
        "convertedAt": datetime.now(timezone.utc).isoformat(),
        "detectedType": "download",
    }


def _selectHeaders(headers: dict[str, str]) -> dict[str, str]:
    """Extract interesting HTTP headers for provenance storage."""
    keepKeys = {
        "content-type", "content-length", "content-disposition",
        "last-modified", "etag", "server", "date",
    }
    return {k: v for k, v in headers.items() if k.lower() in keepKeys}


def _findMatchingInput(outputStem: str) -> Path | None:
    """Find an input file whose stem matches the given output file stem."""
    for ext in EXTENSION_MAP:
        candidate = INPUT_DIR / f"{outputStem}{ext}"
        if candidate.exists():
            return candidate
    return None


def _inferSourceType(inputPath: Path) -> SourceType:
    """Infer the source type from a file's extension."""
    ext = inputPath.suffix.lower()
    return EXTENSION_MAP.get(ext, SourceType.PDF)


# ── GUI Serving ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serveGui():
    """Serve the main GUI page."""
    guiPath = STATIC_DIR / "index.html"
    if guiPath.exists():
        return HTMLResponse(guiPath.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>Knowledge Slot Curation Tool</h1>"
        "<p>GUI not found. Place index.html in static/ directory.</p>"
        f"<p>API docs: <a href='/docs'>/docs</a></p>"
    )


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("\n  Knowledge Slot Curation Tool")
    print("  http://localhost:8400\n")

    uvicorn.run(
        "server:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8400")),
        reload=os.environ.get("HOST", "127.0.0.1") == "127.0.0.1",
        log_level="info",
    )
