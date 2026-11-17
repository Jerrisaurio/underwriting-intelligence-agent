"""Profile pipeline: a fixed, code-driven sequence (not an LLM loop).

    resolve → watchlist (mandatory) → history → related → [short-circuit?] → web research
            → conflicts → confidence → rules

Mandatory checks live in code so no model decision can skip them. R1 (confirmed critical
sanction/fraud) is decided before the web step and skips it: no amount of public information
would change a DECLINE, so the call would be pure cost. Every step is timed into ``trace``.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from uw_agent.agent.confidence import compute_confidence, external_evidence, internal_evidence
from uw_agent.agent.conflicts import detect_conflicts
from uw_agent.agent.rules import evaluate_rules, short_circuits
from uw_agent.config import Settings
from uw_agent.data.repository import DataRepository
from uw_agent.resolution import EntityResolver, ResolutionOutcome, ResolutionResult
from uw_agent.schema.profile import (
    Assessment,
    CandidateSummary,
    CompanyIdentity,
    ConfidenceBreakdown,
    ConfidenceLevel,
    ProfileStatus,
    QueryInfo,
    RecommendedAction,
    ResearchStatus,
    RiskFlag,
    Trace,
    TraceStep,
    TriggeredRule,
    UnderwritingProfile,
    WebResearch,
)
from uw_agent.tools import RelatedEntities, WatchlistScreener, summarize_history
from uw_agent.web import ResearchRequest, UnavailableResearcher, WebResearcher, choose_depth
from uw_agent.web.models import ResearchOutcome, Usage

STATUS_BY_OUTCOME = {
    ResolutionOutcome.RESOLVED: ProfileStatus.COMPLETE,
    ResolutionOutcome.RESOLVED_WITH_AMBIGUITY: ProfileStatus.COMPLETE,
    ResolutionOutcome.AMBIGUOUS: ProfileStatus.AMBIGUOUS,
    ResolutionOutcome.NOT_FOUND: ProfileStatus.NOT_FOUND,
    ResolutionOutcome.INVALID_INPUT: ProfileStatus.INVALID_INPUT,
}
ACTION_LABELS_ES = {
    RecommendedAction.DECLINE: "Declinar",
    RecommendedAction.REFER_TO_COMPLIANCE: "Turnar a Cumplimiento",
    RecommendedAction.NEEDS_CLARIFICATION: "Aclarar la identidad de la empresa",
    RecommendedAction.INSUFFICIENT_INFORMATION: "Información insuficiente",
    RecommendedAction.REFER_TO_SENIOR_UNDERWRITER: "Turnar a suscriptor senior",
    RecommendedAction.PROCEED_WITH_CONDITIONS: "Proceder con condiciones",
    RecommendedAction.PROCEED_STANDARD: "Proceder en condiciones estándar",
}


class ProfilePipeline:
    def __init__(
        self,
        repo: DataRepository,
        resolver: EntityResolver | None = None,
        researcher: WebResearcher | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repo = repo
        self.resolver = resolver or EntityResolver.from_repository(repo)
        self.watchlist = WatchlistScreener(repo, self.resolver)
        self.related = RelatedEntities(repo)
        self.researcher = researcher or UnavailableResearcher("Investigación web no configurada")
        self.settings = settings
        p = repo.portfolio
        self._industries = tuple(sorted(i for i in p["industry"].unique() if i))
        self._sum_insured_p90 = float(p.groupby("ClientId")["sum_insured"].sum().quantile(0.9))

    def build(self, name: str, as_of: date, state: str | None = None) -> UnderwritingProfile:
        started = time.perf_counter()
        trace = Trace()

        @contextmanager
        def step(label: str):
            t0 = time.perf_counter()
            detail: list[str] = []
            yield detail
            trace.steps.append(
                TraceStep(
                    step=label,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    detail="; ".join(detail),
                )
            )

        query = QueryInfo(
            input_name=name,
            state_hint=state,
            as_of_date=as_of,
            generated_at=datetime.now().astimezone(),
        )

        with step("entity_resolution") as d:
            res = self.resolver.resolve(name, state=state)
            d.append(f"{res.outcome.value} {res.client_id or ''}".strip())
        status = STATUS_BY_OUTCOME[res.outcome]

        flags: list[RiskFlag] = []
        if res.candidates:
            with step("watchlist_screening") as d:
                flags = self.watchlist.screen(res)
                d.append(f"{len(flags)} entrada(s) vinculadas")

        identity = history = None
        related = []
        if res.client_id:
            with step("client_history") as d:
                identity = self._identity(res.client_id)
                history = summarize_history(self.repo, res.client_id, as_of)
                d.append(
                    f"{history.relationship.n_policies} pólizas, {history.claims.n_claims} siniestros"
                )
            with step("related_entities") as d:
                related = self.related.for_client(res.client_id)
                d.append(f"{len(related)} relacionada(s)")

        anomalies = history.anomalies if history else []
        internal_conflicts = detect_conflicts(res, identity, flags, anomalies)
        short_circuit = short_circuits(flags)
        if short_circuit:
            trace.short_circuit = "R1: bandera crítica confirmada; se omite la investigación web"

        with step("web_research") as d:
            web, usage = self._research(
                status, short_circuit, flags, identity, history, internal_conflicts, res, state
            )
            d.append(f"{web.status.value} {web.depth} {len(web.findings)} hallazgo(s)")

        with step("assessment") as d:
            conflicts = detect_conflicts(res, identity, flags, anomalies, web)
            internal = internal_evidence(
                history.relationship if history else None,
                history.claims if history else None,
                bool(identity and identity.industry),
                self._history_years(history, as_of),
            )
            confidence = compute_confidence(
                res.entity_confidence, internal, conflicts, external_evidence(web)
            )
            action, rules = evaluate_rules(
                status, flags, history.claims if history else None, conflicts, confidence.level, web
            )
            d.append(f"{action.value}, confianza {confidence.level.value}")

        gaps = list(history.data_gaps) if history else []
        if status is ProfileStatus.NOT_FOUND:
            gaps.append("La empresa no existe en el portafolio, siniestros ni watchlist internos")
        if web.status in (ResearchStatus.UNAVAILABLE, ResearchStatus.FAILED):
            gaps.append(f"Sin información pública: {web.reason}")

        self._fill_usage(trace, usage)
        trace.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return UnderwritingProfile(
            status=status,
            query=query,
            entity_resolution=res,
            candidates_summary=self._candidate_summaries(res, flags),
            company_identity=identity,
            relationship=history.relationship if history else None,
            claims_performance=history.claims if history else None,
            risk_flags=flags,
            related_entities=related,
            public_information=web,
            conflicts=conflicts,
            data_gaps=gaps,
            assessment=Assessment(
                recommended_action=action,
                triggered_rules=rules,
                confidence=confidence,
                summary=self._summary(status, res, identity, history, flags, action, as_of, web),
            ),
            trace=trace,
        )

    def error_profile(
        self, name: str, as_of: date, state: str | None, exc: Exception
    ) -> UnderwritingProfile:
        """Batch mode: one company failing must not stop the run; it gets an ERROR line."""
        message = f"{type(exc).__name__}: {exc}"[:300]
        return UnderwritingProfile(
            status=ProfileStatus.ERROR,
            query=QueryInfo(
                input_name=name,
                state_hint=state,
                as_of_date=as_of,
                generated_at=datetime.now().astimezone(),
            ),
            data_gaps=[f"Error al construir el perfil: {message}"],
            assessment=Assessment(
                recommended_action=RecommendedAction.INSUFFICIENT_INFORMATION,
                triggered_rules=[
                    TriggeredRule(
                        rule_id="R0",
                        action=RecommendedAction.INSUFFICIENT_INFORMATION,
                        explanation="El perfil no pudo construirse por un error del sistema.",
                    )
                ],
                confidence=ConfidenceBreakdown(
                    overall=0,
                    level=ConfidenceLevel.LOW,
                    entity=0,
                    internal=0,
                    external=0,
                    conflict_penalty=0,
                    capped=False,
                ),
                summary=f"Error al construir el perfil de '{name}': {message}",
            ),
        )

    # ------------------------------------------------------------------ web step

    def _research(
        self, status, short_circuit, flags, identity, history, conflicts, res, state
    ) -> tuple[WebResearch, Usage | None]:
        # Returns the usage instead of storing it on self: the pipeline is shared by batch
        # worker threads and must stay stateless per call.
        depth, reasons = choose_depth(
            status,
            short_circuit,
            flags,
            identity,
            history.relationship if history else None,
            history.claims if history else None,
            conflicts,
            self._sum_insured_p90,
        )
        base = {
            "depth": depth,
            "depth_reasons": reasons,
            "provider": self.researcher.provider,
            "model": self.researcher.model,
        }
        if depth == "T0":
            return WebResearch(status=ResearchStatus.SKIPPED, reason=reasons[0], **base), None
        if not self.researcher.available:
            outcome = self.researcher.research(
                ResearchRequest(res.query, state, depth, self._industries)
            )
            return WebResearch(status=outcome.status, reason=outcome.reason, **base), None

        request = ResearchRequest(
            name=identity.legal_name if identity else res.query,
            state=identity.state if identity else state,
            depth=depth,
            industries=self._industries,
        )
        outcome: ResearchOutcome = self.researcher.research(request)
        web = WebResearch(
            status=outcome.status,
            reason=outcome.reason,
            identity=outcome.identity,
            findings=outcome.findings,
            dropped_unverified=outcome.dropped_unverified,
            dropped_other_entity=outcome.dropped_other_entity,
            cache_hit=outcome.cache_hit,
            **base,
        )
        return web, outcome.usage

    def _fill_usage(self, trace: Trace, u: Usage | None) -> None:
        if u is None:
            return
        trace.llm_calls = u.llm_calls
        trace.web_search_calls = u.web_search_calls
        trace.input_tokens = u.input_tokens
        trace.output_tokens = u.output_tokens
        trace.cost_usd = self._cost(u)

    def _cost(self, u) -> float | None:
        if u.llm_calls == 0:
            return 0.0
        s = self.settings
        prices = (
            (s.price_input_per_mtok, s.price_output_per_mtok, s.price_per_web_search)
            if s
            else (None,) * 3
        )
        if any(p is None for p in prices):
            return None  # never guess a price
        p_in, p_out, p_search = prices
        return round(
            u.input_tokens / 1e6 * p_in
            + u.output_tokens / 1e6 * p_out
            + u.web_search_calls * p_search,
            6,
        )

    # ------------------------------------------------------------------ helpers

    def _identity(self, client_id: str) -> CompanyIdentity:
        info = self.repo.clients.loc[client_id]
        pol = self.repo.policies_for(client_id)
        return CompanyIdentity(
            client_id=client_id,
            legal_name=info["display_name"],
            name_variants=sorted(pol["client_name"].unique().tolist()),
            state=info["state"],
            municipality=info["municipality"],
            industry=info["industry"] or None,
            evidence=[f"portfolio:{p}" for p in pol["policy_id"].head(20)],
        )

    @staticmethod
    def _history_years(history, as_of: date) -> float:
        if history is None or history.relationship.first_policy_start is None:
            return 0.0
        start = pd.Timestamp(history.relationship.first_policy_start)
        return (pd.Timestamp(as_of) - start).days / 365.25

    def _candidate_summaries(
        self, res: ResolutionResult, flags: list[RiskFlag]
    ) -> list[CandidateSummary]:
        if res.outcome not in (
            ResolutionOutcome.AMBIGUOUS,
            ResolutionOutcome.RESOLVED_WITH_AMBIGUITY,
        ):
            return []
        active: dict[str, list[str]] = {}
        for f in flags:
            if f.is_active:
                active.setdefault(f.linked_client_id, []).append(f"{f.flag_type}/{f.severity}")
        return [
            CandidateSummary(
                client_id=c.client_id,
                display_name=c.display_name,
                state=c.state,
                n_policies=c.n_policies,
                score=c.score,
                active_flags=active.get(c.client_id, []),
            )
            for c in res.candidates
        ]

    @staticmethod
    def _summary(status, res, identity, history, flags, action, as_of, web) -> str:
        label = ACTION_LABELS_ES[action]
        if status is ProfileStatus.INVALID_INPUT:
            return f"Entrada inválida: {'; '.join(res.notes)}."
        if status is ProfileStatus.NOT_FOUND:
            return f"No se encontró '{res.query}' en las bases internas. Recomendación: {label}."
        if status is ProfileStatus.AMBIGUOUS:
            return (
                f"'{res.query}' coincide con {res.n_candidates_total} clientes sin uno dominante; "
                f"se requiere precisar estado o razón social. Recomendación: {label}."
            )
        rel, clm = history.relationship, history.claims
        n_active_flags = sum(f.is_active for f in flags)
        credibility = "creíble" if clm.credibility.value == "credible" else "poco creíble"
        web_part = (
            f" Fuentes públicas: {len(web.findings)} hallazgo(s)."
            if web.status is ResearchStatus.DONE
            else ""
        )
        return (
            f"{identity.legal_name} ({identity.state}): {rel.n_policies} pólizas, "
            f"{rel.n_active_policies} vigentes al {as_of.isoformat()}; siniestralidad "
            f"{clm.client_loss_ratio:.0%} ({credibility}); {n_active_flags} bandera(s) activa(s) "
            f"en watchlist.{web_part} Recomendación: {label}."
        )
