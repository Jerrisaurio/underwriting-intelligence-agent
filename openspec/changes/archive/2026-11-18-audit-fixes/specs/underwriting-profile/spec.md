## MODIFIED Requirements

### Requirement: Explicit conflicts
The system SHALL report conflicts ENTITY_AMBIGUITY, WATCHLIST_NOTE_VS_STATUS,
FLAG_PREDATES_RELATIONSHIP, WATCHLIST_LINKED_BY_NAME_ONLY, INDUSTRY_MISSING,
INDUSTRY_NAME_MISMATCH and DATA_ANOMALY with severity, sources and a Spanish description, and
SHALL NOT resolve them silently. Every conflict SHALL also carry a `reasoning` text in Spanish that
states which source is more authoritative and why, what the conflict implies for underwriting,
and what to verify.

#### Scenario: Business word contradicts industry
- **WHEN** the client is "Agroindustrias X" and its industry is "Hotelería y Turismo"
- **THEN** an INDUSTRY_NAME_MISMATCH conflict of severity medium is reported

#### Scenario: Conflict is reasoned, not only described
- **WHEN** any conflict is reported
- **THEN** its `reasoning` is non-empty and names the authoritative source, the implication and a verification step

## ADDED Requirements

### Requirement: Coverage versus web industry
The system SHALL report COVERAGE_VS_WEB_INDUSTRY (medium) when an unambiguous coverage holds more
than half of the client's written premium and the industry found on the web is not consistent
with it. Unambiguous coverages are Agrícola (Agricultura, Alimentos y Bebidas) and Ingeniería
(Construcción, Inmobiliaria, Minería, Manufactura). Coverages any business buys (fleet, liability,
fire, miscellaneous, cargo) SHALL NOT imply an industry.

#### Scenario: Agricultural coverage, technology company on the web
- **WHEN** 80% of the client's premium is Agrícola and the web industry is "Tecnología"
- **THEN** a COVERAGE_VS_WEB_INDUSTRY conflict cites the client and the web findings

#### Scenario: Generic coverage implies nothing
- **WHEN** 100% of the premium is Flotilla Vehicular and the web industry is "Tecnología"
- **THEN** no COVERAGE_VS_WEB_INDUSTRY conflict is reported

#### Scenario: No web industry
- **WHEN** web research did not run or returned no industry
- **THEN** no COVERAGE_VS_WEB_INDUSTRY conflict is reported

### Requirement: Industry source
The profile SHALL state the source of `company_identity.industry` in `industry_source`: `portfolio`
when recorded internally (kept even if the web disagrees, with a conflict), `web` when the
portfolio has none and research found one, null otherwise. The web SHALL NOT override a recorded
industry.

#### Scenario: Web fills a gap
- **WHEN** the portfolio has no industry and the web identity industry is "Minería"
- **THEN** industry is "Minería" with `industry_source = "web"` and no INDUSTRY_MISSING conflict

#### Scenario: Web disagrees with the portfolio
- **WHEN** the portfolio says "Construcción" and the web says "Minería"
- **THEN** industry stays "Construcción" with `industry_source = "portfolio"` and INDUSTRY_WEB_MISMATCH is reported
