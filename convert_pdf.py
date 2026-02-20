# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
PDF to Markdown Converter
Uses marker-pdf for high-quality conversion with layout detection.

Usage:
    .venv312\Scripts\python.exe convert_pdf.py input.pdf
    .venv312\Scripts\python.exe convert_pdf.py input.pdf -o output.md
    .venv312\Scripts\python.exe convert_pdf.py input.pdf -o output.md --extract-images
"""

import argparse
import sys
from pathlib import Path

from marker.converters.pdf import PdfConverter
from marker.config.parser import ConfigParser


def convertPdfToMarkdown(inputPath: str, outputPath: str = None, extractImages: bool = False) -> str:
    """Convert a PDF file to Markdown using marker-pdf.

    Args:
        inputPath: Path to the input PDF file.
        outputPath: Optional path for the output Markdown file. Defaults to same name as input with .md extension.
        extractImages: If True, extract images to a subdirectory alongside the output file.

    Returns:
        The generated Markdown text.
    """
    pdfPath = Path(inputPath)
    if not pdfPath.exists():
        print(f"Error: File not found: {pdfPath}")
        sys.exit(1)

    if outputPath is None:
        outputPath = pdfPath.with_suffix(".md")
    else:
        outputPath = Path(outputPath)

    print(f"Converting: {pdfPath}")
    print(f"Output:     {outputPath}")

    configDict = {"output_format": "markdown"}
    if extractImages:
        configDict["extract_images"] = True

    configParser = ConfigParser(configDict)
    converter = PdfConverter(config=configParser.generate_config_dict())
    rendered = converter(str(pdfPath))

    mdText = rendered.markdown

    # Write the markdown output
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(mdText, encoding="utf-8")
    print(f"Done! Written {len(mdText):,} characters to {outputPath}")

    # Save extracted images if any
    if extractImages and rendered.images:
        imageDir = outputPath.parent / f"{outputPath.stem}_images"
        imageDir.mkdir(parents=True, exist_ok=True)
        for imageName, imageData in rendered.images.items():
            imagePath = imageDir / imageName
            imageData.save(str(imagePath))
            print(f"  Saved image: {imagePath}")

    return mdText


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown using marker-pdf")
    parser.add_argument("input", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Path for the output Markdown file (default: same name with .md)")
    parser.add_argument("--extract-images", action="store_true", help="Extract images to a subdirectory")

    args = parser.parse_args()
    convertPdfToMarkdown(args.input, args.output, args.extract_images)
