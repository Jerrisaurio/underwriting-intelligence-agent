"""Profile pipeline: a fixed, code-driven sequence (not an LLM loop).

    resolve → watchlist (mandatory) → history → related → conflicts → confidence → rules

Mandatory checks live in code so no model decision can skip them. Every step is timed into
``trace``. The web-research step (next change) slots in after ``related`` and is skipped when
a short-circuit rule (R1: confirmed critical sanction/fraud) has fired.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from uw_agent.agent.confidence import compute_confidence, internal_evidence
from uw_agent.agent.conflicts import detect_conflicts
from uw_agent.agent.rules import evaluate_rules
from uw_agent.data.repository import DataRepository
from uw_agent.resolution import EntityResolver, ResolutionOutcome, ResolutionResult
from uw_agent.schema.profile import (
    Assessment,
    CandidateSummary,
    CompanyIdentity,
    ProfileStatus,
    QueryInfo,
    RecommendedAction,
    RiskFlag,
    Trace,
    TraceStep,
    UnderwritingProfile,
    WebResearch,
)
from uw_agent.tools import RelatedEntities, WatchlistScreener, summarize_history

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
    def __init__(self, repo: DataRepository, resolver: EntityResolver | None = None) -> None:
        self.repo = repo
        self.resolver = resolver or EntityResolver.from_repository(repo)
        self.watchlist = WatchlistScreener(repo, self.resolver)
        self.related = RelatedEntities(repo)

    def build(self, name: str, as_of: date, state: str | None = None) -> UnderwritingProfile:
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

        with step("assessment") as d:
            conflicts = detect_conflicts(res, identity, flags, history.anomalies if history else [])
            history_years = self._history_years(history, as_of)
            internal = internal_evidence(
                history.relationship if history else None,
                history.claims if history else None,
                bool(identity and identity.industry),
                history_years,
            )
            confidence = compute_confidence(res.entity_confidence, internal, conflicts)
            action, rules = evaluate_rules(
                status, flags, history.claims if history else None, conflicts, confidence.level
            )
            d.append(f"{action.value}, confianza {confidence.level.value}")

        short_circuit = next((r for r in rules if r.rule_id == "R1"), None)
        web = WebResearch(
            status="skipped" if short_circuit else "not_run",
            reason=(
                "Short-circuit por regla R1"
                if short_circuit
                else "Investigación web aún no implementada en esta versión"
            ),
        )
        if short_circuit:
            trace.short_circuit = f"R1: {short_circuit.explanation}"

        gaps = list(history.data_gaps) if history else []
        if status is ProfileStatus.NOT_FOUND:
            gaps.append("La empresa no existe en el portafolio, siniestros ni watchlist internos")

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
                summary=self._summary(status, res, identity, history, flags, action, as_of),
            ),
            trace=trace,
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
        return (
            pd.Timestamp(as_of) - pd.Timestamp(history.relationship.first_policy_start)
        ).days / 365.25

    def _candidate_summaries(
        self, res: ResolutionResult, flags: list[RiskFlag]
    ) -> list[CandidateSummary]:
        if res.outcome not in (
            ResolutionOutcome.AMBIGUOUS,
            ResolutionOutcome.RESOLVED_WITH_AMBIGUITY,
        ):
            return []
        active = {}
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
    def _summary(status, res, identity, history, flags, action, as_of) -> str:
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
        return (
            f"{identity.legal_name} ({identity.state}): {rel.n_policies} pólizas, "
            f"{rel.n_active_policies} vigentes al {as_of.isoformat()}; siniestralidad "
            f"{clm.client_loss_ratio:.0%} ({'creíble' if clm.credibility.value == 'credible' else 'poco creíble'}); "
            f"{n_active_flags} bandera(s) activa(s) en watchlist. Recomendación: {label}."
        )
