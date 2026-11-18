"""Depth calibration: how much web research a profile justifies.

T0  no research: short-circuited (R1), invalid or ambiguous input (we do not know which
    company to research), or research unavailable.
T2  risk signals present: deeper adverse-media search (up to 5 searches).
T1  identity confirmation only (up to 2 searches), including when the only question is the
    industry (missing or inconsistent with the name): the identity check answers it.
"""

from __future__ import annotations

from uw_agent.schema.profile import (
    ClaimsPerformance,
    CompanyIdentity,
    Conflict,
    ConflictType,
    Credibility,
    ProfileStatus,
    Relationship,
    RiskFlag,
)

LR_DEEPEN = 0.8
DISPUTED_DEEPEN = 2
# Same criterion as action rule R5d: an absolute count alone flags every large client.
DISPUTED_SHARE_DEEPEN = 0.25


def choose_depth(
    status: ProfileStatus,
    short_circuit: bool,
    flags: list[RiskFlag],
    identity: CompanyIdentity | None,
    relationship: Relationship | None,
    claims: ClaimsPerformance | None,
    conflicts: list[Conflict],
    sum_insured_p90: float,
) -> tuple[str, list[str]]:
    if short_circuit:
        return "T0", ["Short-circuit: bandera crítica confirmada (R1)"]
    if status in (ProfileStatus.INVALID_INPUT, ProfileStatus.AMBIGUOUS, ProfileStatus.ERROR):
        return "T0", [f"Estatus {status.value}: no hay una empresa identificada que investigar"]

    reasons: list[str] = []
    if status is ProfileStatus.NOT_FOUND:
        reasons.append("Sin registro interno: la web es la única fuente")
    if flags:
        reasons.append(f"{len(flags)} entrada(s) de watchlist (activas o resueltas)")
    if (
        claims
        and claims.credibility is Credibility.CREDIBLE
        and claims.client_loss_ratio > LR_DEEPEN
    ):
        reasons.append(f"Siniestralidad creíble de {claims.client_loss_ratio:.0%}")
    disputed = claims.by_status.get("en_disputa", 0) if claims else 0
    if disputed >= DISPUTED_DEEPEN and disputed / claims.n_claims >= DISPUTED_SHARE_DEEPEN:
        reasons.append(f"{disputed} de {claims.n_claims} siniestros en disputa")
    if relationship and relationship.total_sum_insured_mxn > sum_insured_p90:
        reasons.append("Suma asegurada en el 10% más alto del portafolio")
    if reasons:
        return "T2", reasons
    # An industry question is answered by the identity check (T1 returns the industry from the
    # portfolio's closed list); escalating it to adverse-media search (T2) would spend searches
    # on a data-quality gap that is endemic in this portfolio, not on risk.
    industry_issues = {ConflictType.INDUSTRY_MISSING, ConflictType.INDUSTRY_NAME_MISMATCH}
    if identity and any(c.type in industry_issues for c in conflicts):
        return "T1", [
            "Industria faltante o inconsistente: verificar el giro con la identidad pública"
        ]
    return "T1", ["Sin señales de riesgo: solo confirmación de identidad"]
