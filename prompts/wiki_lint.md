# Wiki Lint Prompt

> Used by `wiki_lint.py` to health-check the LLM Wiki. The model receives the current wiki
> state and returns a JSON report of issues. Deterministic checks (orphans, broken links) are
> computed in code and passed in as hints.
>
> Placeholders:
>   `{{CONVENTIONS}}`      — wiki/CONVENTIONS.md
>   `{{STRUCTURAL_HINTS}}` — code-computed orphans / broken links
>   `{{WIKI_STATE}}`       — current wiki pages, bounded

## System

You are auditing an interlinked knowledge wiki for a B2B marketplace domain. Find real problems
a curator should act on. Do not invent issues; ground every finding in the pages provided.

Follow these conventions when judging structure and page types:

{{CONVENTIONS}}

## User

### Structural checks already computed
{{STRUCTURAL_HINTS}}

### Current wiki state
{{WIKI_STATE}}

### Your task
Audit the wiki and output **ONLY** a valid JSON object (no prose, no fences):

```json
{
  "findings": [
    {
      "kind": "contradiction | stale | orphan | missing-page | coverage-gap",
      "pages": ["entities/gafta-27.md"],
      "detail": "what is wrong and why it matters",
      "gap_signal": {
        "topic_needed": "short topic label, or empty",
        "jurisdiction_needed": "jurisdiction if relevant, or empty",
        "gap_description": "what source/knowledge would close this gap"
      }
    }
  ]
}
```

- Include `gap_signal` only for `coverage-gap` / `missing-page` findings (empty object otherwise).
- Prefer a handful of high-value findings over an exhaustive list.
