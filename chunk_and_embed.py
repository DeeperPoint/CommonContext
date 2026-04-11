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
from schema_analyzer import _discoverApiKey, _callOpenRouter
from provenance import getProvenance

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
) -> str:
    """Call LLM to get the topic for a specific chunk."""
    template = _loadPromptTemplate()
    
    def _sub(t: str) -> str:
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
            return parsed.get("topic", "general")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON output: {response}")
            return "general"


async def _embed_chunks(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Get embeddings from OpenAI, batching 100 at a time if needed."""
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
                model="text-embedding-3-small",
                input=batch
            )
            return [data.embedding for data in resp.data]
            
        embeddings.extend(await _do_embed())
    return embeddings


async def process_document(
    markdown_path: str,
    schema_path: str,
) -> str:
    """Process a markdown file into contextualized chunks with tags and embeddings."""
    md_file = Path(markdown_path)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown file {markdown_path} not found.")
        
    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file {schema_path} not found.")

    doc_content = md_file.read_text(encoding="utf-8")
    schema_content = schema_file.read_text(encoding="utf-8")
    doc_stem = md_file.stem
    doc_filename = md_file.name
    
    # 1. Semantic split
    raw_chunks = _split_markdown_by_headings(doc_content)
    
    # Filter empty or trivial chunks
    valid_chunks = [c for c in raw_chunks if len(c['content'].strip()) > 10]
    
    # Base provenance
    prov = getProvenance(doc_stem) or {}
    metadata_block = prov.get("extracted_metadata", {})
    doc_meta = metadata_block.get("document_metadata", {})
    org_meta = metadata_block.get("issuing_organization", {})
    geo_meta = metadata_block.get("geographic_scope", {})
    
    # Use correct keys based on the metadata extraction schema
    base_metadata = {
        "doc_type": doc_meta.get("document_type", "unknown"),
        "standard": org_meta.get("name", "unknown"),
        "jurisdiction": geo_meta.get("jurisdictions", ["unknown"]),
    }
    
    # 2. Tagging (Concurrent)
    sem = asyncio.Semaphore(10) # Max 10 concurrent requests
    logger.info(f"Tagging {len(valid_chunks)} chunks for {doc_filename}...")
    
    tasks = [
        _tag_chunk_topic(
            schema_content,
            doc_filename,
            c["hierarchy"],
            c["content"],
            sem
        ) for c in valid_chunks
    ]
    
    topics = await asyncio.gather(*tasks)
    
    # 3. Preparing contextual content and Embedding
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        load_dotenv()
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key:
            logger.warning("OPENAI_API_KEY not found. Attempting OpenRouter key fallback for embeddings.")
            openai_key = _discoverApiKey()
    
    # Check if OpenRouter key should be base
    is_openrouter = openai_key.startswith("sk-or-v1")
    client = AsyncOpenAI(
        api_key=openai_key,
        base_url="https://openrouter.ai/api/v1" if is_openrouter else None
    )

    logger.info(f"Embedding {len(valid_chunks)} chunks...")
    contextual_contents = [
        f"[{doc_filename}] {c['hierarchy']} > {c['content']}" if c['hierarchy'] else f"[{doc_filename}] {c['content']}"
        for c in valid_chunks
    ]
    
    embeddings = await _embed_chunks(client, contextual_contents)
    
    # 4. Stream to JSONL
    out_file = OUTPUT_DIR / f"{doc_stem}_processed.jsonl"
    with open(out_file, 'w', encoding="utf-8") as f:
        for i, (chunk, topic, emb, ctx_content) in enumerate(zip(valid_chunks, topics, embeddings, contextual_contents)):
            metadata = base_metadata.copy()
            metadata["topic"] = topic
            
            record = {
                "chunk_id": f"{doc_stem}_{i}",
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
        print("Usage: python chunk_and_embed.py <markdown_file> <schema_file>")
        sys.exit(1)
        
    md_path = sys.argv[1]
    sch_path = sys.argv[2]
    
    asyncio.run(process_document(md_path, sch_path))
