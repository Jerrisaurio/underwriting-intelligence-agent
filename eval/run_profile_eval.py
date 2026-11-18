"""Profile-level evaluation against verifiable facts.

There is no ground truth for "the right underwriting decision", so this evaluation checks
what *can* be verified:

1. Watchlist recall. For every sampled client, each watchlist entry under its ClientId must
   appear in the profile: as ``confirmed`` when the name resolved to that client, or at least as
   ``possible`` when the client was a candidate. Plus the 7 entries whose ClientId is absent
   from the portfolio, which must be reached by name. Target: 100% (a missed sanction is the
   costliest error the agent can make).
2. Aggregate exactness: policies, premium, claims, incurred and loss ratio recomputed with an
   independent pandas implementation.
3. Evidence validity: every evidence id cited in a profile exists in the source data.
4. Schema validity: every profile round-trips through the schema.
5. Reliability, latency and cost per lookup.

The sample is seeded: all ClientIds that have watchlist entries, plus random clients; the
input is one of the client's recorded spellings.

``--with-state`` passes the client's state as the underwriter would (most names are shared by
several clients, so the state is what makes them identifiable).

Run:  uv run python eval/run_profile_eval.py [--sample 300] [--as-of 2025-09-28] [--with-state]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uw_agent.agent import ProfilePipeline  # noqa: E402
from uw_agent.config import Settings  # noqa: E402
from uw_agent.data import DataRepository  # noqa: E402
from uw_agent.schema.profile import UnderwritingProfile  # noqa: E402
from uw_agent.web import build_researcher  # noqa: E402

SEED = 20261117
# Approximate extraction date of the source files: keeps "active policy" meaningful.
DEFAULT_AS_OF = "2025-09-28"
TOL = 0.01


def expected_aggregates(repo: DataRepository, cid: str, as_of: date) -> dict:
    """Independent re-implementation (plain pandas filters, no shared code with tools/)."""
    ts = pd.Timestamp(as_of)
    p = repo.portfolio[(repo.portfolio.ClientId == cid) & (repo.portfolio.policy_start_date <= ts)]
    c = repo.claims[
        (repo.claims.ClientId == cid)
        & (repo.claims.claim_date <= ts)
        & repo.claims.policy_id.isin(p.policy_id)
    ]
    premium = p.premium.sum()
    return {
        "n_policies": len(p),
        "premium": premium,
        "n_claims": len(c),
        "incurred": c.incurred_loss_mxn.sum(),
        "loss_ratio": c.incurred_loss_mxn.sum() / premium if premium else 0.0,
    }


def evidence_ids(profile: UnderwritingProfile) -> list[str]:
    ids: list[str] = []
    for section in (profile.company_identity, profile.relationship, profile.claims_performance):
        if section is not None:
            ids += section.evidence
    for f in profile.risk_flags:
        ids += f.evidence
    for c in profile.conflicts:
        ids += c.sources
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300, help="random clients on top of flagged ones")
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--with-state", action="store_true", help="pass the client's state as hint")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of)
    suffix = "_with_state" if args.with_state else ""
    args.out = args.out or ROOT / "eval" / "results" / f"profile{suffix}.json"

    settings = Settings.from_env()
    repo = DataRepository.load(settings.data_dir)
    pipeline = ProfilePipeline(repo, researcher=build_researcher(settings), settings=settings)
    rng = random.Random(SEED)

    clients = repo.clients.index
    flagged = sorted(set(repo.watchlist.ClientId) & set(clients))
    others = sorted(set(clients) - set(flagged))
    sample = flagged + rng.sample(others, min(args.sample, len(others)))
    spellings = repo.portfolio.groupby("ClientId")["client_name"].agg(lambda s: sorted(set(s)))
    cases = [(cid, rng.choice(spellings[cid])) for cid in sample]
    # Watchlist entries whose ClientId is not in the portfolio: input = their own name.
    orphans = repo.watchlist[~repo.watchlist.ClientId.isin(clients)]
    cases += [(None, name) for name in orphans.client_name]

    valid_ids = (
        {f"portfolio:{x}" for x in repo.portfolio.policy_id}
        | {f"claims:{x}" for x in repo.claims.claim_id}
        | {f"watchlist:{x}" for x in repo.watchlist.watchlist_id}
        | {f"portfolio:client:{x}" for x in clients}
    )
    wl_by_client = repo.watchlist.groupby("ClientId")["watchlist_id"].agg(set).to_dict()

    rows, failures = [], []
    for true_cid, name in cases:
        t0 = time.perf_counter()
        try:
            state = repo.clients.at[true_cid, "state"] if args.with_state and true_cid else None
            profile = pipeline.build(name, as_of=as_of, state=state)
            error = None
        except Exception as exc:  # noqa: BLE001 - counted as a reliability failure
            profile, error = None, f"{type(exc).__name__}: {exc}"
        latency = (time.perf_counter() - t0) * 1000
        row = {"input": name, "true_client_id": true_cid, "latency_ms": latency, "error": error}
        if profile is None:
            rows.append(row)
            continue

        UnderwritingProfile.model_validate_json(profile.model_dump_json())  # schema round-trip
        row["resolved_client_id"] = profile.entity_resolution.client_id
        row["status"] = profile.status.value
        row["action"] = profile.assessment.recommended_action.value
        row["confidence"] = profile.assessment.confidence.level.value
        row["cost_usd"] = profile.trace.cost_usd
        bad_evidence = [
            e for e in evidence_ids(profile) if not e.startswith("web:") and e not in valid_ids
        ]
        row["bad_evidence"] = len(bad_evidence)

        linked = {f.watchlist_id: f.link.value for f in profile.risk_flags}
        if true_cid is None:  # orphan watchlist entry, reachable by name only
            expected = set(orphans[orphans.client_name == name].watchlist_id)
            row["wl_expected"], row["wl_found_any"] = len(expected), len(expected & linked.keys())
            row["wl_found_confirmed"] = None
        else:
            expected = wl_by_client.get(true_cid, set())
            row["wl_expected"] = len(expected)
            row["wl_found_any"] = len(expected & linked.keys())
            row["wl_found_confirmed"] = sum(linked.get(w) == "confirmed" for w in expected)
            row["resolved_to_true"] = profile.entity_resolution.client_id == true_cid
            if row["resolved_to_true"]:
                exp = expected_aggregates(repo, true_cid, as_of)
                got = {
                    "n_policies": profile.relationship.n_policies,
                    "premium": profile.relationship.total_premium_mxn,
                    "n_claims": profile.claims_performance.n_claims,
                    "incurred": profile.claims_performance.incurred_mxn,
                    "loss_ratio": profile.claims_performance.client_loss_ratio,
                }
                mismatches = {k: (exp[k], got[k]) for k in exp if abs(exp[k] - got[k]) > TOL}
                row["aggregates_ok"] = not mismatches
                if mismatches:
                    failures.append({"input": name, "aggregate_mismatch": mismatches})
            missed = expected - linked.keys()
            if missed:
                failures.append(
                    {
                        "input": name,
                        "true_client_id": true_cid,
                        "missed_watchlist": sorted(missed),
                        "status": row["status"],
                        "resolved": row["resolved_client_id"],
                    }
                )
        rows.append(row)

    ok = [r for r in rows if r["error"] is None]
    resolved_true = [r for r in ok if r.get("resolved_to_true")]
    wl_rows = [r for r in ok if r.get("wl_expected")]
    wl_true = [r for r in resolved_true if r.get("wl_expected")]
    lat = sorted(r["latency_ms"] for r in rows)
    costs = [r.get("cost_usd") for r in ok]
    n = len(rows)
    report = {
        "as_of": args.as_of,
        "with_state": args.with_state,
        "web_research": pipeline.researcher.provider
        if pipeline.researcher.available
        else "unavailable",
        "cases": n,
        "errors": sum(r["error"] is not None for r in rows),
        "resolved_to_true_client": round(
            len(resolved_true) / max(1, sum(1 for r in ok if r["true_client_id"])), 4
        ),
        "watchlist_recall_any_link": round(
            sum(r["wl_found_any"] for r in wl_rows)
            / max(1, sum(r["wl_expected"] for r in wl_rows)),
            4,
        ),
        "watchlist_entries_expected": sum(r["wl_expected"] for r in wl_rows),
        "watchlist_recall_confirmed_when_resolved": round(
            sum(r["wl_found_confirmed"] for r in wl_true)
            / max(1, sum(r["wl_expected"] for r in wl_true)),
            4,
        ),
        "aggregates_exact": round(
            sum(r["aggregates_ok"] for r in resolved_true) / max(1, len(resolved_true)), 4
        ),
        "profiles_with_invalid_evidence": sum(r["bad_evidence"] > 0 for r in ok),
        "schema_valid": len(ok),
        "latency_ms_p50": round(lat[n // 2], 2),
        "latency_ms_p95": round(lat[min(n - 1, int(n * 0.95))], 2),
        "cost_per_lookup_usd": (
            round(sum(costs) / len(costs), 6)
            if costs and all(c is not None for c in costs)
            else None
        ),
        "by_status": dict(Counter(r.get("status") for r in ok)),
        "by_action": dict(Counter(r.get("action") for r in ok)),
        "by_confidence": dict(Counter(r.get("confidence") for r in ok)),
        "failures": failures[:50],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "failures"}, indent=2, ensure_ascii=False
        )
    )
    print(f"failures listed: {len(failures)} -> {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
