---
source_url: null
title: "Manufacturing Capacity Subcontract Agreement — Standard Structure (Reference Guide)"
note: "AUTHORED REFERENCE — not a copy of any single vendor's template. Synthesizes commonly-recognized structural elements of a manufacturing subcontract/services agreement, cross-checked against multiple free-template providers (Contractbook, Business-in-a-Box, PandaDoc, eSign, Legal Templates) found via web search, without reproducing any one site's exact wording. This is legal-structure knowledge, not legal advice, and not a ready-to-sign document."
---

# Manufacturing Capacity Subcontract Agreement — Standard Structure

Once a capacity-exchange deal reaches the `deal_context` disclosure stage and both parties have agreed to proceed, the working document shifts from an NDA to a subcontract/services agreement covering the actual machining work. Common structural elements:

## 1. Parties, Effective Date, Term
Legal names, effective date, and whether the term is a single job, a time-boxed capacity rental (e.g., "second shift, 8 weeks"), or an ongoing arrangement.

## 2. Scope of Work
The specific deliverable: part description or drawing reference, quantity, tolerance requirements, material, and any required processes (heat treatment, coating, inspection). For a capacity-rental instrument rather than a spot purchase, scope is expressed as available machine-hours/shift-time rather than a finished-part count.

## 3. Specifications & Acceptance Criteria
Referenced drawings/CAD files, dimensional tolerances, surface finish requirements, and the inspection method that determines acceptance (CMM report, first-article inspection, statistical sampling plan).

## 4. Schedule & Delivery
Start date, milestones, delivery window, and what happens if either side misses a date — this is where a marketplace's `delivery_window` / availability-window matching data becomes contractual.

## 5. Price & Payment Terms
Rate structure (per-part, per-hour, or fixed price), currency, invoicing schedule, and payment terms (net 30/45/60 are common in manufacturing subcontracting). For capacity rental, the rate is typically $/machine-hour, sometimes with an operator-included premium.

## 6. Quality Requirements
Reference to the buyer's or industry's quality system requirements (e.g., "supplier shall maintain ISO 9001 certification" or "AS9100D for aerospace-designated work") and any customer-flow-down requirements the buyer is itself obligated to pass through.

## 7. Materials & Tooling Ownership
Who supplies raw material and special tooling/fixtures; who owns tooling built specifically for this job after the contract ends (a frequent negotiation point — the shop that built the fixture wants to keep it for future runs; the buyer who paid for it wants ownership).

## 8. Confidentiality
Either incorporates the prior NDA by reference or restates core confidentiality obligations directly.

## 9. Intellectual Property
Ownership of the finished part design (normally stays with the buyer) versus the machining process/programs used to produce it (normally stays with the shop) — this distinction matters more in subcontract manufacturing than in most services agreements.

## 10. Liability, Indemnification & Insurance
Liability caps (often tied to contract value), indemnification for defective work, and required insurance (general liability, and often product liability for aerospace/medical work) — this is also where cargo/equipment-in-transit insurance terms are referenced if the buyer's material or the shop's output is being shipped (see `cargo_insurance_overview.md`, `equipment_cargo_transit_insurance.md`).

## 11. Warranty
Workmanship warranty period and remedy (rework, replacement, refund) for parts that fail acceptance criteria after delivery.

## 12. Termination
For cause (quality failures, missed milestones) and for convenience (with notice), and what happens to work-in-progress and any advance payment on termination.

## 13. Dispute Resolution
Escalation path — direct negotiation, then mediation/arbitration, then courts — and governing law/jurisdiction.

## 14. Facilitator Roles (Marketplace-Specific)
Not part of a traditional two-party subcontract template, but relevant here: named roles for any third-party inspector, logistics/rigging provider, or trade-finance provider attached to the deal, and how their acceptance/sign-off gates the deal's completion.

## Why this matters for a capacity-exchange marketplace

This structure maps directly onto the deal-instrument vocabulary a platform like this needs: `spot_purchase` uses sections 1–6 and 9–13 in something close to their traditional form; `capacity_rental` reframes section 2 as machine-hours rather than parts and leans harder on section 4 (the availability-window matching this marketplace's `window_overlap` matching dimension is built for); facilitator roles (section 14) map onto `facilitator_slots` on the deal record.
