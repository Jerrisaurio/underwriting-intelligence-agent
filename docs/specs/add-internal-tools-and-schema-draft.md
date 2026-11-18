# Draft: add-internal-tools-and-schema

Status: approved by the user on 2026-11-17 (requirements review, all open questions closed).
Source of truth for the OpenSpec change `add-internal-tools-and-schema`.

## Goal

Produce a complete, auditable underwriting profile from the **internal** databases only
(portfolio, claims, watchlist), with a documented schema, rule-based recommended action and
confidence, exposed through `uw-agent profile "<name>"`. Web research and LLM narrative are
out of scope (next change); the schema already reserves their sections.

## Decisions (closed questions)

| # | Topic | Decision |
|---|---|---|
| 1 | Reference date | Default `as_of_date` = today; overridable with `--as-of` / `UW_AS_OF_DATE`. Always echoed in the profile. A `data_gaps` entry is added when the client has no active policy. |
| 2 | Client loss ratio | Σ incurred / Σ written premium over the full history, plus a breakdown by policy start year. Documented limitation: written, not earned, premium. |
| 3 | Credibility | Loss ratio is `credible` only with ≥ 3 policies **and** ≥ 2 years of history (first policy start to as_of). Otherwise `credibility: low` and it triggers no rule. |
| 4 | Watchlist matching | `confirmed`: ClientId of the chosen client. `possible`: other ClientIds inside the resolver ambiguity window, plus name-only matches (exact normalized core + family, or alias) for watchlist ClientIds absent from the portfolio (ClientIds absent from the portfolio). Never fuzzy against the watchlist. |
| 5 | Resolved flags | Shown, never trigger rules. If the note contradicts the status → conflict `WATCHLIST_NOTE_VS_STATUS` → `REFER_TO_SENIOR_UNDERWRITER`. |
| 6 | Action matrix | See "Recommended action". `possible` flags cap at `REFER_TO_COMPLIANCE`, never `DECLINE`. |
| 7 | Short-circuit | Active critical `sancion_regulatoria` (confirmed) → `DECLINE`; internal summaries are still computed; only web research is skipped (relevant from the next change). |
| 8 | Industry conflicts | Only `INDUSTRY_MISSING` and `INDUSTRY_NAME_MISMATCH` (explicit business word in the name contradicts the industry). Industry vs coverage vs web is deferred to the web change. |
| 9 | Related entities | Included: curated YAML of corporate groups / historical names (real companies only). Shown, never used by rules. |
| 10 | Ambiguous / not found | AMBIGUOUS → `status: AMBIGUOUS`, candidates with mini-summary (state, policies, active flags), action `NEEDS_CLARIFICATION`. NOT_FOUND → empty profile, `INSUFFICIENT_INFORMATION`. |
| 11 | Language | Field names in English; source values verbatim (Spanish); agent-generated text (notes, conflicts, rule explanations) in Spanish. |
| 12 | Exit codes | `0` a profile was produced (any status); `2` invalid input; `1` system failure (missing/corrupt data). |

## Happy path

1. Resolve the name (existing `EntityResolver`).
2. Watchlist lookup over the chosen client and the candidates (decision 4).
3. Portfolio summary for the chosen ClientId at `as_of_date`.
4. Claims summary for the chosen ClientId (claims after `as_of_date` excluded).
5. Related entities lookup.
6. Conflict detection (rules below).
7. Recommended action (matrix, precedence) and confidence (formula below).
8. Emit the `UnderwritingProfile` JSON; every fact carries evidence ids.

## Recommended action

Precedence (first match wins):

0. `INSUFFICIENT_INFORMATION` (R0): invalid input.
1. `DECLINE`: confirmed active flag with severity `crítico` and type `sancion_regulatoria` or `investigacion_fraude`.
2. `REFER_TO_COMPLIANCE`: confirmed active `sancion_regulatoria` / `investigacion_fraude` (non-critical) or `persona_politicamente_expuesta` (any); any `possible` active flag of those types.
3. `NEEDS_CLARIFICATION`: resolution AMBIGUOUS.
4. `INSUFFICIENT_INFORMATION`: NOT_FOUND, or overall confidence `LOW`.
5. `REFER_TO_SENIOR_UNDERWRITER`: confirmed active `pago_incumplido` critical; `litigio_activo` / `riesgo_crediticio` high; credible LR > 1.0; ≥ 2 claims `en_disputa` that are also ≥ 25% of the client's claims (amended during implementation: an absolute count does not scale to large clients); any conflict of severity `high`.
6. `PROCEED_WITH_CONDITIONS`: other confirmed active flags (`pago_incumplido` high/medium/low, `litigio_activo` / `riesgo_crediticio` medium/low); credible LR in (0.7, 1.0]; any `possible` active flag of other types.
7. `PROCEED_STANDARD`: none of the above.

Each triggered rule is reported with an id and a Spanish explanation.

## Confidence

`overall = C_entity × (0.7·C_internal + 0.3·C_external) − Σ penalties`, clipped to [0, 1].

- `C_entity`: resolver `entity_confidence`.
- `C_internal`: 0.4·min(years_history/4, 1) + 0.3·[credible LR] + 0.15·[industry present] + 0.15·[≥ 1 active policy].
- `C_external`: 0.5 (neutral) in this change: no web source yet.
- Penalties: 0.15 per `high` conflict, 0.07 per `medium`; `ENTITY_AMBIGUITY` carries no penalty (already in `C_entity`).
- Cap: if `C_entity` < 0.6, overall ≤ 0.4.
- Levels: HIGH ≥ 0.75, MEDIUM [0.5, 0.75), LOW < 0.5.

## Conflicts (this change)

| Type | Severity | Trigger |
|---|---|---|
| `ENTITY_AMBIGUITY` | medium | resolution RESOLVED_WITH_AMBIGUITY |
| `WATCHLIST_NOTE_VS_STATUS` | high | resolved flag whose note describes an ongoing situation |
| `FLAG_PREDATES_RELATIONSHIP` | low | flag_date < first policy start |
| `WATCHLIST_LINKED_BY_NAME_ONLY` | medium | flag linked by name (watchlist ClientId not in portfolio) |
| `INDUSTRY_MISSING` | low | no industry for the client |
| `INDUSTRY_NAME_MISMATCH` | medium | business word in name contradicts industry |
| `DATA_ANOMALY` | low | claims after as_of, unparseable values |

All conflicts are listed with sources, a Spanish description and `resolution: unresolved` (this
change resolves none automatically).

## Unhappy paths

| Case | Behaviour |
|---|---|
| Data file or column missing | `DataSchemaError`, clear message, exit 1 |
| Unparseable value in a client's rows | Row excluded from metrics, reported in `data_gaps` / `DATA_ANOMALY` |
| Claims after `as_of_date` | Excluded from metrics, `DATA_ANOMALY` |
| Client without claims | LR = 0 with its credibility, never "no data" |
| Client without active policy | `data_gaps` entry, profile still produced |
| Invalid input (empty, only legal form, too long) | `status: INVALID_INPUT`, exit 2 |
| AMBIGUOUS | candidates + mini-summaries, `NEEDS_CLARIFICATION`, exit 0 |
| NOT_FOUND | empty profile, `INSUFFICIENT_INFORMATION`, exit 0 |
| Invalid `--as-of` | CLI error, exit 2 |

## Out of scope (next changes)

Web research, LLM narrative, external confidence, batch mode, caching, cost tracking, profile-level
evaluation report.
