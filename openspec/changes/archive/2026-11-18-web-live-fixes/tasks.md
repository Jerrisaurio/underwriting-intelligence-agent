## 1. Verified identity

- [x] 1.1 Schema 1.2: `WebResearch.identity_verified`, `ConflictType.ACTIVE_FLAG_VS_NEWS` (+ reasoning template)
- [x] 1.2 Researcher: identity verified only with a confirmed kept finding; otherwise found_publicly false, industry discarded
- [x] 1.3 Pipeline/conflicts: industry fill and industry conflicts only with verified identity
- [x] 1.4 Tests: unsupported identity, supported identity, no industry conflict when unverified
- [x] 1.5 Tests pass and ruff clean

## 2. Active flag vs news and T2 depth

- [x] 2.1 ACTIVE_FLAG_VS_NEWS conflict (rules unchanged)
- [x] 2.2 T2 request names the five risk categories; bump PROMPT_VERSION
- [x] 2.3 Tests: conflict with rule still firing; T2 input content
- [x] 2.4 Tests pass and ruff clean

## 3. Evaluation and model comparison

- [x] 3.1 `run_web_eval.py`: `--model`, `--runs`, per-case searches/tokens/rules, agreement, averages; output per model
- [x] 3.2 Run the web evaluation with gpt-4o-mini and gpt-5.4-mini (2 runs each)
- [x] 3.3 `eval/REPORT.md`: live web results and model comparison; `docs/OPEN_ITEMS.md`: close the watchlist review item
- [x] 3.4 `docs/SCHEMA.md`: identity_verified and ACTIVE_FLAG_VS_NEWS
- [x] 3.5 Tests pass, ruff clean, `openspec validate --all --strict`
