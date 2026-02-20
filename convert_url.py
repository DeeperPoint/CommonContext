# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
URL to Markdown Converter
Fetches a web page, extracts the main content, and converts it to clean Markdown.

Usage:
    .venv/Scripts/python.exe convert_url.py https://example.com/page
    .venv/Scripts/python.exe convert_url.py https://example.com/page -o outputs/page.md
    .venv/Scripts/python.exe convert_url.py https://example.com/page --include-links --include-images
"""

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


# Elements that typically contain navigation, ads, or boilerplate — not content
NOISE_TAGS = [
    "nav", "header", "footer", "aside", "script", "style", "noscript",
    "iframe", "svg", "form", "button",
]

NOISE_ROLES = ["navigation", "banner", "contentinfo", "complementary", "search"]

NOISE_CLASS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"nav", r"menu", r"sidebar", r"footer", r"header", r"banner",
        r"breadcrumb", r"cookie", r"popup", r"modal", r"social",
        r"share", r"comment", r"advert", r"widget", r"related",
        r"signup", r"newsletter", r"promo",
    ]
]


def fetchPage(url: str, timeout: int = 30) -> str:
    """Fetch raw HTML from a URL.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        The HTML content as a string.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def isNoiseElement(tag) -> bool:
    """Determine whether a BeautifulSoup tag is likely navigation/boilerplate noise."""
    if tag.name in NOISE_TAGS:
        return True

    role = tag.get("role", "")
    if role in NOISE_ROLES:
        return True

    classes = " ".join(tag.get("class", []))
    tagId = tag.get("id", "")
    combined = f"{classes} {tagId}"
    if any(p.search(combined) for p in NOISE_CLASS_PATTERNS):
        return True

    return False


def extractMainContent(soup: BeautifulSoup) -> BeautifulSoup:
    """Extract the main content area, stripping navigation and boilerplate.

    Args:
        soup: Parsed BeautifulSoup document.

    Returns:
        A BeautifulSoup object containing only the main content.
    """
    # Try to find an explicit main content container
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(role="main")
        or soup.find(id=re.compile(r"content|main|article", re.IGNORECASE))
        or soup.find(class_=re.compile(r"content|main|article", re.IGNORECASE))
    )

    target = main if main else soup.body if soup.body else soup

    # Collect noise elements first, then decompose (avoids mutation during iteration)
    noiseElements = [tag for tag in target.find_all(True) if isNoiseElement(tag)]
    for tag in noiseElements:
        if tag.parent is not None:  # guard against already-decomposed children
            tag.decompose()

    return target


def convertToMarkdown(
    html: str,
    url: str,
    includeLinks: bool = True,
    includeImages: bool = False,
) -> str:
    """Convert HTML to clean Markdown.

    Args:
        html: Raw HTML string.
        url: Source URL (used for metadata header).
        includeLinks: If True, preserve hyperlinks in Markdown output.
        includeImages: If True, preserve image references in Markdown output.

    Returns:
        Clean Markdown string with a metadata header.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract page title before stripping
    titleTag = soup.find("title")
    pageTitle = titleTag.get_text(strip=True) if titleTag else urlparse(url).netloc

    # Extract main content
    content = extractMainContent(soup)

    # Convert to markdown
    markdownText = md(
        str(content),
        heading_style="ATX",
        bullets="-",
        strip=None if includeLinks else ["a"],
        convert=["img"] if includeImages else [],
        newline_style="backslash",
    )

    # Normalize whitespace: collapse runs of newlines, trim trailing spaces
    markdownText = re.sub(r"\n{3,}", "\n\n", markdownText)
    markdownText = re.sub(r"[ \t]+$", "", markdownText, flags=re.MULTILINE)
    # Ensure headings have blank lines before them
    markdownText = re.sub(r"([^\n])\n(#{1,6} )", r"\1\n\n\2", markdownText)
    markdownText = markdownText.strip()

    # Prepend metadata header
    header = (
        f"---\n"
        f"source_url: {url}\n"
        f"title: \"{pageTitle}\"\n"
        f"---\n\n"
        f"# {pageTitle}\n\n"
    )

    return header + markdownText


def generateOutputFilename(url: str, outputDir: str = "outputs") -> Path:
    """Generate a reasonable output filename from a URL.

    Args:
        url: The source URL.
        outputDir: Directory to place the output file in.

    Returns:
        A Path object for the output file.
    """
    parsed = urlparse(url)

    # Build filename from the URL path
    pathPart = parsed.path.strip("/")
    if pathPart:
        # Use the last meaningful segment of the path
        segments = [s for s in pathPart.split("/") if s]
        name = segments[-1] if segments else parsed.netloc
    else:
        name = parsed.netloc

    # Remove file extensions and clean up
    name = re.sub(r"\.(html?|php|aspx?)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    if not name:
        name = "page"

    return Path(outputDir) / f"{name}.md"


def convertUrlToMarkdown(
    url: str,
    outputPath: str = None,
    includeLinks: bool = True,
    includeImages: bool = False,
) -> str:
    """Fetch a URL and convert its content to Markdown.

    Args:
        url: The URL to fetch and convert.
        outputPath: Optional output file path. Auto-generated from URL if not provided.
        includeLinks: If True, preserve hyperlinks in output.
        includeImages: If True, preserve image references in output.

    Returns:
        The generated Markdown text.
    """
    if outputPath is None:
        outPath = generateOutputFilename(url)
    else:
        outPath = Path(outputPath)

    print(f"Fetching:   {url}")

    html = fetchPage(url)
    print(f"Received:   {len(html):,} characters of HTML")

    print("Converting to Markdown...")
    markdownText = convertToMarkdown(html, url, includeLinks, includeImages)

    # Write output
    outPath.parent.mkdir(parents=True, exist_ok=True)
    outPath.write_text(markdownText, encoding="utf-8")
    print(f"Done!       {len(markdownText):,} characters written to {outPath}")

    return markdownText


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch a web page and convert it to clean Markdown"
    )
    parser.add_argument("url", help="URL of the page to convert")
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: auto-generated in outputs/ from URL)",
    )
    parser.add_argument(
        "--include-links",
        action="store_true",
        default=True,
        help="Preserve hyperlinks in output (default: True)",
    )
    parser.add_argument(
        "--no-links",
        action="store_true",
        help="Strip hyperlinks from output",
    )
    parser.add_argument(
        "--include-images",
        action="store_true",
        help="Preserve image references in output",
    )

    args = parser.parse_args()

    includeLinks = not args.no_links
    convertUrlToMarkdown(args.url, args.output, includeLinks, args.include_images)
