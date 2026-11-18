"""Recommended action: deterministic rules with precedence.

Every rule that fires is reported (rule id + Spanish explanation); the action is the one with
the highest precedence among them. Order of ``PRECEDENCE`` = order in docs/SCHEMA.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from uw_agent.agent.conflicts import unflagged_adverse
from uw_agent.schema.profile import (
    ClaimsPerformance,
    ConfidenceLevel,
    Conflict,
    Credibility,
    ProfileStatus,
    RecommendedAction,
    RiskFlag,
    Severity,
    TriggeredRule,
    WatchlistLink,
    WebResearch,
)

A = RecommendedAction
PRECEDENCE = [
    A.DECLINE,
    A.REFER_TO_COMPLIANCE,
    A.NEEDS_CLARIFICATION,
    A.INSUFFICIENT_INFORMATION,
    A.REFER_TO_SENIOR_UNDERWRITER,
    A.PROCEED_WITH_CONDITIONS,
    A.PROCEED_STANDARD,
]

COMPLIANCE_TYPES = {"sancion_regulatoria", "investigacion_fraude", "persona_politicamente_expuesta"}
DECLINE_TYPES = {"sancion_regulatoria", "investigacion_fraude"}
LR_REFER = 1.0
LR_CONDITIONS = 0.7
DISPUTED_REFER = 2
# Share of the client's claims in dispute. An absolute count alone does not scale: the largest
# clients have many disputed claims in absolute terms while their disputed share equals the
# portfolio average.
DISPUTED_SHARE_REFER = 0.25


@dataclass(frozen=True)
class RuleThresholds:
    lr_refer: float = LR_REFER
    lr_conditions: float = LR_CONDITIONS
    disputed_refer: int = DISPUTED_REFER
    disputed_share_refer: float = DISPUTED_SHARE_REFER


def _flag_label(f: RiskFlag) -> str:
    return f"{f.watchlist_id} {f.flag_type}/{f.severity}"


def short_circuits(flags: list[RiskFlag]) -> bool:
    """R1 can be decided before any web call: it depends only on confirmed watchlist flags."""
    return any(
        f.is_active
        and f.link is WatchlistLink.CONFIRMED
        and f.flag_type in DECLINE_TYPES
        and f.severity == "crítico"
        for f in flags
    )


def evaluate_rules(
    status: ProfileStatus,
    flags: list[RiskFlag],
    claims: ClaimsPerformance | None,
    conflicts: list[Conflict],
    confidence_level: ConfidenceLevel,
    web: WebResearch | None = None,
    t: RuleThresholds = RuleThresholds(),
) -> tuple[RecommendedAction, list[TriggeredRule]]:
    fired: list[TriggeredRule] = []

    def fire(rule_id: str, action: RecommendedAction, explanation: str):
        fired.append(TriggeredRule(rule_id=rule_id, action=action, explanation=explanation))

    active = [f for f in flags if f.is_active]
    confirmed = [f for f in active if f.link is WatchlistLink.CONFIRMED]
    possible = [f for f in active if f.link is WatchlistLink.POSSIBLE]

    for f in confirmed:
        critical = f.severity == "crítico"
        if f.flag_type in DECLINE_TYPES and critical:
            fire("R1", A.DECLINE, f"Bandera activa crítica confirmada: {_flag_label(f)}.")
        elif f.flag_type in COMPLIANCE_TYPES:
            fire("R2", A.REFER_TO_COMPLIANCE, f"Bandera activa de cumplimiento: {_flag_label(f)}.")
        elif f.flag_type == "pago_incumplido" and critical:
            fire("R5a", A.REFER_TO_SENIOR_UNDERWRITER, f"Impago crítico activo: {_flag_label(f)}.")
        elif f.flag_type in {"litigio_activo", "riesgo_crediticio"} and f.severity == "alto":
            fire(
                "R5b",
                A.REFER_TO_SENIOR_UNDERWRITER,
                f"Bandera activa de severidad alta: {_flag_label(f)}.",
            )
        else:
            fire(
                "R6a",
                A.PROCEED_WITH_CONDITIONS,
                f"Bandera activa a atender como condición: {_flag_label(f)}.",
            )

    for f in possible:
        # Possible links never decline: a human must confirm the entity first.
        if f.flag_type in COMPLIANCE_TYPES:
            fire(
                "R2b",
                A.REFER_TO_COMPLIANCE,
                f"Posible coincidencia en watchlist ({f.link_method.value}) con {f.linked_client_id}: "
                f"{_flag_label(f)}.",
            )
        else:
            fire(
                "R6b",
                A.PROCEED_WITH_CONDITIONS,
                f"Posible coincidencia en watchlist ({f.link_method.value}) con {f.linked_client_id}: "
                f"{_flag_label(f)}.",
            )

    if status is ProfileStatus.INVALID_INPUT:
        fire(
            "R0",
            A.INSUFFICIENT_INFORMATION,
            "El nombre recibido no es válido; no se evaluó ninguna fuente.",
        )
    if status is ProfileStatus.AMBIGUOUS:
        fire(
            "R3", A.NEEDS_CLARIFICATION, "Varios clientes coinciden con el nombre y ninguno domina."
        )
    if status is ProfileStatus.NOT_FOUND:
        fire("R4a", A.INSUFFICIENT_INFORMATION, "No se encontró el cliente en las bases internas.")
    elif status is ProfileStatus.COMPLETE and confidence_level is ConfidenceLevel.LOW:
        fire(
            "R4b",
            A.INSUFFICIENT_INFORMATION,
            "La evidencia disponible es insuficiente (confianza baja).",
        )

    if claims is not None and claims.credibility is Credibility.CREDIBLE:
        lr = claims.client_loss_ratio
        if lr > t.lr_refer:
            fire(
                "R5c",
                A.REFER_TO_SENIOR_UNDERWRITER,
                f"Siniestralidad creíble de {lr:.0%} (> {t.lr_refer:.0%}).",
            )
        elif lr > t.lr_conditions:
            fire(
                "R6c",
                A.PROCEED_WITH_CONDITIONS,
                f"Siniestralidad creíble de {lr:.0%} (entre {t.lr_conditions:.0%} y {t.lr_refer:.0%}).",
            )
    disputed = claims.by_status.get("en_disputa", 0) if claims is not None else 0
    if disputed >= t.disputed_refer and disputed / claims.n_claims >= t.disputed_share_refer:
        fire(
            "R5d",
            A.REFER_TO_SENIOR_UNDERWRITER,
            f"{disputed} de {claims.n_claims} siniestros en disputa ({disputed / claims.n_claims:.0%}).",
        )
    for c in conflicts:
        if c.severity is Severity.HIGH:
            fire(
                "R5e",
                A.REFER_TO_SENIOR_UNDERWRITER,
                f"Conflicto de severidad alta {c.id}: {c.type.value}.",
            )

    # Web evidence is less authoritative than internal data: it can refer, never decline.
    for f in unflagged_adverse(flags, web):
        if f.risk_category in ("sanction", "fraud"):
            fire(
                "R2c",
                A.REFER_TO_COMPLIANCE,
                f"Fuente pública adversa ({f.risk_category}) sin bandera en watchlist: {f.id}.",
            )
        else:
            fire(
                "R5f",
                A.REFER_TO_SENIOR_UNDERWRITER,
                f"Fuente pública adversa ({f.risk_category}) sin bandera en watchlist: {f.id}.",
            )

    if not fired:
        fire(
            "R7",
            A.PROCEED_STANDARD,
            "Sin banderas activas, siniestralidad dentro de rango y sin conflictos graves.",
        )
    action = min((r.action for r in fired), key=PRECEDENCE.index)
    return action, fired
