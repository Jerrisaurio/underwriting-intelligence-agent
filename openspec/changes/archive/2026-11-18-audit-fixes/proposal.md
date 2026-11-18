## Why

An audit of the implementation against every requirement of the challenge found gaps: the
literal example "coverage type implies one industry, the web suggests another" is not detected;
conflicts are surfaced but not *reasoned through*; 79% of deep (T2) web lookups are triggered
only by missing or inconsistent industry, which a T1 identity check already answers; the source
of the industry value is not traceable; and some documentation does not match what a reviewer
can run. These must be closed before submission.

## What Changes

- New conflict `COVERAGE_VS_WEB_INDUSTRY`: only unambiguous coverages (Agrícola, Ingeniería) that
  hold the majority of the client's premium, compared with the industry found on the web.
- Every conflict carries a `reasoning` field: three deterministic Spanish sentences (which source
  is more authoritative and why, what it implies for underwriting, what to verify).
- Depth policy: missing or name-inconsistent industry leads to T1, no longer to T2.
- `company_identity.industry_source` (`portfolio` / `web` / null): the web fills a missing
  industry, never overrides a recorded one; when both exist and differ the internal value stays
  and a conflict is raised.
- `docs/SCHEMA.md` names every field of the schema; README states that examples are fictitious
  and how to list valid names from the data.
- Continuous integration: GitHub Actions running ruff and pytest on every push.

## Capabilities

### New Capabilities
- `quality-gates`: automated lint and test checks on every push and pull request.

### Modified Capabilities
- `underwriting-profile`: conflict reasoning, coverage-vs-web industry conflict, industry source.
- `web-research`: depth policy no longer escalates to T2 for industry issues.

## Impact

- Code: `agent/conflicts.py`, `agent/pipeline.py`, `schema/profile.py`, `web/depth.py`, tests.
- Docs: `docs/SCHEMA.md`, `README.md`, `eval/REPORT.md` (depth distribution).
- New file: `.github/workflows/ci.yml`. No new runtime dependencies; no data in CI (tests use
  fictitious fixtures).
