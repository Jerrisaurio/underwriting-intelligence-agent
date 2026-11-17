## Context

The data layer and the entity resolver exist and are evaluated (99% accuracy, 0% false
resolutions on 1,030 cases). The challenge requires a structured, auditable profile with a
documented schema, confidence and recommended actions. Detailed decisions and unhappy paths are
in `docs/specs/add-internal-tools-and-schema-draft.md`.

## Goals / Non-Goals

**Goals:**
- A complete internal-only profile per company, every fact traceable to source rows.
- Deterministic rules for conflicts, action and confidence, each explained in Spanish.
- A schema that already reserves the web/narrative sections so the next change only fills them.

**Non-Goals:**
- Web research, LLM narrative, external confidence (next change: `add-web-research`).
- Batch mode, caching and cost tracking (`add-batch-and-observability`).

## Decisions

- **Tools are plain functions over `DataRepository`** returning Pydantic models. They are pure and
  deterministic, so they are unit-testable and reusable by a future LLM tool-calling layer
  without changes.
- **Orchestration is code, not an LLM loop.** `agent/pipeline.py` fixes the order: resolve →
  watchlist (mandatory) → portfolio → claims → related entities → conflicts → action →
  confidence. Mandatory checks cannot be skipped by a model decision.
- **Evidence ids** (`portfolio:POL-…`, `claims:CLM-…`, `watchlist:WL-…`) are attached to facts;
  the profile keeps an evidence registry so an underwriter can trace any number.
- **Rules as data:** the action matrix lives in one module with rule ids (R1…); triggered rules are
  listed in the profile. Thresholds live in a config dataclass, not inline.
- **Confidence formula** (see draft) is explicit and penalises conflicts; `C_external` is a neutral
  0.5 until web research exists.
- **Reference date** defaults to today and is always echoed; metrics exclude data after it.

## Risks / Trade-offs

- With `as_of` = today most policies are expired → many "no active policy" gaps. Mitigated by
  `--as-of` and by stating it in the profile.
- Written (not earned) premium biases the loss ratio for 2-year policies → documented limitation.
- Name-based business-word check for industry is heuristic → reported as `medium` conflict only,
  never decisive.
- Confidence weights are a starting point, not calibrated against outcomes (no ground truth for
  underwriting decisions exists in the data).
