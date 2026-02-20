# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Schema Analyzer — LLM-assisted domain schema extraction.

Reads a converted Markdown document and the current domain schema,
sends them to an LLM via OpenRouter, and returns proposed schema
additions and refinements.

The analysis prompt is loaded from prompts/schema_analysis.md so it
can be reviewed and edited without touching code.

Usage (standalone):
    .venv/Scripts/python.exe schema_analyzer.py outputs/document.md

Usage (from server):
    from schema_analyzer import analyseDocument
    result = await analyseDocument("outputs/document.md", "schemas/grain_trade_schema.yaml")
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("curation.analyzer")

# ── Configuration ──────────────────────────────────────────────────────────

PROMPT_DIR = Path("prompts")
SCHEMA_DIR = Path("schemas")
OUTPUT_DIR = Path("outputs")
ANALYSIS_DIR = Path("analyses")

PROMPT_FILE = PROMPT_DIR / "schema_analysis.md"

# OpenRouter endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default model — can be overridden via OPENROUTER_MODEL env var
DEFAULT_MODEL = "google/gemini-2.0-flash-001"

# Env files to search for the API key (in priority order)
ENV_SEARCH_PATHS = [
    Path(".")  / ".env",
    Path.home() / "Documents" / "GitHub" / "DPWebsitePublishingSystem" / ".env",
    Path.home() / "Documents" / "GitHub" / "CosolventAI" / ".env",
]


# ── API Key Discovery ─────────────────────────────────────────────────────

def _discoverApiKey() -> str:
    """Find the OpenRouter API key from environment or known .env files."""
    # 1. Check environment first
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key

    # 2. Try known .env file locations
    for envPath in ENV_SEARCH_PATHS:
        if envPath.exists():
            load_dotenv(envPath, override=False)
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if key:
                logger.info("Loaded API key from %s", envPath)
                return key

    raise RuntimeError(
        "OPENROUTER_API_KEY not found. Set it as an environment variable "
        "or add it to a .env file in one of these locations:\n"
        + "\n".join(f"  - {p}" for p in ENV_SEARCH_PATHS)
    )


# ── Prompt Loading ─────────────────────────────────────────────────────────

def _loadPromptTemplate() -> str:
    """Load the analysis prompt from the prompts/ directory."""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {PROMPT_FILE}\n"
            "Run the server setup to create it, or place a prompt file at that path."
        )
    return PROMPT_FILE.read_text(encoding="utf-8")


def _extractSystemPrompt(template: str) -> str:
    """Extract the System Prompt section from the template."""
    # Find content between "## System Prompt" and the next "---" or "## "
    match = re.search(
        r"## System Prompt\s*\n(.*?)(?=\n---|\n## )",
        template,
        re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _extractUserPrompt(template: str) -> str:
    """Extract everything from '## Analysis Instructions' onward as the user prompt."""
    match = re.search(
        r"(## Analysis Instructions.*)",
        template,
        re.DOTALL,
    )
    return match.group(1).strip() if match else template


def _buildPrompt(
    documentContent: str,
    documentFilename: str,
    existingSchema: str,
    schemaFilename: str,
) -> tuple[str, str]:
    """Build the system and user prompts with variable substitution.

    Returns:
        (systemPrompt, userPrompt) tuple.
    """
    template = _loadPromptTemplate()

    # Substitute variables
    def _sub(text: str) -> str:
        text = text.replace("{{DOCUMENT_CONTENT}}", documentContent)
        text = text.replace("{{DOCUMENT_FILENAME}}", documentFilename)
        text = text.replace("{{EXISTING_SCHEMA}}", existingSchema or "_No existing schema — this is the first analysis._")
        text = text.replace("{{SCHEMA_FILENAME}}", schemaFilename or "none")
        return text

    systemPrompt = _sub(_extractSystemPrompt(template))
    userPrompt = _sub(_extractUserPrompt(template))

    return systemPrompt, userPrompt


# ── LLM Call ───────────────────────────────────────────────────────────────

async def _callOpenRouter(
    systemPrompt: str,
    userPrompt: str,
    model: str | None = None,
) -> str:
    """Send the analysis request to OpenRouter and return the response text."""
    apiKey = _discoverApiKey()
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    headers = {
        "Authorization": f"Bearer {apiKey}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://deeperpoint.com",
        "X-Title": "Knowledge Slot Schema Analyzer",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": systemPrompt},
            {"role": "user", "content": userPrompt},
        ],
        "temperature": 0.3,    # Low temperature for structured analysis
        "max_tokens": 16000,   # Schema output can be long
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        logger.info("Sending analysis request to OpenRouter (model: %s)…", model)
        response = await client.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    data = response.json()

    # Extract the response text
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"No response from OpenRouter: {json.dumps(data, indent=2)}")

    content = choices[0].get("message", {}).get("content", "")

    # Log usage stats
    usage = data.get("usage", {})
    if usage:
        logger.info(
            "Tokens — prompt: %s, completion: %s, total: %s",
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )

    return content


# ── Result Parsing ─────────────────────────────────────────────────────────

def _extractYaml(responseText: str) -> str:
    """Extract the YAML block from the LLM response.

    The model may wrap the YAML in a code fence, or return it raw.
    """
    # Try to find a fenced YAML block
    match = re.search(r"```ya?ml\s*\n(.*?)```", responseText, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no fence, return the whole response (likely raw YAML)
    return responseText.strip()


# ── Public API ─────────────────────────────────────────────────────────────

async def analyseDocument(
    documentPath: str,
    schemaPath: str | None = None,
    model: str | None = None,
) -> dict:
    """Analyse a converted document and propose schema additions.

    Args:
        documentPath: Path to the converted Markdown file.
        schemaPath: Optional path to the existing domain schema YAML.
        model: Optional OpenRouter model override.

    Returns:
        Dict with keys: analysisYaml, rawResponse, documentFilename,
        schemaFilename, model, savedTo.
    """
    docPath = Path(documentPath)
    if not docPath.exists():
        raise FileNotFoundError(f"Document not found: {documentPath}")

    documentContent = docPath.read_text(encoding="utf-8", errors="replace")
    documentFilename = docPath.name

    # Load existing schema if provided
    existingSchema = ""
    schemaFilename = ""
    if schemaPath:
        schemaFile = Path(schemaPath)
        if schemaFile.exists():
            existingSchema = schemaFile.read_text(encoding="utf-8", errors="replace")
            schemaFilename = schemaFile.name
    else:
        # Auto-detect: use the first .yaml in schemas/
        schemaFiles = sorted(SCHEMA_DIR.glob("*.yaml")) + sorted(SCHEMA_DIR.glob("*.yml"))
        if schemaFiles:
            existingSchema = schemaFiles[0].read_text(encoding="utf-8", errors="replace")
            schemaFilename = schemaFiles[0].name

    # Build prompts
    systemPrompt, userPrompt = _buildPrompt(
        documentContent, documentFilename, existingSchema, schemaFilename,
    )

    # Call LLM
    rawResponse = await _callOpenRouter(systemPrompt, userPrompt, model)

    # Extract YAML
    analysisYaml = _extractYaml(rawResponse)

    # Save result
    ANALYSIS_DIR.mkdir(exist_ok=True)
    outputStem = docPath.stem
    outputPath = ANALYSIS_DIR / f"{outputStem}_analysis.yaml"
    outputPath.write_text(
        f"# Schema analysis of: {documentFilename}\n"
        f"# Existing schema: {schemaFilename or 'none'}\n"
        f"# Model: {model or os.environ.get('OPENROUTER_MODEL', DEFAULT_MODEL)}\n"
        f"# Generated by: schema_analyzer.py\n\n"
        f"{analysisYaml}\n",
        encoding="utf-8",
    )
    logger.info("Analysis saved to %s", outputPath)

    return {
        "analysisYaml": analysisYaml,
        "rawResponse": rawResponse,
        "documentFilename": documentFilename,
        "schemaFilename": schemaFilename,
        "model": model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
        "savedTo": str(outputPath),
    }


# ── CLI Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import asyncio

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Analyse a converted document for domain schema extraction"
    )
    parser.add_argument("document", help="Path to the converted Markdown file")
    parser.add_argument(
        "--schema", "-s",
        help="Path to existing schema YAML (auto-detected from schemas/ if omitted)",
    )
    parser.add_argument(
        "--model", "-m",
        help=f"OpenRouter model (default: {DEFAULT_MODEL})",
    )

    args = parser.parse_args()

    result = asyncio.run(analyseDocument(args.document, args.schema, args.model))
    print(f"\nAnalysis saved to: {result['savedTo']}")
    print(f"Model: {result['model']}")
    print(f"Schema used: {result['schemaFilename'] or 'none'}")
