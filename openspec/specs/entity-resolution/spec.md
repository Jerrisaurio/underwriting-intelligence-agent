# entity-resolution Specification

## Purpose

Map a free-text company name to a portfolio ClientId, robust to legal-name, trade-name,
abbreviation and typographic variants, and honest about ambiguity.
Implemented in `src/uw_agent/resolution/`; evaluated by `eval/run_resolution_eval.py`.

## Requirements

### Requirement: Deterministic normalization
The system SHALL normalize names by removing accents, case and punctuation, expanding known
abbreviations (GF, ORG, CORP, CIA) and splitting the trailing legal form into a family
(SA, SAPI, SAB, SRL, SC, SCL, PLC) and a "de C.V." flag. Equal inputs SHALL always produce equal
results.

#### Scenario: Legal-form spellings
- **WHEN** the input is "Tecnologías Bajío SACV" or "TECNOLOGÍAS BAJÍO S.A. DE C.V."
- **THEN** both normalize to core "TECNOLOGIAS BAJIO", family "SA", with "de C.V."

### Requirement: Layered matching
The system SHALL match the normalized core against every spelling a ClientId has used, in this
order of strength: exact, compact (spaces ignored), alias table, partial (all query words present),
fuzzy. Fuzzy matches SHALL require every word to resemble its counterpart (ratio ≥ 0.80, or one
Damerau-Levenshtein edit on words of 4+ letters).

#### Scenario: Typo in the distinctive word
- **WHEN** the input is "Tecnologías Nvoa S.A. de C.V." and the client is "Tecnologías Nova S.A. de C.V."
- **THEN** the client is matched by fuzzy match

#### Scenario: Different word is not a typo
- **WHEN** the input is "Constructora Modelo S.A. de C.V." and only "Constructora Morelos S.A. de C.V." exists
- **THEN** the result is NOT_FOUND

#### Scenario: Truncated portfolio spelling
- **WHEN** "Bajío S.A. de C.V." is a recorded spelling of both Tecnologías Bajío and Soluciones Bajío
- **AND** the input is "Soluciones Bajío S.A. de C.V."
- **THEN** Tecnologías Bajío is not a candidate

### Requirement: Legal form separates entities
The system SHALL penalise candidates whose legal-form family differs from the query's and SHALL
treat a different "de C.V." suffix within the same family as a weak signal only.

#### Scenario: Same core, different family
- **WHEN** the input is "Tecnologías Bajío S.C." and S.C. and S.A. de C.V. clients exist
- **THEN** the S.C. client is RESOLVED and the S.A. ones are listed with `legal_form_match = false`

### Requirement: Honest handling of homonyms
The system SHALL return RESOLVED only when a single ClientId matches; RESOLVED_WITH_AMBIGUITY when
several ClientIds tie and the leader holds at least 70% of their policies; AMBIGUOUS otherwise,
including generic partial queries matching several different names. Ambiguous outcomes SHALL list
the candidates and SHALL cap entity confidence at 0.4.

#### Scenario: Dominant homonym
- **WHEN** a name belongs to a client with 50 policies and another with 2
- **THEN** the outcome is RESOLVED_WITH_AMBIGUITY for the 50-policy client and both are candidates

#### Scenario: No dominant homonym
- **WHEN** a name belongs to two clients with 3 policies each
- **THEN** the outcome is AMBIGUOUS with no client_id

#### Scenario: State hint
- **WHEN** the same ambiguous name is resolved with `--state Sonora`
- **THEN** the Sonora client is RESOLVED

### Requirement: Input validation
The system SHALL return INVALID_INPUT for empty input, input longer than 200 characters, or input
that contains only a legal form.

#### Scenario: Only a legal form
- **WHEN** the input is "S.A. de C.V."
- **THEN** the outcome is INVALID_INPUT

### Requirement: Measured quality
The resolver SHALL be evaluated on a generated case set covering exact, typographic, legal-form,
truncated, real-company, typo, alias, state-hint, not-found and invalid inputs, reporting accuracy,
false-resolution rate, candidate recall and confidence calibration.

#### Scenario: No confident wrong answers
- **WHEN** the evaluation runs
- **THEN** the false-resolution rate (wrong ClientId without an ambiguity flag) is 0%
