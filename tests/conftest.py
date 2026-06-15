# Copyright (c) 2026 Mustafa Uzumeri. All rights reserved.
"""
Shared pytest fixtures and external-boundary mocks for the Knowledge Slot
curation test suite.

The pipeline talks to two paid external services — OpenRouter (chunk topic
tagging) and OpenAI (embeddings). The unit/e2e tests never hit the network:
`patched_pipeline` replaces both boundaries with deterministic fakes so the
*pipeline logic* (splitting, contextual enrichment, metadata mapping, JSONL
streaming) is exercised end to end without API keys or cost.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root on sys.path so `import chunk_and_embed`, `import provenance`, etc. work
# regardless of the directory pytest is invoked from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# schemas/ is imported as a top-level module by the pipeline code.
SCHEMAS = ROOT / "schemas"
if str(SCHEMAS) not in sys.path:
    sys.path.insert(0, str(SCHEMAS))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

EMBED_DIM = 1536


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


class _FakeEmbedding:
    def __init__(self, vector):
        self.embedding = vector


class _FakeEmbeddingsResponse:
    def __init__(self, vectors):
        self.data = [_FakeEmbedding(v) for v in vectors]


class _FakeEmbeddingsAPI:
    """Deterministic stand-in for client.embeddings."""

    def __init__(self, calls):
        self._calls = calls

    async def create(self, model, input):
        self._calls.append({"model": model, "n": len(input)})
        # Deterministic, content-derived vectors so similarity tests are stable.
        vectors = []
        for text in input:
            seed = (sum(ord(c) for c in text) % 97) / 100.0
            vectors.append([seed] * EMBED_DIM)
        return _FakeEmbeddingsResponse(vectors)


class _FakeAsyncOpenAI:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs
        self.embeddings = _FakeEmbeddingsAPI(_FakeAsyncOpenAI.embed_calls)

    # Class-level call log so tests can assert how embeddings were invoked.
    embed_calls: list = []


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Patch the OpenRouter tagging call and the OpenAI embeddings client.

    Yields a dict of call logs the test can assert against:
      - tag_calls: every chunk text sent to the (fake) topic tagger
      - topic_map: optional dict the test can fill to control returned topics
    """
    import chunk_and_embed as ce

    tag_calls: list[str] = []
    topic_map: dict[str, str] = {}
    default_topic = {"value": "general"}

    async def fake_call_openrouter(system_prompt: str, user_prompt: str, model=None):
        tag_calls.append(user_prompt)
        topic = default_topic["value"]
        # Match needles only against the chunk text region, not the whole prompt
        # (which embeds the schema YAML and would match unrelated topic words).
        region = user_prompt
        if "Chunk Text:" in user_prompt:
            region = user_prompt.split("Chunk Text:", 1)[1]
        for needle, mapped in topic_map.items():
            if needle.lower() in region.lower():
                topic = mapped
                break
        return '{"topic": "%s"}' % topic

    _FakeAsyncOpenAI.embed_calls = []
    monkeypatch.setattr(ce, "_callOpenRouter", fake_call_openrouter)
    monkeypatch.setattr(ce, "AsyncOpenAI", _FakeAsyncOpenAI)
    # Ensure the embedding-key branch is satisfied without touching real .env.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")

    yield {
        "tag_calls": tag_calls,
        "topic_map": topic_map,
        "default_topic": default_topic,
        "embed_calls": _FakeAsyncOpenAI.embed_calls,
    }
