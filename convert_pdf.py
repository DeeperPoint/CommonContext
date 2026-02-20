# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Batch Document-to-Markdown Converter

Converts all files in inputs/ that don't already have a corresponding .md
file in outputs/. Supports PDF and HTML input files.

Two PDF conversion modes:
  --fast    Uses pymupdf4llm for instant text extraction (no OCR, no ML).
            Best for digitally-authored PDFs with selectable text.
  (default) Uses marker-pdf for high-quality conversion with layout detection.
            Best for scanned documents or complex layouts requiring OCR.

Single-file mode:
  convert_pdf.py inputs/file.pdf --fast
  convert_pdf.py inputs/file.pdf -o outputs/custom_name.md

Batch mode (converts all unconverted files in inputs/):
  convert_pdf.py --fast
  convert_pdf.py
"""

import argparse
import sys
import time
from pathlib import Path

# Supported input file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm"}


def getOutputPath(inputPath: Path, outputDir: Path) -> Path:
    """Derive the output .md path for a given input file.

    Args:
        inputPath: Path to the input file.
        outputDir: Directory for output files.

    Returns:
        A Path object for the corresponding output .md file.
    """
    return outputDir / inputPath.with_suffix(".md").name


def findPendingFiles(inputDir: Path, outputDir: Path) -> list[Path]:
    """Find input files that don't yet have a corresponding output in outputs/.

    Args:
        inputDir: Directory containing source files.
        outputDir: Directory containing converted files.

    Returns:
        List of input file Paths that need conversion.
    """
    pending = []
    for inputFile in sorted(inputDir.iterdir()):
        if inputFile.is_file() and inputFile.suffix.lower() in SUPPORTED_EXTENSIONS:
            outPath = getOutputPath(inputFile, outputDir)
            if not outPath.exists():
                pending.append(inputFile)
    return pending


def convertHtmlToMarkdown(inputPath: Path, outputPath: Path) -> str:
    """Convert a local HTML file to Markdown using BeautifulSoup + markdownify.

    Args:
        inputPath: Path to the HTML file.
        outputPath: Path for the output Markdown file.

    Returns:
        The generated Markdown text.
    """
    import re
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    print(f"  Mode:     html (BeautifulSoup + markdownify)")

    startTime = time.time()

    html = inputPath.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Extract page title
    titleTag = soup.find("title")
    pageTitle = titleTag.get_text(strip=True) if titleTag else inputPath.stem

    # Strip noise elements
    for tag in soup.find_all(["nav", "header", "footer", "aside", "script",
                              "style", "noscript", "iframe", "form"]):
        tag.decompose()

    # Find main content
    content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(role="main")
        or soup.body
        or soup
    )

    mdText = md(
        str(content),
        heading_style="ATX",
        bullets="-",
        newline_style="backslash",
    )

    # Clean up whitespace
    mdText = re.sub(r"\n{3,}", "\n\n", mdText)
    mdText = re.sub(r"[ \t]+$", "", mdText, flags=re.MULTILINE)
    mdText = mdText.strip()

    # Add frontmatter
    header = (
        f"---\n"
        f"source_file: {inputPath.name}\n"
        f"title: \"{pageTitle}\"\n"
        f"---\n\n"
        f"# {pageTitle}\n\n"
    )
    mdText = header + mdText

    elapsed = time.time() - startTime

    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(mdText, encoding="utf-8")
    print(f"  Done:     {len(mdText):,} chars -> {outputPath} ({elapsed:.1f}s)")

    return mdText


def convertPdfFast(inputPath: Path, outputPath: Path) -> str:
    """Convert a PDF to Markdown using pymupdf4llm (fast, no ML).

    Args:
        inputPath: Path to the input PDF file.
        outputPath: Path for the output Markdown file.

    Returns:
        The generated Markdown text.
    """
    import pymupdf4llm

    print(f"  Mode:     fast (pymupdf4llm — no OCR)")

    startTime = time.time()
    mdText = pymupdf4llm.to_markdown(str(inputPath))
    elapsed = time.time() - startTime

    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(mdText, encoding="utf-8")
    print(f"  Done:     {len(mdText):,} chars -> {outputPath} ({elapsed:.1f}s)")

    return mdText


def convertPdfFull(inputPath: Path, outputPath: Path, extractImages: bool = False) -> str:
    """Convert a PDF to Markdown using marker-pdf (ML-based, with OCR).

    Args:
        inputPath: Path to the input PDF file.
        outputPath: Path for the output Markdown file.
        extractImages: If True, extract images to a subdirectory.

    Returns:
        The generated Markdown text.
    """
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.config.parser import ConfigParser

    print(f"  Mode:     full (marker-pdf — ML + OCR)")

    startTime = time.time()

    print("  Loading models (this may take a while on first run)...")
    artifactDict = create_model_dict()

    configDict = {"output_format": "markdown"}
    configParser = ConfigParser(configDict)

    converter = PdfConverter(
        artifact_dict=artifactDict,
        config=configParser.generate_config_dict(),
    )

    print("  Converting PDF...")
    rendered = converter(str(inputPath))
    elapsed = time.time() - startTime

    mdText = rendered.markdown

    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(mdText, encoding="utf-8")
    print(f"  Done:     {len(mdText):,} chars -> {outputPath} ({elapsed:.1f}s)")

    # Save extracted images if any
    if extractImages and hasattr(rendered, 'images') and rendered.images:
        imageDir = outputPath.parent / f"{outputPath.stem}_images"
        imageDir.mkdir(parents=True, exist_ok=True)
        for imageName, imageData in rendered.images.items():
            imagePath = imageDir / imageName
            imageData.save(str(imagePath))
            print(f"  Saved image: {imagePath}")

    return mdText


def convertFile(inputPath: Path, outputPath: Path, fast: bool = True,
                extractImages: bool = False) -> str:
    """Convert a single file based on its extension.

    Args:
        inputPath: Path to the input file.
        outputPath: Path for the output Markdown file.
        fast: If True, use pymupdf4llm for PDFs instead of marker-pdf.
        extractImages: If True, extract images (full PDF mode only).

    Returns:
        The generated Markdown text.
    """
    ext = inputPath.suffix.lower()

    if ext in (".html", ".htm"):
        return convertHtmlToMarkdown(inputPath, outputPath)
    elif ext == ".pdf":
        if fast:
            return convertPdfFast(inputPath, outputPath)
        else:
            return convertPdfFull(inputPath, outputPath, extractImages)
    else:
        print(f"  Skipped:  unsupported file type {ext}")
        return ""


def runBatch(inputDir: Path, outputDir: Path, fast: bool = True,
             extractImages: bool = False) -> None:
    """Convert all pending files in inputDir.

    Args:
        inputDir: Directory containing source files.
        outputDir: Directory for converted output.
        fast: If True, use fast PDF mode.
        extractImages: If True, extract images (full PDF mode only).
    """
    pending = findPendingFiles(inputDir, outputDir)

    if not pending:
        print("Nothing to convert — all input files already have outputs.")
        return

    print(f"Found {len(pending)} file(s) to convert:\n")
    for f in pending:
        print(f"  {f.name}")
    print()

    totalStart = time.time()
    for i, inputFile in enumerate(pending, 1):
        outPath = getOutputPath(inputFile, outputDir)
        print(f"[{i}/{len(pending)}] {inputFile.name}")
        try:
            convertFile(inputFile, outPath, fast, extractImages)
        except Exception as e:
            print(f"  ERROR:    {e}")
        print()

    totalElapsed = time.time() - totalStart
    print(f"Batch complete: {len(pending)} file(s) in {totalElapsed:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown (batch or single file)",
        epilog="Run without arguments to batch-convert all pending files in inputs/.",
    )
    parser.add_argument(
        "input", nargs="?", default=None,
        help="Path to a single input file (omit for batch mode)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (single-file mode only)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Use pymupdf4llm for fast PDF extraction (default in batch mode)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Use marker-pdf for ML-based PDF conversion with OCR",
    )
    parser.add_argument(
        "--extract-images", action="store_true",
        help="Extract images to a subdirectory (full PDF mode only)",
    )

    args = parser.parse_args()

    # Determine fast vs full mode (default: fast)
    useFast = not args.full

    inputDir = Path("inputs")
    outputDir = Path("outputs")

    if args.input:
        # Single-file mode
        inputFile = Path(args.input)
        if not inputFile.exists():
            print(f"Error: File not found: {inputFile}")
            sys.exit(1)
        outPath = Path(args.output) if args.output else getOutputPath(inputFile, outputDir)
        print(f"[1/1] {inputFile.name}")
        convertFile(inputFile, outPath, useFast, args.extract_images)
    else:
        # Batch mode
        if not inputDir.exists():
            print(f"Error: Input directory not found: {inputDir}")
            sys.exit(1)
        runBatch(inputDir, outputDir, useFast, args.extract_images)
