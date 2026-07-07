# Wiki Conventions

> This file tells the LLM (Sonnet 5) **how to maintain this wiki**. It is read on every
> ingest and lint run. The wiki is an LLM-maintained, interlinked knowledge base that sits
> between the raw source documents (`../inputs/`, converted to `../outputs/*.md`) and the two
> artifacts CommonContext produces: the **domain schema** and the **reference library**.
>
> **You (the LLM) own every file under `wiki/`. Humans read it; you write it.**

---

## 1. What the wiki is for

- **Compile knowledge once, keep it current.** When a new source arrives, do not just summarize
  it in isolation — *integrate* it into the existing pages, updating cross-references and noting
  where new information confirms or contradicts what is already recorded.
- The wiki is the synthesized layer that later feeds (a) domain-schema synthesis and (b) the
  embedded reference library used by the marketplace's Q&A.

## 2. Page taxonomy

Pages are grouped into typed folders. The concrete set is **derived from the domain schema**
(`../schemas/*_schema.yaml`) — one page *type* per entity class in that schema — plus a few
generic types. Typical types:

| Folder | `type:` | Holds one page per… |
|---|---|---|
| `entities/` | `entity` | Named real-world thing (an organization, contract, standard, grade, corridor, product class) |
| `concepts/` | `concept` | Domain concept, rule, process, or trade parameter |
| `participant-roles/` | `participant-role` | Marketplace role (supply / demand / facilitator subtype) |
| `sources/` | `source` | One summary page per ingested document (its provenance + key takeaways) |

> When a vertical needs sharper buckets (e.g. grain → `contracts/`, `grades/`, `corridors/`,
> `standards/`; machinery → `machine-types/`, `certifications/`), create those folders and use a
> matching `type:` slug. Prefer specific types when the schema implies them.

## 3. Page format

Every page is markdown with **YAML frontmatter**, then a body that uses `[[wikilinks]]`.

```markdown
---
title: GAFTA Contract No. 27
type: entity
summary: Standard CIF/C&F contract for Canadian & US grain in bulk, tale quale.
sources: [27_2025]            # provenance stems (the outputs/<stem>.md this came from)
updated: 2026-07-07
---

Body in markdown. Link related pages with double brackets, e.g. this contract governs
[[wheat-hrw]] shipments along the [[corridor-canada-philippines]] and incorporates
[[gafta-arbitration-rules]] by reference.

## Key terms
- ...

## Provenance
Derived from [[source-27_2025]]. Any factual claim should be traceable to a source page.
```

Rules:
- `title`, `type`, `summary` (one line), `sources` (list of provenance stems), `updated` (ISO date)
  are **required** in frontmatter.
- Use `[[wikilink]]` where the link target is the page's path **without** the folder or `.md`
  (e.g. `[[gafta-27]]` for `entities/gafta-27.md`). Create the target page if it doesn't exist yet.
- Keep claims sourced. When two sources disagree, record **both** and add a `> **Conflict:**` note.

## 4. index.md and log.md

- **`index.md`** is a generated catalog — every page listed with its one-line `summary`, grouped by
  type. It is **rebuilt automatically** from page frontmatter after each ingest; do not hand-write it.
- **`log.md`** is append-only. Each ingest/lint adds one line, prefixed for grep-ability:
  `## [YYYY-MM-DD] ingest | <source title>` followed by a short note of what changed.

## 5. Ingest rules (what to do with a new source)

1. Read the new document and the current `index.md` (+ any pages it implies).
2. Decide which pages to **create** or **update**. One source typically touches several pages.
3. For each affected page, return its **complete** new body (not a diff) plus frontmatter fields.
4. Add/refresh `[[wikilinks]]` between related pages.
5. Prefer integrating into existing pages over creating near-duplicates.
6. Always create/refresh a `sources/<stem>.md` page summarizing the document itself.

## 6. Lint rules (periodic health-check)

Report: contradictions between pages, stale claims a newer source supersedes, **orphan** pages
(no inbound `[[links]]`), important concepts mentioned but lacking their own page, and coverage
gaps worth curating. Emit gaps as pull-signals for the curation dashboard.
