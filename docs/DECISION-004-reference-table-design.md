<!-- Copyright (c) 2026 Mustafa Uzumeri. All rights reserved. -->

# DECISION-004: Reference Library Table Design

> **Status:** Open — awaiting team discussion  
> **Date:** 2026-03-14  
> **Author:** Mustafa Uzumeri  
> **Extracted from:** DECISION-000 §4 / §9, Question 4  
> **Related:** DECISION-001 (pull signal transport), ROADMAP §2.8 (demand-driven curation)

---

## 1. Problem

The Knowledge Slot needs database tables in Cosolvent to store sponsor-curated reference material. The design must support:

1. **Document-level metadata** — title, authority, type, vertical-specific tags — for filtering.
2. **Chunk-level embeddings** — for vector similarity search.
3. **Citation** — answers must cite specific clauses or sections, not just "from document X."
4. **Gap tracking** — the Pull System (ROADMAP §2.8) needs a place to record knowledge gaps detected during live queries.

The existing `ai_document_chunks` table (used for participant-uploaded documents) conflates document identity with chunks and lacks the metadata structure needed for reference material. Reference documents must be architecturally separate from participant documents (ROADMAP §2.1).

---

## 2. Proposed Design: Three Tables

### 2.1 — `reference_documents` (document-level metadata)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `title` | TEXT | e.g. "GAFTA Contract No. 27 (2025)" |
| `source_authority` | TEXT | e.g. "GAFTA" |
| `document_type` | TEXT | "contract", "regulation", "guide", "standard", etc. |
| `version` | TEXT | e.g. "2025 edition" |
| `source_url` | TEXT (nullable) | For staleness detection (DECISION-002) |
| `content_hash` | TEXT (nullable) | For change detection (DECISION-002) |
| `vertical_metadata` | JSONB | Vertical-specific tags (see below) |
| `status` | TEXT | "draft", "active", "superseded" |
| `uploaded_by` | UUID (FK → users) | The admin/sponsor |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 2.2 — `reference_chunks` (chunk-level embeddings)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `document_id` | UUID (FK → reference_documents, CASCADE) | |
| `chunk_index` | INTEGER | |
| `chunk_text` | TEXT | |
| `embedding` | Vector(1536) | Must match participant embedding model |
| `chunk_metadata` | JSONB | Inherited from parent + chunk-specific |
| `section_id` | TEXT (nullable) | Clause/section identifier for citation |
| `created_at` | TIMESTAMPTZ | |
| UNIQUE(`document_id`, `chunk_index`) | | |

### 2.3 — `knowledge_gap_signals` (demand-driven curation)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID (PK) | |
| `raw_query` | TEXT | The user's original question |
| `inferred_scope` | JSONB | e.g. `{"region": "buenos_aires", "vertical": "irish_music"}` |
| `transaction_context` | TEXT (nullable) | e.g. "Buyer in X querying requirements for Seller in Y" |
| `querying_user_id` | UUID (FK → users) | For notification when gap is resolved |
| `confidence_score` | FLOAT (nullable) | RAG retrieval confidence that triggered the gap |
| `fallback_response` | TEXT (nullable) | The unverified answer that was returned |
| `status` | TEXT | "pending", "assigned", "resolved", "dismissed" |
| `resolved_by_document_id` | UUID (FK → reference_documents, nullable) | Links resolution to the ingested document |
| `curator_notes` | TEXT (nullable) | |
| `created_at` | TIMESTAMPTZ | |
| `resolved_at` | TIMESTAMPTZ (nullable) | |

---

## 3. Design Rationale

### Why Two Tables for Reference Content (Not One)?

The existing `ai_document_chunks` stores both document identity and chunk data in a single row. This works for participant uploads (one-off documents with minimal metadata) but fails for reference material because:

- **Filtering requires document-level metadata.** A query scoped to "Japan wheat regulations" should filter at the document level, then search chunks within matching documents. A flat table would duplicate metadata across every chunk.
- **Citation requires section identity.** An answer citing "GAFTA Contract 27, Clause 18" needs a `section_id` on the chunk, plus the document title from the parent row.
- **Document lifecycle is independent of chunks.** When a document is superseded, its status changes at the document level. Chunks are re-generated when a new version is ingested.

### Why a Separate Gap Signals Table?

Gap signals are a fundamentally different data type from reference content. They are:
- Created by the Cosolvent runtime (not the curation tool)
- Consumed by the curator (not by the RAG pipeline)
- Transient — they are resolved or dismissed, not queried by users

Storing them alongside reference documents would conflate the work queue with the knowledge base.

### `vertical_metadata` JSONB Approach

Different verticals tag reference documents with radically different metadata. Grain trading uses `origin_country`, `commodity_type`, `trade_terms`. Mental health uses `jurisdiction`, `clinical_area`, `insurance_provider`. Defense procurement uses `export_control_regime`, `nato_stock_number`.

A JSONB column accommodates this without schema changes per vertical. The allowed keys and values are defined by the `reference_metadata_schema` in the vertical's configuration, not by the database schema.

---

## 4. Open Sub-Questions

### 4.1 — Where Does `knowledge_gap_signals` Live?

This table is populated by Cosolvent (runtime) and consumed by KnowledgeSlot (curation tool). Its physical location depends on the transport decision in **DECISION-001**:

| DECISION-001 Outcome | `knowledge_gap_signals` Location |
|----------------------|----------------------------------|
| Option A (shared database) | Cosolvent's PostgreSQL, read by KnowledgeSlot |
| Option B (API) | KnowledgeSlot's own store, populated via API from Cosolvent |
| Option C (file-based) | Exported as JSON from Cosolvent, imported by KnowledgeSlot |

This decision should be made after DECISION-001 is resolved.

### 4.2 — Cross-Slot Search Interface

DECISION-000 §4 proposed a composable retrieval interface:

```python
@dataclass
class RetrievalResult:
    source: Literal["participant_docs", "reference_library"]
    content: str
    metadata: dict[str, Any]
    score: float
    citation: str | None
```

Both participant document search and reference library search should return this same shape, so callers can request merged results. **Does the team agree with this interface?**

---

## 5. Decision

> *(To be filled in after team discussion.)*

**Two-table design accepted?**  
**Gap signals table accepted?**  
**JSONB metadata approach accepted?**  
**Rationale:**  
**Date decided:**  
**Action items:**
