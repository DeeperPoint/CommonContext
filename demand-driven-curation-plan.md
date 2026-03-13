# Proposal: Demand-Driven Curation (The "Pull" System)

## Concept Overview
The Knowledge Slot was originally conceived as a repository that sponsors populate proactively (the "Push" model). However, expecting sponsors to exhaustively document an entire global ecosystem upfront creates a massive barrier to adoption—the "Sponsor Cold Start" problem. 

The **Demand-Driven Curation** (or "Pull") system shifts this paradigm. It allows active market queries to identify exactly what knowledge has commercial value and is currently missing. When a user asks a question that the Knowledge Slot cannot answer, the system does two things:
1. **Fails gracefully** (often by falling back to external/unverified synthesis).
2. **Fires a Curatorial Pull Signal** to the sponsor, highlighting the specific knowledge gap that is actively obstructing a potential transaction.

## Architectural Additions to the Roadmap

To implement this in the `KnowledgeSlot` and `Cosolvent` architectures, the following elements need to be added to the roadmap:

### 1. Retrieval Monitoring & Gap Detection 
*(Affects `Cosolvent` runtime and `KnowledgeSlot` schema design)*
*   **Confidence Thresholds:** The RAG retrieval system must establish a confidence threshold. If a query yields results below this threshold, it triggers a "Knowledge Gap" event.
*   **LLM Self-Assessment:** The prompt configuration (Intelligence Slot) needs instructions forcing the LLM to explicitly declare when the provided context is insufficient to answer the query definitively.

### 2. External Fallback Synthesis (The Stopgap)
*(Affects `Cosolvent` Agent/Intelligence Slots)*
*   When a gap is detected, the system shouldn't just return an error. It should pivot to an external search tool (e.g., via the MCP Slot) to synthesize a provisional answer.
*   **UI/UX Requirement:** This external synthesis must be clearly visually delineated (e.g., marked as "Unverified External Synthesis") to protect the authoritative nature of the Knowledge Slot.

### 3. The Curatorial Pull Signal (The Sponsor UX)
*(Addresses Roadmap Open Question 5: "Sponsor curation UX")*
*   **Event Logging:** Gap events must be logged to a new table (e.g., `knowledge_gap_signals`), capturing:
    *   The raw user query.
    *   The inferred metadata scope (e.g., `region:buenos_aires`, `vertical:irish_music`).
    *   The context of the transaction (e.g., "Buyer in X querying requirements for Seller in Y").
*   **Sponsor Dashboard UI:** The admin interface needs a "Curation Queue" or "Demand Signals" view, sorting these gaps by frequency or transaction value at stake.

### 4. The Fulfillment Loop
*(Affects `KnowledgeSlot` curation workflow)*
*   When a sponsor acts on a Pull Signal and uploads new reference material, the system must link the new ingestion back to the original gap event.
*   **Proactive Notification:** The user whose query generated the pull signal should receive an asynchronous notification once the sponsor has fulfilled the gap, successfully unblocking their transaction.

## Proposed Updates to ROADMAP.md

To formalize this, I recommend the following additions to `ROADMAP.md`:

**Add to §2. Design Principles:**
*   Create a new principle: **2.8 — Demand-Driven Curation (Pull Signals)**. Explain that the library is progressively built not just through proactive ingestion, but actively guided by user queries that fall outside the current envelope, triggering signals for the sponsor to fill high-value gaps.

**Add to §4.1 — Deliverables:**
*   Add a deliverable: **Gap detection prompt** (Editable LLM prompt that instructs the model to declare missing context and format a pull signal).

**Add to §5 — Roadmap Phases:**
*   Under Phase 3 (Ingestion Preparation), add: *Define database schema for `knowledge_gap_signals`.*
*   Under Phase 4 (Integration Testing), add: *Test the "Curatorial Pull" loop: Intentionally query missing information, verify the fallback response, verify the generation of a curation signal, ingest the missing document, and verify the updated response.*

**Update §8 — Open Questions:**
*   Resolve or expand Question 5 (*"What does the admin workflow look like for a non-technical sponsor..."*) to explicitly include managing the Curatorial Pull Signal queue.  
