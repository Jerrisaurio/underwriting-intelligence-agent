"""Web research tests with a fake OpenAI client (no network, no key)."""

from datetime import date
from types import SimpleNamespace as NS

import httpx2 as httpx  # transport used by the installed openai SDK
import openai
import pytest

from tests.conftest import AS_OF
from uw_agent.agent import ProfilePipeline
from uw_agent.config import Settings
from uw_agent.infra.cache import CachedResearcher
from uw_agent.resolution import EntityResolver
from uw_agent.schema.profile import ConflictType, RecommendedAction, ResearchStatus
from uw_agent.web import ResearchRequest, build_researcher
from uw_agent.web.models import LLMFinding, LLMIdentity, LLMResearch
from uw_agent.web.openai_researcher import OpenAIWebResearcher

REQ = ResearchRequest(
    "Constructora Morelos S.A. de C.V.", "Puebla", "T2", ("Construcción", "Minería")
)


def finding(url, category="identity", stance="neutral", match="confirmed", published=None):
    return LLMFinding(
        claim="Texto.",
        url=url,
        source_title=None,
        published_date=published,
        risk_category=category,
        stance=stance,
        entity_match=match,
    )


def response(findings, sources, industry="Construcción", found=True):
    search = NS(type="web_search_call", action=NS(sources=[NS(type="url", url=u) for u in sources]))
    return NS(
        output=[search, search, NS(type="message", content=[])],
        output_parsed=LLMResearch(
            identity=LLMIdentity(
                found_publicly=found, description="Constructora.", industry=industry, state="Puebla"
            ),
            findings=findings,
        ),
        usage=NS(input_tokens=1000, output_tokens=200),
    )


class FakeClient:
    """Stands in for openai.OpenAI: records calls to responses.parse and replays a result."""

    def __init__(self, result):
        self._result = result
        self.calls = []
        self.responses = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def fake(result):
    return FakeClient(result)


def test_findings_must_cite_returned_sources():
    client = fake(
        response(
            [finding("https://www.example.mx/nota/"), finding("https://invented.com/x")],
            sources=["https://example.mx/nota"],
        )
    )
    out = OpenAIWebResearcher("model-x", client=client).research(REQ)
    assert out.status is ResearchStatus.DONE
    assert [f.url for f in out.findings] == ["https://www.example.mx/nota/"]
    assert out.dropped_unverified == 1
    assert out.usage.web_search_calls == 2 and out.usage.input_tokens == 1000
    call = client.calls[0]
    assert call["max_tool_calls"] == 5  # T2 budget
    assert call["include"] == ["web_search_call.action.sources"]
    assert call["store"] is False  # the provider must not retain the response
    # Data governance: only name, state, depth and the industry list are sent.
    assert "Constructora Morelos" in call["input"] and "premium" not in call["input"].lower()


def test_other_company_findings_are_dropped_and_industry_is_closed_list():
    client = fake(
        response(
            [finding("https://a.mx/1", match="different_company")],
            sources=["https://a.mx/1"],
            industry="Astronáutica",
        )
    )
    out = OpenAIWebResearcher("m", client=client).research(REQ)
    assert out.findings == [] and out.dropped_other_entity == 1
    assert out.identity.industry is None  # not in the closed list


def test_provider_error_becomes_failed_outcome():
    err = openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))
    out = OpenAIWebResearcher("m", client=fake(err)).research(REQ)
    assert out.status is ResearchStatus.FAILED and "APITimeoutError" in out.reason


def test_unparsable_output_is_failed():
    r = response([], [])
    r.output_parsed = None
    assert OpenAIWebResearcher("m", client=fake(r)).research(REQ).status is ResearchStatus.FAILED


def test_factory_without_credentials_is_unavailable():
    r = build_researcher(Settings(data_dir=".", as_of_date=date.today()))
    assert not r.available
    assert r.research(REQ).status is ResearchStatus.UNAVAILABLE
    assert "OPENAI_API_KEY" in r.research(REQ).reason


def test_cache_hit_costs_nothing(tmp_path):
    client = fake(response([finding("https://a.mx/1")], ["https://a.mx/1"]))
    cached = CachedResearcher(OpenAIWebResearcher("m", client=client), tmp_path / "c.sqlite", 7)
    first, second = cached.research(REQ), cached.research(REQ)
    assert len(client.calls) == 1
    assert not first.cache_hit and second.cache_hit
    assert second.usage.llm_calls == 0 and second.findings == first.findings


def test_corrupt_cache_is_bypassed(tmp_path):
    bad = tmp_path / "c.sqlite"
    bad.write_text("not a database")
    client = fake(response([], []))
    cached = CachedResearcher(OpenAIWebResearcher("m", client=client), bad, 7)
    assert cached.research(REQ).status is ResearchStatus.DONE


# ---------------------------------------------------------------- pipeline integration


def pipeline_with(repo, result, prices=True):
    settings = Settings(
        data_dir=".",
        as_of_date=AS_OF,
        price_input_per_mtok=1.0 if prices else None,
        price_output_per_mtok=4.0,
        price_per_web_search=0.01,
    )
    researcher = OpenAIWebResearcher("m", client=fake(result))
    return ProfilePipeline(
        repo,
        EntityResolver.from_repository(repo, alias_file=None),
        researcher=researcher,
        settings=settings,
    )


def test_resolved_flag_contradicted_by_news(repo):
    news = finding(
        "https://n.mx/1", category="litigation", stance="negative", published="2024-02-01"
    )
    p = pipeline_with(repo, response([news], ["https://n.mx/1"])).build(
        "Constructora Morelos S.A. de C.V.", as_of=AS_OF
    )
    assert p.public_information.status is ResearchStatus.DONE
    assert p.public_information.depth == "T2"  # it has a watchlist entry
    conflict = next(c for c in p.conflicts if c.type is ConflictType.WATCHLIST_STATUS_VS_NEWS)
    assert set(conflict.sources) == {"watchlist:W5", "web:1"}
    assert p.trace.cost_usd == pytest.approx(1000 / 1e6 * 1 + 200 / 1e6 * 4 + 2 * 0.01)


def test_unflagged_sanction_news_refers_but_never_declines(repo):
    news = finding("https://n.mx/2", category="sanction", stance="negative")
    p = pipeline_with(repo, response([news], ["https://n.mx/2"])).build(
        "Transportes Delta S.A. de C.V.", as_of=AS_OF
    )
    assert "R2c" in {r.rule_id for r in p.assessment.triggered_rules}
    assert p.assessment.recommended_action is RecommendedAction.REFER_TO_COMPLIANCE
    assert ConflictType.ADVERSE_MEDIA_NOT_IN_WATCHLIST in {c.type for c in p.conflicts}


def test_industry_mismatch_and_external_confidence(repo):
    p = pipeline_with(
        repo, response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Minería")
    ).build("Constructora Morelos S.A. de C.V.", as_of=AS_OF)
    assert ConflictType.INDUSTRY_WEB_MISMATCH in {c.type for c in p.conflicts}
    assert p.assessment.confidence.external == 0.8


def test_unpriced_run_reports_null_cost(repo):
    p = pipeline_with(repo, response([], []), prices=False).build(
        "Constructora Morelos S.A. de C.V.", as_of=AS_OF
    )
    assert p.trace.cost_usd is None and p.trace.input_tokens == 1000


def test_short_circuit_makes_no_call(repo):
    pipe = pipeline_with(repo, response([], []))
    p = pipe.build("PDG", as_of=AS_OF)
    assert p.public_information.status is ResearchStatus.SKIPPED
    assert pipe.researcher._client.calls == []


def test_web_failure_keeps_internal_profile(repo):
    err = openai.RateLimitError(
        "slow down",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )
    p = pipeline_with(repo, err).build("Transportes Delta S.A. de C.V.", as_of=AS_OF)
    assert p.public_information.status is ResearchStatus.FAILED
    assert p.claims_performance is not None
    assert any("Sin información pública" in g for g in p.data_gaps)


# ---------------------------------------------------------------- audit-fixes


def _types(profile):
    return {c.type for c in profile.conflicts}


def test_every_conflict_is_reasoned(repo):
    p = pipeline_with(
        repo, response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Minería")
    ).build("Constructora Morelos S.A. de C.V.", as_of=AS_OF)
    assert p.conflicts
    for c in p.conflicts:
        assert all(k in c.reasoning for k in ("Autoridad:", "Implicación:", "Verificar:"))


def test_coverage_vs_web_industry(repo):
    p = pipeline_with(
        repo,
        response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Servicios Financieros"),
    ).build("Agroindustrias Sol S.A.", as_of=AS_OF)
    conflict = next(c for c in p.conflicts if c.type is ConflictType.COVERAGE_VS_WEB_INDUSTRY)
    assert "Agrícola" in conflict.description and "web:1" in conflict.sources


def test_generic_coverage_implies_no_industry(repo):
    p = pipeline_with(
        repo, response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Minería")
    ).build("Servicios Flota S.C.", as_of=AS_OF)
    assert ConflictType.COVERAGE_VS_WEB_INDUSTRY not in _types(p)


def test_no_web_industry_no_coverage_conflict(repo):
    p = pipeline_with(repo, response([], [], industry=None)).build(
        "Agroindustrias Sol S.A.", as_of=AS_OF
    )
    assert ConflictType.COVERAGE_VS_WEB_INDUSTRY not in _types(p)


def test_web_fills_missing_industry(repo):
    p = pipeline_with(
        repo, response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Minería")
    ).build("Grupo Quimera S.A.", as_of=AS_OF, state="Jalisco")
    assert p.company_identity.industry == "Minería"
    assert p.company_identity.industry_source == "web"
    assert ConflictType.INDUSTRY_MISSING not in _types(p)
    assert "web:1" in p.company_identity.evidence


def test_web_never_overrides_recorded_industry(repo):
    p = pipeline_with(
        repo, response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Minería")
    ).build("Constructora Morelos S.A. de C.V.", as_of=AS_OF)
    assert p.company_identity.industry == "Construcción"
    assert p.company_identity.industry_source == "portfolio"
    assert ConflictType.INDUSTRY_WEB_MISMATCH in _types(p)


def test_industry_only_signal_stays_at_t1(repo):
    # Grupo Quimera (Jalisco): no flags, no claims, no recorded industry.
    pipe = pipeline_with(repo, response([], []))
    p = pipe.build("Grupo Quimera S.A.", as_of=AS_OF, state="Jalisco")
    assert p.public_information.depth == "T1"
    assert "Industria" in p.public_information.depth_reasons[0]
    assert pipe.researcher._client.calls[0]["max_tool_calls"] == 2


def test_disputed_claims_deepen_only_by_share():
    from uw_agent.schema.profile import ClaimsPerformance, Credibility, ProfileStatus
    from uw_agent.web import choose_depth

    def claims(disputed, total):
        return ClaimsPerformance(
            n_claims=total,
            n_excluded_after_as_of=0,
            incurred_mxn=0,
            reserved_registered_mxn=0,
            by_status={"en_disputa": disputed},
            oldest_open_claim_date=None,
            oldest_open_claim_age_days=None,
            client_loss_ratio=0.1,
            credibility=Credibility.CREDIBLE,
            by_year=[],
            top_claim_types={},
            evidence=[],
        )

    args = (ProfileStatus.COMPLETE, False, [], None, None)
    assert choose_depth(*args, claims(103, 821), [], 1e18)[0] == "T1"  # 12.5%: portfolio average
    assert choose_depth(*args, claims(2, 3), [], 1e18)[0] == "T2"


# ---------------------------------------------------------------- web-live-fixes


def test_unsupported_identity_is_not_verified():
    # Model claims the company exists and names an industry, but no finding supports it.
    client = fake(response([], [], industry="Construcción", found=True))
    out = OpenAIWebResearcher("m", client=client).research(REQ)
    assert out.identity.found_publicly is False
    assert out.identity.industry is None


def test_supported_identity_is_verified():
    client = fake(
        response([finding("https://a.mx/1")], ["https://a.mx/1"], industry="Construcción")
    )
    out = OpenAIWebResearcher("m", client=client).research(REQ)
    assert out.identity.found_publicly is True and out.identity.industry == "Construcción"


def test_uncertain_findings_do_not_verify_identity(repo):
    p = pipeline_with(
        repo,
        response(
            [finding("https://a.mx/1", match="uncertain")], ["https://a.mx/1"], industry="Minería"
        ),
    ).build("Grupo Quimera S.A.", as_of=AS_OF, state="Jalisco")
    assert p.public_information.identity_verified is False
    assert p.company_identity.industry is None  # not filled from an unverified identity
    assert not {ConflictType.INDUSTRY_WEB_MISMATCH, ConflictType.COVERAGE_VS_WEB_INDUSTRY} & _types(
        p
    )


def test_active_flag_vs_public_resolution(repo):
    # PDG has an active confirmed critical sanction (W1). In the pipeline R1 short-circuits the web
    # step, so the conflict detector is exercised directly with a public "resolution" finding.
    from uw_agent.agent.conflicts import detect_conflicts
    from uw_agent.resolution import EntityResolver
    from uw_agent.schema.profile import PublicFinding, ResearchStatus, WebResearch
    from uw_agent.tools import WatchlistScreener

    resolver = EntityResolver.from_repository(repo, alias_file=None)
    res = resolver.resolve("PDG")
    flags = WatchlistScreener(repo, resolver).screen(res)
    news = PublicFinding(
        id="web:1",
        claim="La sanción fue levantada.",
        url="https://n.mx/1",
        risk_category="sanction",
        stance="positive",
        entity_match="confirmed",
    )
    web = WebResearch(status=ResearchStatus.DONE, findings=[news], identity_verified=True)
    conflicts = detect_conflicts(res, None, flags, [], web)
    c = next(c for c in conflicts if c.type is ConflictType.ACTIVE_FLAG_VS_NEWS)
    assert set(c.sources) == {"watchlist:W1", "web:1"}
    assert "Verificar:" in c.reasoning


def test_active_flag_rule_still_fires_despite_news(repo):
    from uw_agent.agent.rules import evaluate_rules
    from uw_agent.resolution import EntityResolver
    from uw_agent.schema.profile import (
        ConfidenceLevel,
        ProfileStatus,
        PublicFinding,
        ResearchStatus,
        WebResearch,
    )
    from uw_agent.tools import WatchlistScreener

    resolver = EntityResolver.from_repository(repo, alias_file=None)
    flags = WatchlistScreener(repo, resolver).screen(resolver.resolve("PDG"))
    news = PublicFinding(
        id="web:1",
        claim="Sanción levantada.",
        url="https://n.mx/1",
        risk_category="sanction",
        stance="positive",
        entity_match="confirmed",
    )
    web = WebResearch(status=ResearchStatus.DONE, findings=[news], identity_verified=True)
    action, rules = evaluate_rules(
        ProfileStatus.COMPLETE, flags, None, [], ConfidenceLevel.MEDIUM, web
    )
    assert action is RecommendedAction.DECLINE and "R1" in {r.rule_id for r in rules}


def test_t2_request_names_the_five_categories():
    client = fake(response([], []))
    OpenAIWebResearcher("m", client=client).research(REQ)  # REQ is T2
    text = client.calls[0]["input"]
    for word in ("sanctions", "fraud", "litigation", "credit", "payment"):
        assert word in text
    t1 = ResearchRequest("X", None, "T1", ("Construcción",))
    OpenAIWebResearcher("m", client=client).research(t1)
    assert "Run one separate search" not in client.calls[1]["input"]
