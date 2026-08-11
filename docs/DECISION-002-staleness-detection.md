<!-- Copyright (c) 2026 Mustafa Uzumeri. All rights reserved. -->

# Proposal: Staleness Detection for Curated Reference Material

> **Status:** Proposal  
> **Date:** 2026-03-14  
> **Author:** Mustafa Uzumeri  
> **Context:** ROADMAP.md §8, Open Question 6 ("Update monitoring")

---

## 1. Problem

Reference documents in the Knowledge Slot go stale. Regulations are amended, standards are revised, trade associations publish new editions of contracts, government agencies update grading requirements. A non-technical curator — a trade association officer, a regulatory specialist — has no systematic way to know that a document in their workspace has been superseded unless they happen to notice.

This is not a theoretical concern. In the grain trading vertical alone, GAFTA periodically revises its standard contracts; the Canadian Grain Commission updates grading standards; Incoterms had a major revision in 2020. A marketplace operating on outdated reference material risks providing incorrect compliance guidance, incorrect contract terms, or incorrect quality specifications — any of which could damage trust and obstruct transactions.

The existing ROADMAP flags this as Open Question 6 but offers no mechanism to address it.

---

## 2. Proposed Mechanism: Periodic Staleness Scan

A background process runs on a configurable schedule (e.g., weekly or monthly) and checks each document in the workspace for indicators that its content may have changed or been superseded. It does not attempt to automatically update content — it generates **staleness alerts** for the curator to review and act on.

### 2.1 — Three Detection Strategies

The scanner uses three complementary strategies, in order of reliability:

#### Strategy A: Source URL Monitoring (Highest Confidence)

For documents with a recorded `source_url` in their provenance record:

1. Fetch the URL using HTTP HEAD or GET.
2. Compare the response's `Last-Modified` header, `ETag`, or content hash against the stored values from the original fetch.
3. If the content has changed, flag the document as **"Source Changed"**.
4. If the URL returns a 404 or redirect, flag as **"Source Moved or Removed"**.

This is deterministic and reliable, but only works for documents that were originally fetched from a URL — not for documents uploaded from email or shared drives.

#### Strategy B: LLM-Assisted Web Search (Medium Confidence)

For all documents, regardless of how they were acquired:

1. Construct a search query from the document's provenance metadata: issuing organization, document identifier, title, and publication date.
   - Example: `"Grain and Feed Trade Association" "Contract No. 27" 2025 OR 2026 OR 2027`
2. Send this query to a web search tool (via MCP Slot or direct API).
3. Pass the search results to an LLM with a staleness assessment prompt:
   - "Given that we hold [title] published by [org] dated [date], do these search results indicate that a newer edition, amendment, or replacement has been published?"
4. If the LLM assessment indicates a likely update, flag the document as **"Possible Update Detected"** with the LLM's reasoning and source links.

This is not foolproof — the LLM may hallucinate or misinterpret search results — but it casts a wide net and catches updates that URL monitoring alone would miss.

#### Strategy C: Age-Based Review Threshold (Lowest Confidence, Highest Coverage)

For all documents:

1. Compare the document's `date_published` (from provenance/extracted metadata) against a configurable `review_after_months` threshold (default: 12 months).
2. If the document is older than the threshold, flag it as **"Due for Review"**.
3. The threshold can be set per document type (e.g., regulations might have a 6-month review cycle, industry guides might have 24 months).

This is a blunt instrument — many documents remain valid for years — but it ensures nothing is silently forgotten. The curator can dismiss the alert and reset the clock.

### 2.2 — Alert Presentation

Staleness alerts are presented in the curation tool's GUI as a dedicated **"Freshness Check"** panel, alongside the demand-driven gap signal queue. Each alert shows:

- Document title and identifier
- Issuing organization
- Date of last verification
- Alert type (Source Changed / Possible Update / Due for Review)
- Confidence level (High / Medium / Low)
- LLM reasoning (for Strategy B alerts)
- Links to potentially updated sources
- Action buttons: **Dismiss** (reset review clock), **Investigate** (open in browser), **Replace** (start ingestion of updated version)

### 2.3 — Alert Lifecycle

```
Scan detects staleness indicator
        ↓
Alert created (status: PENDING)
        ↓
Curator reviews alert
        ↓
    ┌───────────────────────────┐
    │                           │
 DISMISS                    INVESTIGATE
 (document is still          (curator checks
  current; reset clock)       the source)
                                │
                         ┌──────┴──────┐
                         │             │
                    NO CHANGE       UPDATE FOUND
                    (dismiss)       (curator ingests
                                    new version via
                                    existing pipeline)
                                        │
                                   Old document archived
                                   New document linked to
                                   same metadata scope
                                        │
                                   Alert status: RESOLVED
```

---

## 3. Data Requirements

The provenance system already captures most of what is needed. The following additions are required:

| Field | Where | Purpose |
|-------|-------|---------|
| `last_verified_at` | Provenance record | Timestamp of last successful freshness check |
| `content_hash` | Provenance record | Hash of document content at time of ingestion (for URL change detection) |
| `http_etag` | Provenance record | ETag from original HTTP response (if URL-sourced) |
| `http_last_modified` | Provenance record | Last-Modified header from original HTTP response |
| `review_after_months` | Workspace config or per-document | Configurable staleness threshold |

A new `staleness_alerts` store (JSON file per workspace, or table if database-backed) tracks:

| Field | Purpose |
|-------|---------|
| `alert_id` | Unique identifier |
| `document_stem` | Which document triggered the alert |
| `alert_type` | `source_changed`, `possible_update`, `due_for_review` |
| `confidence` | `high`, `medium`, `low` |
| `detected_at` | When the scan found the indicator |
| `evidence` | LLM reasoning, changed headers, search result URLs |
| `status` | `pending`, `dismissed`, `investigating`, `resolved` |
| `resolved_at` | When the curator acted on it |
| `notes` | Curator's notes on disposition |

---

## 4. Implementation Considerations

### 4.1 — Scope

This is entirely a CommonContext curation tool feature. It does not affect the Cosolvent runtime. The live marketplace serves whatever is in the `reference_library` table; the staleness scanner operates offline on the curation workspace.

### 4.2 — LLM Cost

Strategy B (web search + LLM assessment) consumes LLM tokens. For a workspace with 50 documents scanned monthly, the cost is negligible (perhaps 50 short LLM calls via OpenRouter). For larger workspaces, the scan can be batched or frequency-reduced.

### 4.3 — False Positives

The system should be tuned to accept false positives rather than miss real updates. A curator dismissing a spurious "Due for Review" alert costs seconds. A marketplace operating on a superseded regulation costs trust.

### 4.4 — Relationship to the Pull System

Staleness detection and demand-driven curation are complementary:

- **Pull signals** tell the curator: *"Someone asked a question we can't answer."* (Missing content)
- **Staleness alerts** tell the curator: *"Something we're claiming is authoritative may no longer be current."* (Degraded content)

Both feed into the same curator workflow — a prioritized queue of items needing attention. They can share the same UI panel.

---

## 5. Proposed ROADMAP Updates

**Add to §2 — Design Principles:**
- New principle **2.9 — Staleness Detection**. Reference documents are periodically checked for indicators of change or supersession. The system alerts the curator rather than attempting automatic updates, preserving the sponsor's editorial authority over the reference library.

**Add to §4.1 — Deliverables:**
- **Staleness assessment prompt** (Editable LLM prompt for evaluating web search results against existing document metadata)

**Add to §5 — Roadmap Phases:**
- Phase 2 or Phase 3: *Record `content_hash`, `http_etag`, and `http_last_modified` during document ingestion for downstream change detection.*
- Phase 4 or new Phase: *Implement staleness scanner with URL monitoring (Strategy A) and age-based review (Strategy C). Strategy B (LLM web search) can follow as an enhancement.*

**Resolve §8 — Open Question 6:**
- This proposal directly addresses Open Question 6 ("How should the system handle updates to reference documents?"). The answer: periodic automated scanning with curator-facing alerts, not automatic replacement.

