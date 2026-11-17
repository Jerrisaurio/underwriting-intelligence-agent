from pathlib import Path

import pytest

from tests.conftest import AS_OF
from uw_agent.resolution import EntityResolver
from uw_agent.schema.profile import Credibility, LinkMethod, WatchlistLink
from uw_agent.tools import RelatedEntities, WatchlistScreener, summarize_history


@pytest.fixture(scope="module")
def resolver(repo):
    return EntityResolver.from_repository(repo, alias_file=None)


@pytest.fixture(scope="module")
def screener(repo, resolver):
    return WatchlistScreener(repo, resolver)


def _links(flags):
    return {f.watchlist_id: (f.link, f.link_method, f.linked_client_id) for f in flags}


def test_confirmed_flag_and_name_only_link(screener, resolver):
    flags = screener.screen(resolver.resolve("Pemex"))
    assert _links(flags) == {
        "W1": (WatchlistLink.CONFIRMED, LinkMethod.CLIENT_ID, "PMX"),
        "W2": (WatchlistLink.POSSIBLE, LinkMethod.NAME, "PMX"),
    }


def test_homonym_flag_is_possible_not_confirmed(screener, resolver):
    res = resolver.resolve("Tecnologías Bajío S.A. de C.V.")
    assert res.client_id == "BIG"
    assert _links(screener.screen(res)) == {
        "W4": (WatchlistLink.POSSIBLE, LinkMethod.HOMONYM_CANDIDATE, "SMALL")
    }


def test_ambiguous_name_screens_all_candidates(screener, resolver):
    flags = screener.screen(resolver.resolve("Grupo Nova S.A."))
    assert _links(flags) == {"W3": (WatchlistLink.POSSIBLE, LinkMethod.HOMONYM_CANDIDATE, "N2")}


def test_note_contradicting_resolved_status_is_marked(screener, resolver):
    (flag,) = screener.screen(resolver.resolve("Constructora Morelos S.A. de C.V."))
    assert flag.status == "resuelto" and flag.note_contradicts_status


def test_history_loss_ratio_credible_and_future_claim_excluded(repo):
    h = summarize_history(repo, "LOSS", AS_OF)
    assert h.relationship.n_policies == 6
    assert h.claims.n_claims == 3
    assert h.claims.n_excluded_after_as_of == 1
    assert h.claims.client_loss_ratio == pytest.approx(7000 / 6000, abs=1e-4)
    assert h.claims.credibility is Credibility.CREDIBLE
    assert any("posterior" in d for d, _ in h.anomalies)
    assert set(h.relationship.evidence) == {f"portfolio:LOSS-{i}" for i in range(6)}


def test_thin_history_is_not_credible(repo):
    h = summarize_history(repo, "THIN", AS_OF)
    assert h.claims.client_loss_ratio == pytest.approx(1.6)
    assert h.claims.credibility is Credibility.LOW


def test_client_without_claims_has_zero_loss_ratio(repo):
    h = summarize_history(repo, "N1", AS_OF)
    assert h.claims.n_claims == 0 and h.claims.client_loss_ratio == 0.0


def test_no_active_policy_is_a_data_gap(repo):
    h = summarize_history(repo, "SMALL", AS_OF)  # 2 policies of 1 year from 2021
    assert h.relationship.n_active_policies == 0
    assert any("Sin pólizas vigentes" in g for g in h.data_gaps)


def test_policies_after_as_of_are_ignored(repo):
    h = summarize_history(repo, "THIN", AS_OF.replace(year=2023))
    assert h.relationship.n_policies == 0


def test_related_entities(repo, tmp_path: Path):
    path = tmp_path / "related.yaml"
    path.write_text(
        "groups:\n  - group: HSBC México\n    relation: former_name\n"
        "    members: ['HSBC México S.A.', 'BITAL SA', 'Missing Co']\n",
        encoding="utf-8",
    )
    related = RelatedEntities(repo, path).for_client("HSBC")
    assert [(r.name, r.client_ids) for r in related] == [
        ("BITAL SA", ["BITAL"]),
        ("Missing Co", []),
    ]
    assert RelatedEntities(repo, path).for_client("PMX") == []
