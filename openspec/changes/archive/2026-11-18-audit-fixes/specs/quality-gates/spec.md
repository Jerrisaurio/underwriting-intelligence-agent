## ADDED Requirements

### Requirement: Automated checks on every push
The repository SHALL run lint (ruff check and format check) and the unit tests (pytest) on every
push and pull request, using the locked environment and without access to the source data or
any credential.

#### Scenario: Push to develop
- **WHEN** a commit is pushed to any branch
- **THEN** the CI workflow installs the locked environment, runs ruff and pytest, and fails the run if either fails

#### Scenario: No data in CI
- **WHEN** the workflow runs
- **THEN** no CSV, dataset or API key is required (tests use fictitious fixtures)
