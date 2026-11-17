"""Conflict detection over internal data.

A conflict is a contradiction or a weakness in the evidence that an underwriter must see.
Conflicts are never resolved automatically here (``resolution = "unresolved"``); their severity
feeds the confidence penalty and, when ``high``, the action rules.
"""

from __future__ import annotations

from uw_agent.resolution import NormalizedName, ResolutionOutcome, ResolutionResult, normalize_name
from uw_agent.schema.profile import (
    CompanyIdentity,
    Conflict,
    ConflictType,
    LinkMethod,
    PublicFinding,
    ResearchStatus,
    RiskFlag,
    Severity,
    WatchlistLink,
    WebResearch,
)

# Web risk categories and the watchlist flag type each one corresponds to.
WEB_CATEGORY_TO_FLAG = {
    "sanction": "sancion_regulatoria",
    "fraud": "investigacion_fraude",
    "litigation": "litigio_activo",
    "credit": "riesgo_crediticio",
    "payment": "pago_incumplido",
}

# Business words in a company name and the industries consistent with them. Only words that
# state a line of business explicitly; generic ones (Grupo, Servicios, Corporativo) are ignored.
BUSINESS_WORD_INDUSTRIES: dict[str, set[str]] = {
    "AGROINDUSTRIAS": {"Agricultura", "Alimentos y Bebidas"},
    "CONSTRUCTORA": {"Construcción", "Inmobiliaria"},
    "TRANSPORTES": {"Transporte y Logística"},
    "INMOBILIARIA": {"Inmobiliaria", "Construcción"},
    "TECNOLOGIAS": {"Tecnología", "Servicios Profesionales"},
}


class _Builder:
    def __init__(self) -> None:
        self.items: list[Conflict] = []

    def add(self, ctype: ConflictType, severity: Severity, description: str, sources: list[str]):
        self.items.append(
            Conflict(
                id=f"C{len(self.items) + 1}",
                type=ctype,
                severity=severity,
                description=description,
                sources=sources,
            )
        )


def business_word(name: NormalizedName) -> str | None:
    words = name.core.split()
    return words[0] if words and words[0] in BUSINESS_WORD_INDUSTRIES else None


def confirmed_adverse(web: WebResearch | None) -> list[PublicFinding]:
    """Negative findings about this very company in a watchlist-relevant category."""
    if web is None or web.status is not ResearchStatus.DONE:
        return []
    return [
        f
        for f in web.findings
        if f.entity_match == "confirmed"
        and f.stance == "negative"
        and f.risk_category in WEB_CATEGORY_TO_FLAG
    ]


def unflagged_adverse(flags: list[RiskFlag], web: WebResearch | None) -> list[PublicFinding]:
    """Confirmed adverse findings with no confirmed watchlist entry of the same type."""
    flagged = {f.flag_type for f in flags if f.link is WatchlistLink.CONFIRMED}
    return [
        f for f in confirmed_adverse(web) if WEB_CATEGORY_TO_FLAG[f.risk_category] not in flagged
    ]


def detect_conflicts(
    resolution: ResolutionResult,
    identity: CompanyIdentity | None,
    flags: list[RiskFlag],
    anomalies: list[tuple[str, list[str]]],
    web: WebResearch | None = None,
) -> list[Conflict]:
    b = _Builder()

    if resolution.outcome is ResolutionOutcome.RESOLVED_WITH_AMBIGUITY:
        others = [c.client_id for c in resolution.candidates if c.client_id != resolution.client_id]
        b.add(
            ConflictType.ENTITY_AMBIGUITY,
            Severity.MEDIUM,
            f"El nombre coincide también con {len(others)} otro(s) cliente(s); se perfiló el de "
            f"mayor número de pólizas. Verificar que sea la empresa correcta.",
            [f"portfolio:client:{cid}" for cid in [resolution.client_id, *others[:5]]],
        )

    for f in flags:
        src = f.evidence
        confirmed = f.link is WatchlistLink.CONFIRMED
        if f.note_contradicts_status:
            b.add(
                ConflictType.WATCHLIST_NOTE_VS_STATUS,
                Severity.HIGH if confirmed else Severity.MEDIUM,
                f"La entrada {f.watchlist_id} ({f.flag_type}) está marcada como 'resuelto', pero su "
                f'nota describe una situación en curso: "{f.notes}".',
                src,
            )
        if confirmed and f.predates_relationship:
            b.add(
                ConflictType.FLAG_PREDATES_RELATIONSHIP,
                Severity.LOW,
                f"La bandera {f.watchlist_id} ({f.flag_type}, {f.flag_date}) es anterior a la primera "
                "póliza del cliente: se emitió con la bandera ya registrada.",
                src,
            )
        if f.link_method is LinkMethod.NAME:
            b.add(
                ConflictType.WATCHLIST_LINKED_BY_NAME_ONLY,
                Severity.MEDIUM,
                f"La entrada {f.watchlist_id} usa el ClientId {f.watchlist_client_id}, que no existe en "
                f'el portafolio; se vinculó solo por el nombre "{f.watchlist_client_name}".',
                src,
            )

    if identity is not None:
        if not identity.industry:
            b.add(
                ConflictType.INDUSTRY_MISSING,
                Severity.LOW,
                "El portafolio no registra la industria del cliente.",
                [f"portfolio:client:{identity.client_id}"],
            )
        else:
            word = business_word(normalize_name(identity.legal_name))
            if word and identity.industry not in BUSINESS_WORD_INDUSTRIES[word]:
                b.add(
                    ConflictType.INDUSTRY_NAME_MISMATCH,
                    Severity.MEDIUM,
                    f"El nombre indica el giro '{word.title()}', pero la industria registrada es "
                    f"'{identity.industry}'.",
                    [f"portfolio:client:{identity.client_id}"],
                )

    for description, sources in anomalies:
        b.add(ConflictType.DATA_ANOMALY, Severity.LOW, description, sources[:20])

    _web_conflicts(b, identity, flags, web)
    return b.items


def _web_conflicts(
    b: _Builder, identity: CompanyIdentity | None, flags: list[RiskFlag], web: WebResearch | None
) -> None:
    """Internal data stays authoritative: web evidence only raises conflicts, never overwrites."""
    adverse = confirmed_adverse(web)
    for flag in flags:
        if flag.link is not WatchlistLink.CONFIRMED or flag.status != "resuelto":
            continue
        for f in adverse:
            same_type = WEB_CATEGORY_TO_FLAG[f.risk_category] == flag.flag_type
            later = (
                f.published_date and flag.resolved_date and f.published_date > flag.resolved_date
            )
            if same_type and later:
                b.add(
                    ConflictType.WATCHLIST_STATUS_VS_NEWS,
                    Severity.HIGH,
                    f"La entrada {flag.watchlist_id} ({flag.flag_type}) se marcó como resuelta el "
                    f"{flag.resolved_date}, pero una fuente pública del {f.published_date} indica: "
                    f'"{f.claim}"',
                    [*flag.evidence, f.id],
                )
    for f in unflagged_adverse(flags, web):
        b.add(
            ConflictType.ADVERSE_MEDIA_NOT_IN_WATCHLIST,
            Severity.MEDIUM,
            f"Fuente pública con información adversa ({f.risk_category}) sin bandera equivalente "
            f'en la watchlist: "{f.claim}"',
            [f.id],
        )
    if (
        identity is not None
        and identity.industry
        and web is not None
        and web.identity is not None
        and web.identity.industry
        and web.identity.industry != identity.industry
    ):
        b.add(
            ConflictType.INDUSTRY_WEB_MISMATCH,
            Severity.MEDIUM,
            f"El portafolio registra la industria '{identity.industry}', pero las fuentes públicas "
            f"describen a la empresa como '{web.identity.industry}'.",
            [f"portfolio:client:{identity.client_id}", *[f.id for f in web.findings[:3]]],
        )
