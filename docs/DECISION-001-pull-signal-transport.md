<!-- Copyright (c) 2026 Mustafa Uzumeri. All rights reserved. -->

# Design Decision: Pull Signal Transport Between Cosolvent and CommonContext

> **Status:** Open — awaiting team discussion  
> **Date:** 2026-03-14  
> **Author:** Mustafa Uzumeri  
> **Context:** ROADMAP.md §2.8 (Demand-Driven Curation) and Roadmap-Update-Demand-Curation.md

---

## 1. Background

The CommonContext is a sponsor-curated reference library that provides authoritative domain knowledge to a Cosolvent marketplace deployment. It was originally conceived as a "push" system: the sponsor proactively fills the library with reference documents before and during marketplace operation.

We have now added a "pull" mechanism (ROADMAP §2.8). When a user asks a question that the CommonContext cannot answer authoritatively, Cosolvent:

1. **Falls back** to general LLM/web knowledge, clearly labeled as "unverified."
2. **Fires a gap signal** to the CommonContext system, notifying the curator that a specific piece of authoritative information is missing and has commercial value (because a real user needed it).

When the curator responds by ingesting an authoritative document that addresses the gap, the original querying user is notified that their question can now be answered from verified sources.

This creates a closed loop:

```
User query → Cosolvent detects gap → unverified fallback + gap signal → CommonContext curator
                                                                              ↓
                                                                    Curator ingests document
                                                                              ↓
                                                              Gap resolved → user notified
```

---

## 2. The Design Question

**How do Cosolvent (the live runtime) and CommonContext (the curation tool) exchange signals?**

Two signals must flow between the systems:

| Signal | Direction | Trigger | Payload |
|--------|-----------|---------|---------|
| **Gap Signal** | Cosolvent → CommonContext | User query falls below confidence threshold | Raw query, inferred metadata scope (region, vertical, product), transaction context, user ID, timestamp |
| **Resolution Signal** | CommonContext → Cosolvent | Curator ingests a document that addresses a tracked gap | Gap ID, new document reference, resolution timestamp |

The current CommonContext curation tool (`server.py`) is an **offline, single-user application**. It runs locally when the sponsor is actively curating content. It does not have a persistent service endpoint or a database shared with Cosolvent. This is the core tension: one system is always running (Cosolvent), the other runs intermittently (CommonContext).

---

## 3. System Responsibilities (Not in Dispute)

Before discussing transport options, the ownership boundaries are clear:

| Responsibility | Owner | Rationale |
|----------------|-------|-----------|
| Detect the gap (confidence thresholds, LLM self-assessment) | **Cosolvent** | Happens during live query processing in the Intelligence Slot |
| Generate the unverified fallback response | **Cosolvent** | Happens during live query processing |
| Label the fallback as "unverified" in the UI | **Cosolvent** | UX responsibility of the runtime |
| Store and manage gap signals | **CommonContext** | The curator is the actor who resolves gaps; the gap queue is their work list |
| Present the gap queue to the curator | **CommonContext** | Part of the curation tool UX |
| Ingest authoritative documents that resolve gaps | **CommonContext** | Core function of the curation pipeline |
| Link new documents back to the gap they resolve | **CommonContext** | Closes the curation loop |
| Notify the original user that the gap is resolved | **Cosolvent** | Cosolvent knows the user; CommonContext does not |

---

## 4. Options for Transport

### Option A: Shared Database Table

Cosolvent writes gap signals directly to a `knowledge_gap_signals` table. When the CommonContext curation tool starts, it reads from this table to populate the curator's queue. When a gap is resolved, the curation tool updates the table, and Cosolvent's notification system picks up the resolution.

```
Cosolvent ──writes──→ knowledge_gap_signals table ←──reads── CommonContext
                             (shared database)
```

**Pros:**
- Simplest to implement — no new infrastructure beyond a database table
- Both systems already depend on the same PostgreSQL instance (Cosolvent's database)
- Gap signals are immediately available; no delivery lag
- Transaction-safe — signals can't be lost

**Cons:**
- Couples CommonContext to Cosolvent's database at deployment time
- Assumes the curation tool has network access to the production database
- Makes it harder to run CommonContext independently (e.g., on a laptop at a conference)
- Security concern: the curation tool gets write access to a production database table

### Option B: API Endpoint (CommonContext as a Service)

CommonContext exposes a lightweight API endpoint that Cosolvent calls to deliver gap signals. CommonContext stores them locally. When gaps are resolved, CommonContext calls a Cosolvent API endpoint to deliver the resolution signal.

```
Cosolvent ──POST /api/gap-signal──→ CommonContext API
CommonContext ──POST /api/gap-resolved──→ Cosolvent API
```

**Pros:**
- Clean separation — each system owns its own data store
- CommonContext can run anywhere (cloud, local, different network)
- Well-defined interface contract (API schema)
- Each system can evolve independently

**Cons:**
- Requires CommonContext to be running as a persistent service (it currently is not)
- Introduces a delivery reliability problem — what if CommonContext is down when a gap signal fires?
- More infrastructure to deploy and maintain
- Requires authentication/authorization between services

### Option C: File-Based Exchange (Export/Import)

Cosolvent periodically exports gap signals to a file (JSON or YAML). The CommonContext curation tool imports this file when the curator starts a session. Resolutions are exported from CommonContext and imported back into Cosolvent.

```
Cosolvent ──exports──→ gap_signals.json ──imports──→ CommonContext
CommonContext ──exports──→ resolutions.json ──imports──→ Cosolvent
```

**Pros:**
- No coupling between systems at runtime
- Works even when the systems are on different networks (file can be emailed, synced, etc.)
- Matches the current offline curation workflow
- Trivial to implement — just JSON file I/O

**Cons:**
- Not real-time — gap signals are delayed until the next export/import cycle
- Manual step required (someone has to transfer the file)
- Risk of stale or duplicate signals if the process isn't disciplined
- No automatic user notification — Cosolvent has to poll for resolution files

### Option D: Hybrid (Shared Table + Offline Fallback)

Use Option A (shared database) as the primary mechanism when CommonContext has network access to the Cosolvent database. Provide Option C (file export/import) as a fallback for offline or disconnected curation sessions.

**Pros:**
- Real-time when connected; functional when disconnected
- Covers the conference-demo and disconnected-sponsor scenarios
- Allows the system to start simple (file-based) and upgrade to shared-table when deployed

**Cons:**
- Two code paths to maintain
- Potential for conflicts if both paths are used simultaneously
- More complex to test

---

## 5. Additional Considerations

### 5.1 — Scale

For the foreseeable future, the gap signal volume will be low. A newly deployed marketplace might generate tens or hundreds of gap signals per month, not thousands. This argues against over-engineering the transport. A polling mechanism or periodic import is likely sufficient.

### 5.2 — Workspace Separation

A separate but related proposal suggests organizing CommonContext content into named **workspaces** (one per vertical deployment). If adopted, gap signals would need to be routed to the correct workspace. This is straightforward for all options — the signal simply carries a `workspace_id` or `vertical_id` field.

### 5.3 — Who Is the Curator?

The curator may not be a developer. In many deployments, the curator is a domain expert (a trade association officer, a regulatory specialist, a procurement manager) using the CommonContext GUI. The transport mechanism should be invisible to them — they should see a prioritized queue of "questions people are asking that we can't answer yet," not a database connection string.

### 5.4 — The Gap Detection Prompt

Regardless of transport choice, the **gap detection prompt** (a deliverable already listed in ROADMAP §4.1) is the critical piece. This is the LLM instruction set that tells the model:
- When to declare that available reference material is insufficient
- How to structure the metadata of a gap signal (what region, what vertical, what type of information is missing)
- How to generate a useful unverified fallback without undermining the authority of the Knowledge Slot

This prompt is owned by CommonContext and supplied to Cosolvent's Intelligence Slot at deployment time, alongside the vertical-specific system prompts.

---

## 6. Recommendation

No recommendation is made here. This document is intended to frame the decision for team discussion.

**The question for the team:**
Given that the CommonContext is currently an offline curation tool and Cosolvent is a live runtime, which transport mechanism best balances simplicity, reliability, and the curator's workflow?

---

## 7. Decision

> *(To be filled in after team discussion.)*

**Chosen option:**  
**Rationale:**  
**Date decided:**  
**Action items:**

