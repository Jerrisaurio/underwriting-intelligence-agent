import pytest

from uw_agent.resolution import EntityResolver, MatchType, ResolutionOutcome

R = ResolutionOutcome


@pytest.fixture(scope="module")
def resolver(repo):
    return EntityResolver.from_repository(repo, alias_file=None)


def test_unique_name_resolves(resolver):
    res = resolver.resolve("Soluciones Arcoíris S.A. de C.V.")
    assert (res.outcome, res.client_id) == (R.RESOLVED, "SOL")
    assert res.entity_confidence == 1.0


def test_trade_name_in_data_resolves(resolver):
    assert resolver.resolve("pdg").client_id == "PDG"


def test_homonym_with_dominant_leader_is_resolved_but_flagged(resolver):
    res = resolver.resolve("Tecnologías Arcoíris S.A. de C.V.")
    assert res.outcome is R.RESOLVED_WITH_AMBIGUITY
    assert res.client_id == "BIG"
    assert {c.client_id for c in res.candidates} >= {"BIG", "SMALL"}
    assert res.entity_confidence < 1.0


def test_homonyms_without_leader_are_ambiguous(resolver):
    res = resolver.resolve("Grupo Quimera S.A.")
    assert res.outcome is R.AMBIGUOUS
    assert res.client_id is None
    assert res.entity_confidence <= 0.4


def test_state_hint_disambiguates(resolver):
    res = resolver.resolve("Grupo Quimera S.A.", state="sonora")
    assert (res.outcome, res.client_id) == (R.RESOLVED, "N2")


def test_unknown_state_hint_is_ignored_and_reported(resolver):
    res = resolver.resolve("Grupo Quimera S.A.", state="Yucatán")
    assert res.outcome is R.AMBIGUOUS
    assert any("ignored" in n for n in res.notes)


def test_legal_form_family_separates_entities(resolver):
    # Same core as BIG/SMALL (S.A. de C.V.), but a different legal-form family: the
    # S.A. candidates drop below the ambiguity window, so this is not a homonym case.
    res = resolver.resolve("Tecnologías Arcoíris S.C.")
    assert (res.outcome, res.client_id) == (R.RESOLVED, "SC")
    assert res.candidates[0].legal_form_match is True
    assert any(c.legal_form_match is False for c in res.candidates[1:])


def test_truncated_portfolio_spelling_does_not_link_other_companies(resolver):
    # "Arcoíris S.A. de C.V." is a spelling of both BIG and SOL; it must not make a
    # query for Soluciones Arcoíris match Tecnologías Arcoíris.
    res = resolver.resolve("Soluciones Arcoíris S.A. de C.V.")
    assert {c.client_id for c in res.candidates} == {"SOL"}


def test_truncated_query_is_flagged(resolver):
    res = resolver.resolve("Arcoíris S.A. de C.V.")
    assert res.outcome in (R.RESOLVED_WITH_AMBIGUITY, R.AMBIGUOUS)
    assert {"BIG", "SOL"} <= {c.client_id for c in res.candidates}


@pytest.mark.parametrize("typo", ["Tecnologias Arcoirsi SA de CV", "Tecnologias Arcoiris SA de CV"])
def test_typos_resolve(resolver, typo):
    assert resolver.resolve(typo).client_id == "BIG"


def test_transposition_in_short_word(resolver):
    assert resolver.resolve("Grupo Qiumera S.A.", state="Jalisco").client_id == "N1"


def test_different_word_is_not_a_typo(resolver):
    # Whole-string similarity is 0.94, but "Modelo" and "Morelos" are different words.
    assert resolver.resolve("Constructora Modelo S.A. de C.V.").outcome is R.NOT_FOUND


def test_generic_partial_query_is_ambiguous(resolver):
    res = resolver.resolve("Arcoíris")
    assert res.outcome in (R.AMBIGUOUS, R.RESOLVED_WITH_AMBIGUITY)


def test_partial_query_with_single_match_resolves(resolver):
    res = resolver.resolve("Soluciones")
    assert (res.outcome, res.client_id) == (R.RESOLVED, "SOL")
    assert res.candidates[0].match_type is MatchType.PARTIAL


@pytest.mark.parametrize("bad", ["", "   ", "S.A. de C.V.", "x" * 300])
def test_invalid_inputs(resolver, bad):
    assert resolver.resolve(bad).outcome is R.INVALID_INPUT


def test_alias_table(repo, tmp_path):
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text(
        "aliases:\n"
        "  - {alias: 'Gulf Petroleum', target: 'Petrolera del Golfo S.A.', type: english_name}\n"
        "  - {alias: 'Ghost', target: 'Not In Portfolio', type: trade_name}\n",
        encoding="utf-8",
    )
    resolver = EntityResolver.from_repository(repo, alias_file=aliases)
    res = resolver.resolve("Gulf Petroleum")
    assert (res.client_id, res.candidates[0].match_type) == ("PDG", MatchType.ALIAS)
    assert resolver.resolve("Ghost").outcome is R.NOT_FOUND
