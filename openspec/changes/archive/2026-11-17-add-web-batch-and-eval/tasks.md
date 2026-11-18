## 1. Web research

- [x] 1.1 `web/models.py`: request, structured output models, outcome with usage
- [x] 1.2 `web/depth.py`: T0/T1/T2 policy with reasons
- [x] 1.3 `web/openai_researcher.py`: Responses API call, source verification, identity filter, error mapping
- [x] 1.4 `web/base.py`: interface, unavailable researcher, factory from settings
- [x] 1.5 `infra/cache.py`: SQLite cache decorator with TTL and corruption fallback
- [x] 1.6 Web conflicts, rules R2c/R5f and C_external in the agent
- [x] 1.7 Pipeline integration and trace (tokens, calls, cost)
- [x] 1.8 Tests with a fake OpenAI client (success, unverified URL, different company, failure)

## 2. Batch

- [x] 2.1 Input readers (.txt / .csv) with validation
- [x] 2.2 Runner: thread pool, dedup, error isolation, ordered JSONL, resume, summary
- [x] 2.3 `uw-agent batch` command
- [x] 2.4 Tests

## 3. Evaluation and docs

- [x] 3.1 `eval/run_profile_eval.py` (watchlist recall, aggregates, schema, evidence, latency, cost)
- [x] 3.2 Hand-labelled web set `eval/web_cases.yaml` + runner (skips without key)
- [x] 3.3 `eval/REPORT.md` with results
- [x] 3.4 README: setup with key, batch usage, architecture, write-up
