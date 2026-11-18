# profile-evaluation Specification

## Purpose
Evaluation of full profiles against verifiable facts and of web research on a hand-labelled
set. Implemented in `eval/run_profile_eval.py` and `eval/run_web_eval.py`.
## Requirements
### Requirement: Profile evaluation against verifiable facts
`eval/run_profile_eval.py` SHALL profile a seeded sample of clients (input = one of their recorded
spellings) and report watchlist recall, exactness of premium/claims aggregates against an
independent computation, schema validity, evidence-id validity, error rate, latency and cost per
lookup.

#### Scenario: Watchlist recall
- **WHEN** a sampled client has watchlist entries under its ClientId and the name resolves to it
- **THEN** every entry appears in `risk_flags` with `link = confirmed`, and recall is reported

#### Scenario: Invalid evidence
- **WHEN** a profile cites an evidence id that does not exist in the source data
- **THEN** the evaluation counts it as an evidence error

### Requirement: Web evaluation set
A hand-labelled set of real companies SHALL define expected public facts; its runner SHALL report
"not run" instead of failing when no API key is configured. When it runs, it SHALL accept the model
and the number of runs per company, and SHALL report per case and on average the web-search calls,
input and output tokens, triggered rules, and whether repeated runs agree on identity, industry and
recommended action.

#### Scenario: No key
- **WHEN** the web evaluation runs without `OPENAI_API_KEY`
- **THEN** it exits 0 and reports that the web set was not run

#### Scenario: Consistency across runs
- **WHEN** the evaluation runs with `--runs 2`
- **THEN** each case reports whether both runs agree on identity, industry and action, and the aggregate reports the agreement rate

