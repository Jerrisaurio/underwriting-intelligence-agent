## Context

Internal profile, schema and rules exist (`underwriting-profile`). No API key is configured in
the development environment, so the web path must be fully testable with fakes and must degrade
gracefully at runtime. Decisions: `docs/specs/add-web-batch-and-eval-draft.md`.

## Goals / Non-Goals

**Goals:** cited, verifiable public findings; bounded cost per lookup; reproducible batch runs;
measurable correctness.

**Non-Goals:** an LLM deciding the action or the confidence; scraping arbitrary pages; a
service/API deployment (the modular monolith keeps that option open).

## Decisions

- **Interface first.** `WebResearcher.research(request) -> ResearchOutcome`. Implementations:
  `OpenAIWebResearcher`, `UnavailableResearcher`, `CachedResearcher` (decorator). The pipeline
  depends on the interface only, so switching provider is one class.
- **One structured call per lookup.** `responses.parse` with the `web_search` tool,
  `max_tool_calls` = depth budget and a Pydantic `text_format`; sources requested through
  `include=["web_search_call.action.sources"]` and used to verify every finding URL.
- **The model classifies, rules decide.** The model returns findings with category, stance and
  entity match, and picks the industry from the portfolio's closed list; conflicts and actions
  are computed by code from those fields.
- **Cache as a decorator** keyed by provider/model/prompt version/name/state/depth, so a prompt
  change invalidates it automatically.
- **Batch with a thread pool**; each company in its own try/except; output written in input order
  to JSONL; summary computed from the written lines (so a resumed run reports totals correctly).

## Risks / Trade-offs

- Web quality depends on the provider's search; mitigated by source verification and identity
  classification, and by never letting web findings decline.
- Synthetic company names will mostly have no public footprint → C_external neutral by design.
- The web evaluation cannot run without a key; reported explicitly as not run.
- Model choice and prices are configuration, not code: availability and pricing change.
