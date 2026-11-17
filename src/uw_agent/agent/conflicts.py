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
    RiskFlag,
    Severity,
    WatchlistLink,
)

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


def detect_conflicts(
    resolution: ResolutionResult,
    identity: CompanyIdentity | None,
    flags: list[RiskFlag],
    anomalies: list[tuple[str, list[str]]],
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
    return b.items
