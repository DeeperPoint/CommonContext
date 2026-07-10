# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.

"""
Chunking & Tagging Pipeline

Processes KnowledgeSlot Markdown into semantically coherent, tagged, and embedded
chunks. Implements contextual chunking (prepending heading lineage to resolve
"lost in the middle" relevance issues) and streams to `.jsonl` for consumption
by downstream Cosolvent vector stores.

Data flows: markdown -> semantic split -> LLM tagging (OpenRouter) -> Embedding (OpenAI) -> JSONL
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Re-use utilities
from schema_analyzer import _callOpenRouter
from provenance import getProvenance

# The reference metadata models live in schemas/, which is not a package on the
# import path during a CLI run; add it so the tagging step can read the
# authoritative topic vocabulary straight from the pydantic model.
import sys as _sys
_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
if str(_SCHEMAS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCHEMAS_DIR))
from reference_metadata_schema import get_allowed_topics

logger = logging.getLogger("curation.chunker")
logging.basicConfig(level=logging.INFO)

PROMPT_DIR = Path("prompts")
PROMPT_FILE = PROMPT_DIR / "chunk_tagging.md"
SCHEMA_DIR = Path("schemas")
OUTPUT_DIR = Path("outputs")


def _loadPromptTemplate() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt template missing: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


# A leading YAML frontmatter block (provenance injected by provenance.py) must
# be stripped before chunking, otherwise it is embedded as a meaningless first
# chunk and pollutes vector search.
_FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(content: str) -> str:
    """Remove a single leading YAML frontmatter block, if present."""
    return _FRONTMATTER_RE.sub("", content, count=1)


# Known standards bodies for the grain vertical, in match priority order.
_KNOWN_STANDARDS = ["GAFTA", "CGC", "USDA", "FGIS", "IUA", "ICC", "ISO"]


def _normalize_standard(name: str | None) -> str | None:
    """Map a free-form issuing-organization name to a known standard enum value.

    The metadata extractor records full organisation names (e.g. "Grain and
    Feed Trade Association (GAFTA)"); the reference metadata schema expects the
    acronym ("GAFTA"). Returns None when no known standard is recognised, which
    is a valid (Optional) value for the schema.
    """
    if not name:
        return None
    upper = name.upper()
    for code in _KNOWN_STANDARDS:
        if code in upper:
            return code
    return None


# Known standards bodies for the manufacturing vertical (ROADMAP §2.2).
_KNOWN_STANDARD_BODIES = ["ASTM", "ISO", "DIN", "JIS", "SAE", "ANSI", "MIL", "EN"]


def _normalize_standard_body(name: str | None) -> str | None:
    """Map a free-form organisation name to a known manufacturing standards body."""
    if not name:
        return None
    upper = name.upper()
    for code in _KNOWN_STANDARD_BODIES:
        # Word-ish boundary check keeps short codes like "EN" from matching
        # inside unrelated words.
        if re.search(rf"\b{code}\b", upper):
            return code
    return None


def _build_base_metadata(vertical: str, metadata_block: dict[str, Any]) -> dict[str, Any]:
    """Build the document-level metadata for a chunk, per vertical.

    This is the seam that makes the pipeline vertical-agnostic: the chunk-level
    `topic` is always tagged by the schema-driven LLM call, while the doc-level
    fields are mapped from the provenance/metadata block according to the active
    vertical's reference metadata schema.
    """
    doc_meta = metadata_block.get("document_metadata", {})
    org_meta = metadata_block.get("issuing_organization", {})
    geo_meta = metadata_block.get("geographic_scope", {})

    if vertical == "manufacturing":
        material_meta = metadata_block.get("material", {})
        return {
            "doc_type": doc_meta.get("document_type", "specification"),
            "standard_body": _normalize_standard_body(org_meta.get("name")),
            "material_class": material_meta.get("material_class"),
            "export_control_regime": material_meta.get("export_control_regime"),
            "process_type": material_meta.get("process_type", []),
            "jurisdiction": geo_meta.get("jurisdictions", []),
        }

    # grain (default)
    return {
        "doc_type": doc_meta.get("document_type", "other"),
        "standard": _normalize_standard(org_meta.get("name")),
        "jurisdiction": geo_meta.get("jurisdictions", []),
    }


def _split_markdown_by_headings(content: str) -> list[dict[str, str]]:
    """Splits markdown into clauses mapped to their header hierarchy."""
    lines = content.split('\n')
    chunks = []
    
    current_headers = {}
    current_chunk_lines = []
    
    header_pattern = re.compile(r'^(#{1,6})\s+(.*)$')
    
    for line in lines:
        match = header_pattern.match(line)
        if match:
            # We hit a new header. Save the previous chunk if it has content.
            joined_content = '\n'.join(current_chunk_lines).strip()
            if joined_content:
                # Build hierarchy string
                hierarchy = " > ".join(
                    v for k, v in sorted(current_headers.items())
                )
                chunks.append({
                    "hierarchy": hierarchy,
                    "content": joined_content
                })
            
            # Update header state
            level = len(match.group(1))
            title = match.group(2).strip()
            
            current_headers[level] = title
            # Remove deeper/lower levels
            keys_to_remove = [k for k in current_headers.keys() if k > level]
            for k in keys_to_remove:
                del current_headers[k]
                
            current_chunk_lines = []
        else:
            current_chunk_lines.append(line)
            
    # Add final chunk
    joined_content = '\n'.join(current_chunk_lines).strip()
    if joined_content:
        hierarchy = " > ".join(
            v for k, v in sorted(current_headers.items())
        )
        chunks.append({
            "hierarchy": hierarchy,
            "content": joined_content
        })
        
    return chunks


async def _tag_chunk_topic(
    schema_content: str,
    doc_filename: str,
    hierarchy: str,
    chunk_text: str,
    semaphore: asyncio.Semaphore,
    allowed_topics: list[str],
) -> str:
    """Call LLM to get the topic for a specific chunk.

    The returned topic is coerced to "general" if the model emits a value
    outside the schema's controlled vocabulary, guaranteeing schema-valid output.
    """
    template = _loadPromptTemplate()

    def _sub(t: str) -> str:
        t = t.replace("{{ALLOWED_TOPICS}}", ", ".join(allowed_topics))
        t = t.replace("{{SCHEMA_CONTENT}}", schema_content)
        t = t.replace("{{DOCUMENT_FILENAME}}", doc_filename)
        t = t.replace("{{HEADING_CONTEXT}}", hierarchy or "None")
        t = t.replace("{{CHUNK_CONTENT}}", chunk_text)
        return t
    
    system_prompt = _sub(template.split("## Analysis Instructions")[0].replace("## System Prompt", "").strip())
    user_prompt = _sub(template.split("## Analysis Instructions")[1].strip())
    
    async with semaphore:
        # Wrap _callOpenRouter in a tenacity-driven retry internally or locally
        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True,
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException))
        )
        async def _do_call():
            return await _callOpenRouter(system_prompt, user_prompt)
            
        response = await _do_call()
        
        # Clean response to ensure it parses as JSON
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            parsed = json.loads(response)
            topic = parsed.get("topic", "general")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON output: {response}")
            return "general"

        # Enforce the controlled vocabulary: anything off-enum becomes "general"
        # so the JSONL always validates against the reference metadata schema.
        if topic not in allowed_topics:
            logger.warning(
                "LLM returned off-vocabulary topic %r; coercing to 'general'.", topic
            )
            return "general"
        return topic


async def _embed_chunks(client: AsyncOpenAI, texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Get embeddings from the configured provider, batching 100 at a time if needed."""
    embeddings = []
    # Process in batches to stay within safe limits
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        async def _do_embed():
            resp = await client.embeddings.create(
                model=model,
                input=batch
            )
            return [data.embedding for data in resp.data]
            
        embeddings.extend(await _do_embed())
    return embeddings


async def process_document(
    markdown_path: str,
    schema_path: str,
    vertical: str = "grain",
    *,
    source_layer: str = "raw",
    identity_stem: str | None = None,
) -> str:
    """Process a markdown file into contextualized chunks with tags and embeddings.

    ``source_layer`` ("raw" | "wiki") is stamped on every chunk's metadata so the
    reference library can prefer high-signal wiki chunks and fall back to raw ones.
    ``identity_stem`` overrides the id/output-file stem (used for wiki pages, whose
    filenames can collide with raw docs — e.g. sources/27_2025.md vs 27_2025.pdf).
    """
    md_file = Path(markdown_path)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown file {markdown_path} not found.")

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file {schema_path} not found.")

    doc_content = _strip_frontmatter(md_file.read_text(encoding="utf-8"))
    schema_content = schema_file.read_text(encoding="utf-8")
    doc_stem = md_file.stem
    doc_filename = md_file.name
    ident = identity_stem or doc_stem  # id/output identity (may differ from provenance stem)

    # 1. Semantic split
    raw_chunks = _split_markdown_by_headings(doc_content)
    
    # Filter empty or trivial chunks
    valid_chunks = [c for c in raw_chunks if len(c['content'].strip()) > 10]
    
    # Base provenance
    prov = getProvenance(doc_stem) or {}
    metadata_block = prov.get("extracted_metadata", {})

    # Document-level metadata, mapped according to the active vertical's schema.
    base_metadata = _build_base_metadata(vertical, metadata_block)
    
    # 2. Tagging (Concurrent)
    sem = asyncio.Semaphore(10) # Max 10 concurrent requests
    allowed_topics = get_allowed_topics(vertical)
    logger.info(f"Tagging {len(valid_chunks)} chunks for {doc_filename}...")

    tasks = [
        _tag_chunk_topic(
            schema_content,
            doc_filename,
            c["hierarchy"],
            c["content"],
            sem,
            allowed_topics,
        ) for c in valid_chunks
    ]
    
    topics = await asyncio.gather(*tasks)
    
    # 3. Preparing contextual content and Embedding
    # Prefer a SINGLE OpenRouter key for embeddings (model openai/text-embedding-3-small,
    # 1536-dim — matches Cosolvent's reference_library). Fall back to a direct OpenAI key.
    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    oa_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not (or_key or oa_key):
        load_dotenv()
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        oa_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if or_key:
        client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
        embed_model = "openai/text-embedding-3-small"
    elif oa_key:
        client = AsyncOpenAI(api_key=oa_key)
        embed_model = "text-embedding-3-small"
    else:
        raise RuntimeError("No embedding key found — set OPENROUTER_API_KEY (preferred) or OPENAI_API_KEY.")

    logger.info(f"Embedding {len(valid_chunks)} chunks via {embed_model}...")
    contextual_contents = [
        f"[{doc_filename}] {c['hierarchy']} > {c['content']}" if c['hierarchy'] else f"[{doc_filename}] {c['content']}"
        for c in valid_chunks
    ]
    
    embeddings = await _embed_chunks(client, contextual_contents, embed_model)
    
    # 4. Stream to JSONL
    out_file = OUTPUT_DIR / f"{ident}_processed.jsonl"
    with open(out_file, 'w', encoding="utf-8") as f:
        for i, (chunk, topic, emb, ctx_content) in enumerate(zip(valid_chunks, topics, embeddings, contextual_contents)):
            metadata = base_metadata.copy()
            metadata["topic"] = topic
            metadata["source_layer"] = source_layer

            record = {
                "chunk_id": f"{ident}_{i}",
                "content": chunk["content"],
                "contextual_content": ctx_content,
                "metadata": metadata,
                "embedding": emb
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    logger.info(f"Successfully processed {len(valid_chunks)} chunks to {out_file}")
    return str(out_file)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python chunk_and_embed.py <markdown_file> <schema_file> [vertical]")
        sys.exit(1)

    md_path = sys.argv[1]
    sch_path = sys.argv[2]
    vertical = sys.argv[3] if len(sys.argv) > 3 else "grain"

    asyncio.run(process_document(md_path, sch_path, vertical))
