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
    Relationship,
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


# How each conflict is reasoned through: (authoritative source and why, implication for
# underwriting, what to verify). Deterministic on purpose: the reasoning must be reproducible,
# testable and available even when no language model is configured.
REASONING: dict[ConflictType, tuple[str, str, str]] = {
    ConflictType.ENTITY_AMBIGUITY: (
        "El portafolio es la fuente de identidad, pero el nombre por sí solo no distingue entre clientes homónimos.",
        "Todo el perfil podría corresponder a otra empresa con el mismo nombre.",
        "Confirmar estado, razón social completa o RFC con el solicitante.",
    ),
    ConflictType.WATCHLIST_NOTE_VS_STATUS: (
        "Ambos datos son internos; el estatus es un campo estructurado y la nota es el texto del analista.",
        "Una bandera marcada como resuelta podría seguir vigente.",
        "Confirmar con Cumplimiento el estado real del caso antes de emitir.",
    ),
    ConflictType.FLAG_PREDATES_RELATIONSHIP: (
        "Las fechas internas son confiables: la bandera ya existía al iniciar la relación.",
        "Se suscribió con la bandera registrada; puede haber una excepción aprobada o un error de control.",
        "Revisar si existe una autorización documentada para esas pólizas.",
    ),
    ConflictType.WATCHLIST_LINKED_BY_NAME_ONLY: (
        "El ClientId es el vínculo autoritativo; aquí solo coincide el nombre.",
        "La bandera podría pertenecer a otra entidad con el mismo nombre.",
        "Verificar la identidad de la entrada de watchlist antes de aplicarla.",
    ),
    ConflictType.INDUSTRY_MISSING: (
        "El portafolio es la fuente autoritativa de la industria, pero no la registra.",
        "No se puede validar que la cobertura corresponda al giro real del cliente.",
        "Solicitar el giro al cliente o al agente.",
    ),
    ConflictType.INDUSTRY_NAME_MISMATCH: (
        "La industria registrada es el dato autoritativo; el nombre solo sugiere un giro.",
        "Puede ser un error de captura o una empresa que cambió de giro.",
        "Confirmar el giro actual antes de tarificar.",
    ),
    ConflictType.DATA_ANOMALY: (
        "Los registros afectados se excluyeron de las métricas; el resto del perfil se mantiene.",
        "Las cifras podrían estar incompletas.",
        "Revisar los registros citados en la fuente.",
    ),
    ConflictType.WATCHLIST_STATUS_VS_NEWS: (
        "La watchlist es la fuente interna de cumplimiento, pero la fuente pública es posterior a la resolución.",
        "Una bandera resuelta podría estar reactivada.",
        "Verificar con Cumplimiento antes de emitir.",
    ),
    ConflictType.INDUSTRY_WEB_MISMATCH: (
        "Se conserva la industria interna (autoritativa); la web solo aporta evidencia contraria.",
        "La tarificación podría basarse en un giro que ya no corresponde.",
        "Confirmar el giro actual con el cliente.",
    ),
    ConflictType.ADVERSE_MEDIA_NOT_IN_WATCHLIST: (
        "Los datos internos no registran el evento; la fuente pública es menos autoritativa pero específica.",
        "Puede existir un riesgo no capturado por la watchlist.",
        "Validar la fuente y, si se confirma, registrar la bandera.",
    ),
    ConflictType.ACTIVE_FLAG_VS_NEWS: (
        "La watchlist es la fuente interna de cumplimiento y la bandera sigue activa; la fuente pública es menos autoritativa.",
        "La bandera podría estar desactualizada, o la noticia ser incompleta; la bandera se mantiene para la decisión.",
        "Confirmar con Cumplimiento si el caso ya se resolvió y actualizar la watchlist.",
    ),
    ConflictType.COVERAGE_VS_WEB_INDUSTRY: (
        "La cobertura interna es autoritativa sobre lo contratado, pero no sobre el giro; la web describe el giro.",
        "La cobertura podría no corresponder a la actividad real del cliente.",
        "Confirmar qué actividad ampara la póliza.",
    ),
}

# Coverages bought only by specific businesses, and the industries consistent with them.
# Fleet, liability, fire, cargo and miscellaneous are bought by any business: they imply nothing.
COVERAGE_INDUSTRIES: dict[str, set[str]] = {
    "Agrícola": {"Agricultura", "Alimentos y Bebidas"},
    "Ingeniería": {"Construcción", "Inmobiliaria", "Minería", "Manufactura"},
}
COVERAGE_MAJORITY = 0.5


class _Builder:
    def __init__(self) -> None:
        self.items: list[Conflict] = []

    def add(self, ctype: ConflictType, severity: Severity, description: str, sources: list[str]):
        authority, implication, verify = REASONING[ctype]
        self.items.append(
            Conflict(
                id=f"C{len(self.items) + 1}",
                type=ctype,
                severity=severity,
                description=description,
                sources=sources,
                reasoning=f"Autoridad: {authority} Implicación: {implication} Verificar: {verify}",
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
    relationship: Relationship | None = None,
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

    _web_conflicts(b, identity, flags, web, relationship)
    return b.items


def dominant_specific_coverage(relationship: Relationship | None) -> tuple[str, float] | None:
    """The coverage that implies an industry, if it holds the majority of written premium."""
    if relationship is None or not relationship.total_premium_mxn:
        return None
    for line in relationship.coverage_mix:
        share = line.premium_mxn / relationship.total_premium_mxn
        if line.coverage_type in COVERAGE_INDUSTRIES and share > COVERAGE_MAJORITY:
            return line.coverage_type, share
    return None


def _web_conflicts(
    b: _Builder,
    identity: CompanyIdentity | None,
    flags: list[RiskFlag],
    web: WebResearch | None,
    relationship: Relationship | None = None,
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
    # Active internal flag, public evidence of resolution (the mirror image of the case above).
    if web is not None and web.status is ResearchStatus.DONE:
        for flag in flags:
            if flag.link is not WatchlistLink.CONFIRMED or not flag.is_active:
                continue
            for f in web.findings:
                if (
                    f.entity_match == "confirmed"
                    and f.stance in ("positive", "neutral")
                    and WEB_CATEGORY_TO_FLAG.get(f.risk_category) == flag.flag_type
                ):
                    b.add(
                        ConflictType.ACTIVE_FLAG_VS_NEWS,
                        Severity.MEDIUM,
                        f"La entrada {flag.watchlist_id} ({flag.flag_type}) sigue activa, pero una "
                        f'fuente pública indica: "{f.claim}"',
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
    web_industry = web.identity.industry if web is not None and web.identity is not None else None
    dominant = dominant_specific_coverage(relationship)
    verified = web is not None and web.identity_verified
    if identity is not None and web_industry and dominant and verified:
        coverage, share = dominant
        if web_industry not in COVERAGE_INDUSTRIES[coverage]:
            b.add(
                ConflictType.COVERAGE_VS_WEB_INDUSTRY,
                Severity.MEDIUM,
                f"El {share:.0%} de la prima es de cobertura '{coverage}', propia de "
                f"{', '.join(sorted(COVERAGE_INDUSTRIES[coverage]))}, pero las fuentes públicas "
                f"describen a la empresa como '{web_industry}'.",
                [f"portfolio:client:{identity.client_id}", *[f.id for f in web.findings[:3]]],
            )
    # Only a *recorded* industry can be contradicted; a web-filled one is the web's own value.
    if (
        identity is not None
        and identity.industry
        and identity.industry_source == "portfolio"
        and verified
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
