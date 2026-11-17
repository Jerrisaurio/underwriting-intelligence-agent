"""Fuzzy entity resolution: free-text company name -> portfolio ClientId.

Pipeline (every step is deterministic, so the same input always gives the same answer):

1. Normalize the query into core + legal form (see ``normalize.py``).
2. Score every distinct core spelling in the portfolio against the query core:
   exact > compact (spaces ignored) > partial (all query words present) > fuzzy
   (typos / word order). Curated aliases are scored in the same pass.
3. Adjust each candidate spelling by legal form (same family: small bonus;
   different family: strong penalty) and keep the best spelling per ClientId.
4. Decide. Homonyms are the norm in this data (74% of full names map to more than
   one ClientId), so a tie is resolved to the leader only when the leader clearly
   dominates by number of policies; otherwise the result is AMBIGUOUS and the
   candidates are returned instead of a guess.

All thresholds live in ``ResolverConfig`` and are calibrated with
``eval/run_resolution_eval.py``; they are not tuned by hand on single examples.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import fuzz
from rapidfuzz.distance import DamerauLevenshtein

from uw_agent.data.repository import DataRepository
from uw_agent.resolution.models import (
    Candidate,
    MatchType,
    ResolutionOutcome,
    ResolutionResult,
)
from uw_agent.resolution.normalize import NormalizedName, normalize_name, normalize_state

log = logging.getLogger(__name__)

DEFAULT_ALIAS_FILE = Path(__file__).with_name("aliases.yaml")
MAX_QUERY_LENGTH = 200


@dataclass(frozen=True)
class ResolverConfig:
    min_score: float = 0.80
    fuzzy_min: float = 0.90  # below this, a typo match is too likely to be another company
    fuzzy_cap: float = 0.97  # a fuzzy match never ties an exact one
    fuzzy_word_min: float = 0.80  # each word must be this close (see _words_align)
    compact_score: float = 0.98
    alias_score: float = 0.95
    partial_base: float = 0.80
    partial_span: float = 0.15  # partial score grows with the share of the name covered
    family_bonus_same_cv: float = 0.02
    family_bonus_diff_cv: float = 0.01
    family_mismatch_penalty: float = 0.15
    tie_eps: float = 0.005  # candidates this close are indistinguishable by name
    ambiguity_window: float = 0.05  # candidates this close are reported as alternatives
    dominance_threshold: float = 0.70
    ambiguity_confidence_factor: float = 0.90
    ambiguous_confidence_cap: float = 0.40
    max_candidates: int = 10


@dataclass(frozen=True)
class _Variant:
    client_id: str
    raw: str
    norm: NormalizedName


@dataclass
class _Scored:
    client_id: str
    score: float
    match_type: MatchType
    variant: _Variant
    legal_form_match: bool | None


class EntityResolver:
    def __init__(
        self,
        portfolio: pd.DataFrame,
        clients: pd.DataFrame,
        alias_file: Path | None = DEFAULT_ALIAS_FILE,
        config: ResolverConfig | None = None,
    ) -> None:
        self.config = config or ResolverConfig()
        self._clients = clients.to_dict("index")

        pairs = portfolio[["ClientId", "client_name"]].drop_duplicates()
        self._by_core: dict[str, list[_Variant]] = defaultdict(list)
        self._raw_to_ids: dict[str, set[str]] = defaultdict(set)
        for cid, raw in pairs.itertuples(index=False):
            variant = _Variant(cid, raw, normalize_name(raw))
            if variant.norm.core:
                self._by_core[variant.norm.core].append(variant)
            self._raw_to_ids[raw].add(cid)
        # Pre-compute per-core data used in the scoring loop.
        self._cores = [
            (core, frozenset(core.split()), core.replace(" ", "")) for core in self._by_core
        ]
        self._aliases = self._load_aliases(alias_file) if alias_file else {}

    @classmethod
    def from_repository(cls, repo: DataRepository, **kwargs) -> EntityResolver:
        return cls(repo.portfolio, repo.clients, **kwargs)

    # ------------------------------------------------------------------ public API

    def resolve(self, name: str, state: str | None = None) -> ResolutionResult:
        query = (name or "").strip()
        q = normalize_name(query)
        base = {
            "query": query,
            "state_hint": state,
            "normalized_core": q.core,
            "normalized_legal_family": q.legal_family,
        }
        invalid = self._validate(query, q)
        if invalid:
            return ResolutionResult(
                **base,
                outcome=ResolutionOutcome.INVALID_INPUT,
                entity_confidence=0.0,
                notes=[invalid],
            )

        scored = self._score_all(q)
        notes: list[str] = []
        scored = self._apply_state_hint(scored, state, notes)
        ranked = sorted(
            (s for s in scored.values() if s.score >= self.config.min_score),
            key=lambda s: (-s.score, -self._clients[s.client_id]["n_policies"]),
        )
        if not ranked:
            return ResolutionResult(
                **base, outcome=ResolutionOutcome.NOT_FOUND, entity_confidence=0.0, notes=notes
            )
        return self._decide(base, ranked, notes)

    # ------------------------------------------------------------------ scoring

    def _validate(self, query: str, q: NormalizedName) -> str | None:
        if not query:
            return "Empty company name"
        if len(query) > MAX_QUERY_LENGTH:
            return f"Company name longer than {MAX_QUERY_LENGTH} characters"
        if not q.core:
            return "Name contains only a legal form (e.g. 'S.A. de C.V.')"
        return None

    def _core_similarity(
        self, q: NormalizedName, core: str, tokens: frozenset[str], compact: str
    ) -> tuple[float, MatchType] | None:
        cfg = self.config
        if q.core == core:
            return 1.0, MatchType.EXACT
        if q.compact == compact:
            return cfg.compact_score, MatchType.COMPACT
        q_tokens = q.tokens
        if q_tokens < tokens:
            # The user typed part of the name ("Bajío" for "Tecnologías Bajío").
            coverage = len(q.core) / len(core)
            return cfg.partial_base + cfg.partial_span * coverage, MatchType.PARTIAL
        if tokens < q_tokens:
            # The *portfolio* spelling is a truncation of the query (the data contains
            # "Bajío S.A. de C.V." as a variant of several companies). Matching it would
            # link "Soluciones Bajío" to "Tecnologías Bajío", so it is ignored here; the
            # candidate still matches through its full spellings.
            return None
        sim = max(fuzz.ratio(q.core, core), fuzz.token_sort_ratio(q.core, core)) / 100
        if sim < cfg.fuzzy_min or not self._words_align(q.core.split(), core.split()):
            return None
        return min(sim, cfg.fuzzy_cap), MatchType.FUZZY

    def _words_align(self, q_words: list[str], c_words: list[str]) -> bool:
        """Every word must resemble its counterpart, not just the string as a whole.

        Whole-string similarity dilutes a one-word difference: "Constructora Modelo" vs
        "Constructora Morelos" scores 0.94 although they are different companies (the
        synthetic names differ by exactly one word). A typo keeps each word close
        ("Sevicios" vs "Servicios" = 0.94); a different word does not ("Modelo" vs
        "Morelos" = 0.77). Words are aligned in order and also sorted (word-order typos).
        """
        if len(q_words) != len(c_words):
            return False

        def close(x: str, y: str) -> bool:
            if fuzz.ratio(x, y) / 100 >= self.config.fuzzy_word_min:
                return True
            # Short words: a single transposition ("Nvoa" for "Nova") costs 2 Levenshtein
            # edits (ratio 0.5) but only 1 Damerau-Levenshtein edit. Allow exactly one
            # such edit on words of 4+ letters; "Modelo" vs "Morelos" needs 2 and is rejected.
            return min(len(x), len(y)) >= 4 and DamerauLevenshtein.distance(x, y) <= 1

        def aligned(a: list[str], b: list[str]) -> bool:
            return all(close(x, y) for x, y in zip(a, b, strict=True))

        return aligned(q_words, c_words) or aligned(sorted(q_words), sorted(c_words))

    def _legal_adjustment(self, q: NormalizedName, v: NormalizedName) -> tuple[float, bool | None]:
        cfg = self.config
        if q.legal_family is None or v.legal_family is None:
            return 0.0, None
        if q.legal_family != v.legal_family:
            return -cfg.family_mismatch_penalty, False
        if q.has_cv == v.has_cv:
            return cfg.family_bonus_same_cv, True
        return cfg.family_bonus_diff_cv, True

    def _score_all(self, q: NormalizedName) -> dict[str, _Scored]:
        best: dict[str, _Scored] = {}

        def offer(variant: _Variant, base_score: float, match_type: MatchType, use_legal: bool):
            adj, form_match = self._legal_adjustment(q, variant.norm) if use_legal else (0, None)
            cand = _Scored(variant.client_id, base_score + adj, match_type, variant, form_match)
            current = best.get(variant.client_id)
            if current is None or cand.score > current.score:
                best[variant.client_id] = cand

        for core, tokens, compact in self._cores:
            hit = self._core_similarity(q, core, tokens, compact)
            if hit:
                for variant in self._by_core[core]:
                    offer(variant, hit[0], hit[1], use_legal=True)

        for variant in self._aliases.get(q.core, []):
            offer(variant, self.config.alias_score, MatchType.ALIAS, use_legal=False)
        return best

    def _apply_state_hint(
        self, scored: dict[str, _Scored], state: str | None, notes: list[str]
    ) -> dict[str, _Scored]:
        if not state:
            return scored
        wanted = normalize_state(state)
        kept = {
            cid: s
            for cid, s in scored.items()
            if normalize_state(self._clients[cid]["state"]) == wanted
        }
        if kept:
            notes.append(f"Candidates filtered by state hint '{state}'")
            return kept
        if scored:
            notes.append(f"State hint '{state}' matched no candidate; hint ignored")
        return scored

    # ------------------------------------------------------------------ decision

    def _decide(self, base: dict, ranked: list[_Scored], notes: list[str]) -> ResolutionResult:
        cfg = self.config
        top = ranked[0]
        window = [s for s in ranked if s.score >= top.score - cfg.ambiguity_window]

        if top.match_type is MatchType.PARTIAL:
            # Partial scores only reflect how much of each name was typed, so all partial
            # matches in the window are equally plausible.
            tier = [s for s in window if s.match_type is MatchType.PARTIAL]
        else:
            tier = [s for s in ranked if s.score >= top.score - cfg.tie_eps]
        tier_ids = {s.client_id for s in tier}
        outside = [s for s in ranked if s.client_id not in tier_ids]
        margin = round(top.score - outside[0].score, 4) if outside else None

        n_pol = {s.client_id: self._clients[s.client_id]["n_policies"] for s in tier}
        leader = max(tier, key=lambda s: (n_pol[s.client_id], s.score))
        dominance = n_pol[leader.client_id] / sum(n_pol.values())
        score = min(top.score, 1.0)

        if len(window) == 1:
            outcome, client_id, confidence = ResolutionOutcome.RESOLVED, leader.client_id, score
        elif top.match_type is MatchType.PARTIAL and len({s.variant.norm.core for s in tier}) > 1:
            notes.append(
                "Query matches only part of several different names; too generic to pick one"
            )
            outcome, client_id = ResolutionOutcome.AMBIGUOUS, None
            confidence = min(cfg.ambiguous_confidence_cap, score * dominance)
        elif dominance >= cfg.dominance_threshold:
            outcome, client_id = ResolutionOutcome.RESOLVED_WITH_AMBIGUITY, leader.client_id
            confidence = score * dominance * cfg.ambiguity_confidence_factor
            notes.append(
                f"{len(window) - 1} other ClientId(s) match closely; profile built for the "
                f"one with most policies ({dominance:.0%} of the tied candidates' policies)"
            )
        else:
            outcome, client_id = ResolutionOutcome.AMBIGUOUS, None
            confidence = min(cfg.ambiguous_confidence_cap, score * dominance)
            notes.append("Several ClientIds match and none dominates; clarification needed")

        if client_id:
            chosen = next(s for s in ranked if s.client_id == client_id)
            if chosen.legal_form_match is False:
                notes.append("Legal form in the query differs from the matched client's")
            if chosen.match_type in (MatchType.PARTIAL, MatchType.FUZZY, MatchType.ALIAS):
                notes.append(f"Matched by {chosen.match_type.value} name match")

        ordered = [leader] + [s for s in ranked if s is not leader]
        return ResolutionResult(
            **base,
            outcome=outcome,
            client_id=client_id,
            entity_confidence=round(confidence, 4),
            dominance=round(dominance, 4) if len(window) > 1 else None,
            margin_to_next=margin,
            candidates=[self._to_candidate(s) for s in ordered[: cfg.max_candidates]],
            n_candidates_total=len(ranked),
            notes=notes,
        )

    def _to_candidate(self, s: _Scored) -> Candidate:
        info = self._clients[s.client_id]
        return Candidate(
            client_id=s.client_id,
            display_name=info["display_name"],
            state=info["state"],
            municipality=info["municipality"],
            n_policies=int(info["n_policies"]),
            score=round(min(s.score, 1.0), 4),
            match_type=s.match_type,
            matched_variant=s.variant.raw,
            legal_form_match=s.legal_form_match,
        )

    # ------------------------------------------------------------------ aliases

    def _load_aliases(self, path: Path) -> dict[str, list[_Variant]]:
        entries = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("aliases", [])
        index: dict[str, list[_Variant]] = defaultdict(list)
        for entry in entries:
            target = entry.get("target")
            ids = self._raw_to_ids.get(target or "", set())
            if not ids:
                log.warning(
                    "Alias %r -> %r: target not in portfolio, skipped", entry.get("alias"), target
                )
                continue
            alias_core = normalize_name(entry["alias"]).core
            for cid in sorted(ids):
                index[alias_core].append(_Variant(cid, target, normalize_name(target)))
        return dict(index)
