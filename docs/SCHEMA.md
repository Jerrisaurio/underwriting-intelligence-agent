# Underwriting profile schema (v1.1)

`uw-agent profile "<name>"` prints one `UnderwritingProfile` as JSON. The machine-readable
JSON Schema is printed by `uw-agent schema`; the Pydantic source is
`src/uw_agent/schema/profile.py`.

Conventions:
- Field names are English. Values copied from the source data stay verbatim (Spanish), e.g.
  `flag_type: "pago_incumplido"`. Text written by the agent (descriptions, explanations,
  `summary`) is Spanish, for Mexican underwriters.
- **Evidence ids** point at source rows: `portfolio:<policy_id>`, `claims:<claim_id>`,
  `watchlist:<watchlist_id>`, `portfolio:client:<ClientId>`. Any number in the profile can be
  traced back to the rows it was computed from.
- Amounts are MXN as recorded (no inflation or FX adjustment).

## Top level

| Field | Meaning |
|---|---|
| `schema_version` | Version of this schema. |
| `status` | `COMPLETE` one client profiled (ambiguity may still be flagged) · `AMBIGUOUS` several clients match, none dominates: only candidates are returned · `NOT_FOUND` no internal match · `INVALID_INPUT` · `ERROR` unexpected failure (batch mode). |
| `query` | `input_name`, `state_hint`, `as_of_date` (reference date for "active" and for excluding later data), `generated_at`. |
| `entity_resolution` | Full resolver output: `outcome`, `client_id`, `entity_confidence`, `dominance`, `margin_to_next`, `normalized_core` and `normalized_legal_family` (the query after normalization), `candidates` (top 10: `client_id`, `display_name`, `state`, `municipality`, `n_policies`, `score`, `match_type` = exact / compact / partial / fuzzy / alias, `matched_variant` = the portfolio spelling that matched, `legal_form_match` = true / false / null when either side has no legal form), `n_candidates_total`, `notes`. |
| `candidates_summary` | When the name is ambiguous: per candidate `client_id`, `display_name`, `state`, `n_policies`, `score`, `active_flags`. Lets the underwriter pick the right company. |
| `company_identity` | `client_id`, `legal_name` (most frequent spelling), `name_variants` (all spellings in the portfolio), `state`, `municipality`, `industry`, `industry_source` (`portfolio` when recorded internally; `web` when the portfolio has none and web research found one, never overriding a recorded value; null when unknown), `evidence`. |
| `relationship` | Portfolio at `as_of_date` (see below). |
| `claims_performance` | Claims history (see below). |
| `risk_flags` | Watchlist entries linked to the profile (see below). |
| `related_entities` | Corporate-group / historical-name links from a curated table: `name`, `relation` (`same_group` / `former_name`), `group`, `client_ids` (portfolio ClientIds of that entity, empty if not a client), `note`. Context only: never used by the action rules. |
| `public_information` | Web research (see below). |
| `conflicts` | Contradictions and weaknesses in the evidence (see below). |
| `data_gaps` | Missing information that limits the assessment, in Spanish (e.g. "Sin pólizas vigentes al 2026-11-17"). |
| `assessment` | `recommended_action`, `triggered_rules` (`rule_id`, `action`, `explanation`), `confidence` (breakdown below), `summary` (Spanish). |
| `trace` | `steps` (`step`, `duration_ms`, `detail`), `short_circuit` reason, `llm_calls`, `web_search_calls`, `input_tokens`, `output_tokens`, `cost_usd` (null when an external call was made but prices are not configured: never guessed), `duration_ms`. |

## `relationship`

| Field | Meaning |
|---|---|
| `n_policies` | Policies started on or before `as_of_date`. |
| `n_active_policies` | Policies with `start <= as_of_date < end`. |
| `total_premium_mxn`, `total_sum_insured_mxn` | Over `n_policies`. |
| `active_premium_mxn`, `active_sum_insured_mxn` | Over active policies: current exposure. |
| `first_policy_start`, `last_policy_end` | Length of the relationship. |
| `coverage_mix` | Per coverage: `coverage_type`, `n_policies`, `n_active`, `premium_mxn`, `sum_insured_mxn`. |
| `evidence` | Every policy id summed. |

## `claims_performance`

| Field | Meaning |
|---|---|
| `n_claims` | Claims on in-scope policies dated on or before `as_of_date`. |
| `n_excluded_after_as_of` | Claims dated after `as_of_date` (excluded, also reported as `DATA_ANOMALY`). |
| `incurred_mxn` | Σ incurred loss. |
| `reserved_registered_mxn` | Σ `reserved_mxn` **as recorded**. In the source, closed claims keep a reserve of 1.0–1.4× incurred, so this is not outstanding exposure. |
| `by_status` | Counts of `cerrado` / `abierto` / `en_disputa`. |
| `oldest_open_claim_date`, `oldest_open_claim_age_days` | Oldest open or disputed claim. |
| `client_loss_ratio` | Σ incurred / Σ **written** premium (no earned premium in the source; 2-year policies are not pro-rated). 0.0 when there are no claims. |
| `credibility` | `credible` with ≥ 3 policies and ≥ 2 years of history; else `low`. A `low` loss ratio never triggers an action rule. |
| `by_year` | Per `policy_start_year`: `n_policies`, `premium_mxn`, `n_claims`, `incurred_mxn`, `loss_ratio`. |
| `top_claim_types` | Five most frequent claim types. |

## `risk_flags[]`

| Field | Meaning |
|---|---|
| `watchlist_id`, `watchlist_client_id`, `watchlist_client_name` | Source entry. |
| `flag_type`, `severity`, `status`, `flag_date`, `resolved_date`, `notes` | Verbatim from the watchlist. |
| `link` | `confirmed`: same ClientId as the profiled client. `possible`: needs human review. |
| `link_method` | `client_id` · `homonym_candidate` (another ClientId the resolver could not rule out) · `name` (watchlist ClientId absent from the portfolio; linked by exact normalized name or curated alias, never fuzzy). |
| `linked_client_id` | Portfolio ClientId the entry was linked to. |
| `note_contradicts_status` | `true` when a `resuelto` entry's note describes an ongoing situation. |
| `predates_relationship` | `true` when the flag is older than the client's first policy. |

## `public_information`

| Field | Meaning |
|---|---|
| `status`, `reason` | `done` · `skipped` (depth T0) · `unavailable` (no `OPENAI_API_KEY` / `UW_OPENAI_MODEL`) · `failed` (provider error after retries; the internal profile is kept). |
| `depth`, `depth_reasons` | `T0` none · `T1` identity check (≤ 2 searches; also when the only question is a missing or name-inconsistent industry) · `T2` adverse-media search (≤ 5 searches; only with risk signals: watchlist entry, credible loss ratio > 80%, top-decile sum insured, ≥ 2 disputed claims, no internal match), with the signals that chose it. |
| `provider`, `model` | Implementation used (`openai`) and the configured model. |
| `identity` | `found_publicly`, `description`, `industry` (only a value of the portfolio's industry list, else null), `state`. |
| `findings` | `id` (`web:n`, used as evidence id), `claim` (Spanish), `url`, `source_title`, `published_date`, `risk_category` (identity, sanction, fraud, litigation, credit, payment, operations, other), `stance` (negative / neutral / positive), `entity_match` (`confirmed` / `uncertain`). |
| `dropped_unverified` | Findings discarded because their URL was not among the sources the search tool returned (invented or unverifiable sources). |
| `dropped_other_entity` | Findings discarded because they described a different company with a similar name. |
| `cache_hit` | Research reused from the cache (cost 0). |

Only the company name, state and depth are sent to the provider: no premiums, claims or
watchlist content.

## `conflicts[]`

Each conflict has `id`, `type`, `severity` (`low` / `medium` / `high`), Spanish `description`,
`sources` (evidence ids), `reasoning` (Spanish, three parts: *Autoridad* (which source is
more authoritative and why), *Implicación* (what it means for underwriting), *Verificar* (what to
check), deterministic per conflict type) and `resolution` (always `unresolved`: the agent surfaces
conflicts, it does not settle them).

| Type | Severity | Raised when |
|---|---|---|
| `ENTITY_AMBIGUITY` | medium | Other ClientIds match the name; the dominant one was profiled. |
| `WATCHLIST_NOTE_VS_STATUS` | high (confirmed) / medium (possible) | A resolved entry's note says the case is ongoing. |
| `FLAG_PREDATES_RELATIONSHIP` | low | A confirmed flag is older than the first policy. |
| `WATCHLIST_LINKED_BY_NAME_ONLY` | medium | Watchlist ClientId not in the portfolio; linked by name. |
| `INDUSTRY_MISSING` | low | No industry recorded. |
| `INDUSTRY_NAME_MISMATCH` | medium | The name states a line of business (Agroindustrias, Constructora, Transportes, Inmobiliaria, Tecnologías) inconsistent with the recorded industry. |
| `DATA_ANOMALY` | low | Unreadable values or claims after `as_of_date`, excluded from metrics. |
| `WATCHLIST_STATUS_VS_NEWS` | high | A confirmed flag is `resuelto`, but a confirmed negative web finding of the same risk category is dated after the resolution. |
| `INDUSTRY_WEB_MISMATCH` | medium | The web industry (closed list) differs from the recorded one. |
| `COVERAGE_VS_WEB_INDUSTRY` | medium | An unambiguous coverage holds > 50% of the written premium (Agrícola → Agricultura / Alimentos y Bebidas; Ingeniería → Construcción / Inmobiliaria / Minería / Manufactura) and the web industry is not consistent with it. Generic coverages (fleet, liability, fire, cargo, miscellaneous) imply no industry. |
| `ADVERSE_MEDIA_NOT_IN_WATCHLIST` | medium | Confirmed negative sanction / fraud / litigation / credit / payment finding with no confirmed watchlist flag of that type. |

## `assessment.confidence`

Computed by rules, never reported by a language model:

```
overall = C_entity × (0.7 · C_internal + 0.3 · C_external) − Σ penalties      (clipped to [0, 1])
```

| Component | Definition |
|---|---|
| `overall`, `level` | The final score in [0, 1] and its level (below). |
| `entity` (C_entity) | Resolver confidence: name similarity, reduced by the dominance share when homonyms exist (×0.9), ≤ 0.4 when ambiguous. |
| `internal` (C_internal) | 0.4 · min(years of history / 4, 1) + 0.3 · [credible loss ratio] + 0.15 · [industry known] + 0.15 · [≥ 1 active policy]. |
| `external` (C_external) | 0.8 when a web finding confirms the company's identity; 0.3 when research only found a *different* company; 0.5 (neutral) otherwise, including no public footprint, skipped, unavailable or failed research. Absence of web evidence is not negative evidence: most private SMEs have none. |
| `conflict_penalty` | 0.15 per `high`, 0.07 per `medium` conflict. `ENTITY_AMBIGUITY` is excluded (already in C_entity). |
| `capped` | If C_entity < 0.6, overall is capped at 0.4: a detailed profile of possibly the wrong company must not look trustworthy. |
| `level` | `HIGH` ≥ 0.75 · `MEDIUM` ≥ 0.5 · `LOW` < 0.5. |

The weights are a reasoned starting point, not fitted: the data contains no ground truth for
underwriting outcomes to calibrate them against.

## `assessment.recommended_action`

All rules are evaluated and listed in `triggered_rules` (`rule_id`, `action`, Spanish
`explanation`); the recommended action is the one with the highest precedence.

| Precedence | Action | Rules |
|---|---|---|
| 1 | `DECLINE` | **R1** confirmed active `sancion_regulatoria` or `investigacion_fraude` with severity `crítico`. Short-circuits web research. |
| 2 | `REFER_TO_COMPLIANCE` | **R2** confirmed active sanction/fraud (non-critical) or PEP. **R2b** *possible* active sanction/fraud/PEP. **R2c** confirmed web finding of sanction/fraud not in the watchlist. |
| 3 | `NEEDS_CLARIFICATION` | **R3** name is ambiguous (no dominant client). |
| 4 | `INSUFFICIENT_INFORMATION` | **R0** invalid input. **R4a** not found. **R4b** confidence `LOW`. |
| 5 | `REFER_TO_SENIOR_UNDERWRITER` | **R5a** confirmed active `pago_incumplido` critical. **R5b** confirmed active `litigio_activo` / `riesgo_crediticio` high. **R5c** credible loss ratio > 100%. **R5d** ≥ 2 disputed claims that are ≥ 25% of the client's claims. **R5e** any `high` conflict. **R5f** confirmed adverse web finding (litigation / credit / payment) not in the watchlist. |
| 6 | `PROCEED_WITH_CONDITIONS` | **R6a** other confirmed active flags (e.g. `pago_incumplido` medium: settle before renewal). **R6b** other *possible* active flags. **R6c** credible loss ratio in (70%, 100%]. |
| 7 | `PROCEED_STANDARD` | **R7** nothing above fired. |

Resolved flags are shown but never trigger rules, unless their note contradicts the status
(→ `WATCHLIST_NOTE_VS_STATUS`, high → R5e). `possible` flags never produce `DECLINE`: a human
must confirm the entity first. Web findings never produce `DECLINE` either: internal data is
the authority; the web can only escalate to a human.
