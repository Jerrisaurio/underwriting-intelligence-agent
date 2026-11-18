## Context

Live runs with `gpt-4o-mini` (see proposal) showed the model asserting identity and industry without
verified findings, using 1 of 5 searches at T2, and varying between runs. The architecture already
verifies each finding's URL; the gap is that the *identity summary* is trusted as-is.

## Goals / Non-Goals

**Goals:** no conclusion from the web without a verified source; usable T2 depth; measurable cost,
depth and consistency per model; a data-backed model choice.

**Non-Goals:** fixing model non-determinism (measured and reported instead); a second LLM pass to
critique the first (cost); retrying searches until findings appear.

## Decisions

- **Verify identity in code, after URL verification.** `identity_verified = any(kept finding is
  confirmed)`. The model's `found_publicly` becomes a claim; the profile exposes the verified value.
  Alternative: ask the model to be stricter in the prompt → rejected as the only safeguard (prompts
  are not guarantees), kept as a complement.
- **ACTIVE_FLAG_VS_NEWS is medium and changes no rule.** Public news of a resolution is weaker than
  the internal compliance record; it raises a conflict for human verification. Alternative: lower
  the flag's effect → rejected (web never overrides internal data).
- **Per-category T2 instruction** in the request input (not the system instructions), so T1 stays
  cheap. Prompt version bumped so cached research is invalidated.
- **Evaluation records from the profile trace** (`web_search_calls`, tokens) and runs each company
  `--runs` times without cache; agreement = same `identity_verified`, industry and action across runs.
- **Model choice by comparison** on the same 13 cases with 2 runs each: verified identity rate,
  industry accuracy, searches used, adverse findings, agreement, tokens and latency.

## Risks / Trade-offs

- [Stricter identity lowers C_external for real companies with only uncertain findings] → accepted:
  neutral (0.5) is the honest value without a verified source.
- [More searches at T2 raise cost] → bounded by `max_tool_calls`; measured in the comparison.
- [Run-to-run variance remains] → reported per model; rules stay deterministic given the findings.

## Migration Plan

Schema 1.2: `WebResearch.identity_verified`, `ConflictType.ACTIVE_FLAG_VS_NEWS`; additive.
`PROMPT_VERSION` bump invalidates the cache.

## Open Questions

Prices per model are not configured; cost is reported as tokens and searches until they are.
