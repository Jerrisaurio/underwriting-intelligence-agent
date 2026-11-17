"""Deterministic normalization of Mexican company names.

A name is split into a *core* (what identifies the business, e.g. ``TECNOLOGIAS ARCOIRIS``)
and a *legal form* (``SA DE CV``, ``SAPI``...).

Why the legal form is kept, not discarded: in the portfolio, the legal-form
*family* (SA, SAPI, SAB, S de RL, SC) is constant within a ClientId (1 exception
out of 8,565) and separates otherwise identical names. "Tecnologías Arcoíris S.C." and
"Tecnologías Arcoíris S.A. de C.V." are different clients. The "de C.V." suffix, by
contrast, varies inside a single ClientId in 190 cases ("SAPI" vs "S.A.P.I. de
C.V."), so it is recorded separately (``has_cv``) and only used as a weak signal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Appended descriptors that are not part of the identifying name.
_TRAILING_DESCRIPTORS = re.compile(r"\s+INSTITUCION DE BANCA MULTIPLE$")

# Common abbreviations expanded so that "GF Inbursa" == "Grupo Financiero Inbursa"
# and "Org. Soriana" == "Organización Soriana".
_ABBREVIATIONS = {
    "GF": "GRUPO FINANCIERO",
    "ORG": "ORGANIZACION",
    "CORP": "CORPORATION",
    "CIA": "COMPANIA",
}

_CV = r"(?:\s?DE\s?C\s?V)"
# Order matters: the longer forms (SAB, SAPI) must be tried before the plain SA.
_LEGAL_FORMS: list[tuple[str, re.Pattern[str]]] = [
    ("SAB", re.compile(rf"\bS\s?A\s?B{_CV}?$")),
    ("SAPI", re.compile(rf"\bS\s?A\s?P\s?I{_CV}?$")),
    ("SRL", re.compile(rf"\bS(?:\s?DE)?\s?R\s?L{_CV}?$")),
    ("SA", re.compile(r"\bSACV$")),
    ("SA", re.compile(rf"\bS\s?A{_CV}?$")),
    ("SCL", re.compile(r"\bS\s?C\s?L$")),
    ("SC", re.compile(r"\bS\s?C$")),
    ("PLC", re.compile(r"\bPLC$")),
]
_HAS_CV = re.compile(r"(?:C\s?V|SACV)$")


@dataclass(frozen=True)
class NormalizedName:
    raw: str
    core: str  # e.g. "TECNOLOGIAS ARCOIRIS"
    legal_family: str | None  # e.g. "SA"; None when the name carries no legal form
    has_cv: bool  # True when the legal form ends in "de C.V."

    @property
    def tokens(self) -> frozenset[str]:
        return frozenset(self.core.split())

    @property
    def compact(self) -> str:
        """Core without spaces: makes "VivaAerobus" equal to "Viva Aerobus"."""
        return self.core.replace(" ", "")


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _clean(text: str) -> str:
    text = strip_accents(text).upper()
    text = text.replace(".", "").replace("&", "")  # "S.A." -> "SA", "AT&T" -> "ATT"
    text = re.sub(r"[^A-Z0-9 ]", " ", text)  # "-", ",", quotes... -> space
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(raw: str) -> NormalizedName:
    text = _TRAILING_DESCRIPTORS.sub("", _clean(raw or ""))
    family: str | None = None
    has_cv = False
    for fam, pattern in _LEGAL_FORMS:
        match = pattern.search(text)
        if match:
            family = fam
            has_cv = bool(_HAS_CV.search(match.group(0)))
            text = text[: match.start()].strip()
            break
    core = " ".join(_ABBREVIATIONS.get(tok, tok) for tok in text.split())
    return NormalizedName(raw=raw, core=core, legal_family=family, has_cv=has_cv)


def normalize_state(state: str | None) -> str | None:
    return _clean(state) if state else None
