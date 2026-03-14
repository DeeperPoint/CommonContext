<!-- Copyright (c) 2026 Mustafa Uzumeri. All rights reserved. -->

# DECISION-003: Facilitator Subtype Strategy

> **Status:** Open — awaiting team discussion  
> **Date:** 2026-03-14  
> **Author:** Mustafa Uzumeri  
> **Extracted from:** DECISION-000 §3 / §9, Question 3

---

## 1. Problem

The Knowledge Slot domain schema for grain trading identifies **9 distinct facilitator subtypes**: broker, shipping agent, insurance broker, superintendent, analyst, fumigator, trade finance provider, customs broker, and legal counsel.

Each plays a different role in the transaction lifecycle. A superintendent inspects cargo quality; a customs broker handles export documentation; an insurance broker arranges marine coverage. Their capabilities, GAFTA registrations, and relevant contract clauses are distinct.

However, Cosolvent's current `ParticipantType` model is flat — one entry per type with a `slug`, `name`, `role`, and `permissions`. The MVP roadmap (Conflict C3) limits participant types to 3 (supply, demand, facilitator).

**The question:** Should facilitator subtypes have distinct permission sets and participant types, or should they be modeled as profile data within a single "facilitator" type?

---

## 2. Options

### Option A — Separate Participant Types (11 total)

Create a distinct `ParticipantType` for each facilitator subtype: `superintendent`, `broker`, `insurance_broker`, etc. Each gets its own permission set.

| Participant Type | Role | Permissions |
|-----------------|------|-------------|
| Seller | supply | Create listings, upload quality docs |
| Buyer | demand | Search, express interest, make offers |
| Broker | facilitator | View both sides, propose introductions |
| Superintendent | facilitator | Access quality docs, submit inspection reports |
| Insurance Broker | facilitator | View shipment details, attach policies |
| *(6 more...)* | facilitator | *(role-specific)* |

**Pros:**
- Cleanest model — each role has exactly the permissions it needs
- Enables fine-grained access control (superintendent sees quality data but not pricing)
- Maps directly to the domain schema

**Cons:**
- Requires relaxing Conflict C3 significantly (3 → 11 types)
- More complex admin setup for each vertical deployment
- May be over-engineered for MVP

### Option B — Single Facilitator Type with `service_type` Profile Field

Keep 3 participant types (supply, demand, facilitator). Model subtypes as a `multi_select` profile field on the facilitator type, with allowed values drawn from the domain schema.

| Participant Type | Role | Profile Field |
|-----------------|------|---------------|
| Seller | supply | — |
| Buyer | demand | — |
| Facilitator | facilitator | `service_type: [superintendent, analyst]` |

**Pros:**
- Works within the 3-type MVP limit
- Simple to implement — no framework changes needed
- Subtypes are vertical-specific data, not framework concerns

**Cons:**
- All facilitators share one permission set (a broker sees the same data as a superintendent)
- Cannot enforce role-specific access controls without additional logic
- The `service_type` field is doing architectural work that the type system should handle

### Option C — Grouped Facilitator Types (5–6 total)

Create grouped types that cluster related subtypes: `logistics_facilitator` (shipping agent, customs broker), `quality_facilitator` (superintendent, analyst, fumigator), `financial_facilitator` (insurance broker, trade finance), `legal_facilitator` (legal counsel), `commercial_facilitator` (broker).

**Pros:**
- Middle ground — fewer types than Option A, more specificity than Option B
- Permission groups align with functional boundaries (quality vs. financial vs. logistics)

**Cons:**
- Still requires relaxing C3 (3 → 5–6 types)
- Groupings are somewhat arbitrary and may not generalize across verticals
- A superintendent and an analyst may need different permissions even within the "quality" group

---

## 3. Cross-Vertical Considerations

The supply/demand/facilitator model maps cleanly to bilateral exchange markets (grain trading, manufacturing, defense procurement). It is more awkward for:

- **Service markets** (mental health: "supply" of therapy is a stretch)
- **Data markets** (both sides supply and consume)
- **Multi-sided markets** (three or more distinct participant categories)

Option B is the most portable across verticals because subtypes stay in profile data. Options A and C build vertical-specific knowledge into the type system.

---

## 4. Recommendation from DECISION-000

DECISION-000 §3 recommended **Option B for Phase 1** (works within 3-type limit), with migration to **Option A later** when the framework matures and C3 is relaxed. The `service_type` field values would be drawn from each vertical's domain schema.

---

## 5. Decision

> *(To be filled in after team discussion.)*

**Chosen option:**  
**Rationale:**  
**Date decided:**  
**Action items:**
