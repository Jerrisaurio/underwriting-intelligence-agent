## 1. Schema

- [x] 1.1 Add `Conflict.reasoning`, `CompanyIdentity.industry_source`, `ConflictType.COVERAGE_VS_WEB_INDUSTRY`; bump `SCHEMA_VERSION` to 1.1
- [x] 1.2 Tests pass and ruff clean

## 2. Conflicts and industry

- [x] 2.1 Reasoning templates per conflict type (authority, implication, verification) applied to every conflict
- [x] 2.2 COVERAGE_VS_WEB_INDUSTRY: unambiguous coverage with > 50% of premium vs web industry
- [x] 2.3 Industry source: web fills a missing industry (no INDUSTRY_MISSING then), never overrides a recorded one
- [x] 2.4 Tests for reasoning, coverage conflict (positive, generic coverage, no web) and industry source
- [x] 2.5 Tests pass and ruff clean

## 3. Depth policy

- [x] 3.1 Missing / name-inconsistent industry leads to T1 with an explicit reason, not T2
- [x] 3.2 Test for the industry-only case; re-measure the depth distribution on the data
- [x] 3.3 Tests pass and ruff clean

## 4. Docs and CI

- [x] 4.1 `docs/SCHEMA.md`: every schema field named, new fields and conflict documented
- [x] 4.2 README: examples are fictitious; how to list valid names from the data
- [x] 4.3 `eval/REPORT.md`: depth distribution after the change
- [x] 4.4 `.github/workflows/ci.yml`: uv locked sync, ruff check, ruff format --check, pytest
- [x] 4.5 Tests pass and ruff clean; `openspec validate --all --strict`

## 5. Security review findings

- [x] 5.1 Web requests sent with `store=false` (provider must not retain responses) + test
- [x] 5.2 Depth policy uses the same disputed-claims share (≥ 25%) as rule R5d + test
- [x] 5.3 README security section
