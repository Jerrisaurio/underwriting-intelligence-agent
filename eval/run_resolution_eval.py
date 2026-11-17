"""Evaluate the entity resolver against eval/datasets/resolution_cases.jsonl.

Each case gets one verdict:

  correct          right answer with the right level of certainty
  correct_flagged  right ClientId, but flagged as ambiguous when the name was unique
  over_cautious    returned AMBIGUOUS (true client among candidates) for a unique name
  missed_ambiguity unflagged RESOLVED on a name shared by several ClientIds
                   (the chosen ClientId is one of them)
  wrong_flagged    picked a wrong ClientId, but flagged the ambiguity
  false_resolution picked a wrong ClientId *without* flagging (the worst outcome:
                   a confident-looking profile of the wrong company)
  miss             NOT_FOUND / INVALID when a client exists
  false_positive   returned candidates or a client for a non-client or invalid input

Headline metrics: accuracy (correct + correct_flagged), false_resolution rate
(target ~0), candidate recall (true client among the returned candidates) and
calibration (accuracy per entity_confidence bucket).

Run:  uv run python eval/run_resolution_eval.py [--out eval/results/resolution.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uw_agent.config import Settings  # noqa: E402
from uw_agent.data import DataRepository  # noqa: E402
from uw_agent.resolution import EntityResolver, ResolutionOutcome  # noqa: E402

CASES = ROOT / "eval" / "datasets" / "resolution_cases.jsonl"
CONFIDENCE_BUCKETS = [(0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]


def verdict(case: dict, res) -> str:
    out = res.outcome
    acceptable = set(case["acceptable_client_ids"])
    cand_ids = {c.client_id for c in res.candidates}
    expected = case["expected_class"]

    if expected == "invalid":
        return "correct" if out is ResolutionOutcome.INVALID_INPUT else "false_positive"
    if expected == "not_found":
        return "correct" if out is ResolutionOutcome.NOT_FOUND else "false_positive"
    if out in (ResolutionOutcome.NOT_FOUND, ResolutionOutcome.INVALID_INPUT):
        return "miss"

    if expected == "unique":
        if out is ResolutionOutcome.RESOLVED:
            return "correct" if res.client_id in acceptable else "false_resolution"
        if out is ResolutionOutcome.RESOLVED_WITH_AMBIGUITY:
            return "correct_flagged" if res.client_id in acceptable else "wrong_flagged"
        return "over_cautious" if acceptable & cand_ids else "wrong_flagged"

    # expected == "ambiguous"
    if out is ResolutionOutcome.RESOLVED:
        return "missed_ambiguity" if res.client_id in acceptable else "false_resolution"
    if out is ResolutionOutcome.RESOLVED_WITH_AMBIGUITY and res.client_id not in acceptable:
        return "wrong_flagged"
    return "correct" if acceptable & cand_ids else "wrong_flagged"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "resolution.json")
    args = parser.parse_args()

    repo = DataRepository.load(Settings.from_env().data_dir)
    resolver = EntityResolver.from_repository(repo)
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]

    rows = []
    for case in cases:
        t0 = time.perf_counter()
        res = resolver.resolve(case["input"], state=case["state_hint"])
        latency_ms = (time.perf_counter() - t0) * 1000
        v = verdict(case, res)
        acceptable = set(case["acceptable_client_ids"])
        rows.append(
            {
                **case,
                "outcome": res.outcome.value,
                "client_id": res.client_id,
                "entity_confidence": res.entity_confidence,
                "n_candidates": len(res.candidates),
                "candidate_hit": bool(acceptable & {c.client_id for c in res.candidates}),
                "verdict": v,
                "ok": v in ("correct", "correct_flagged"),
                "latency_ms": round(latency_ms, 2),
            }
        )

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    def summarize(rs: list[dict]) -> dict:
        n = len(rs)
        positives = [r for r in rs if r["expected_class"] in ("unique", "ambiguous")]
        lat = sorted(r["latency_ms"] for r in rs)
        return {
            "n": n,
            "accuracy": round(sum(r["ok"] for r in rs) / n, 4),
            "false_resolution_rate": round(
                sum(r["verdict"] == "false_resolution" for r in rs) / n, 4
            ),
            "candidate_recall": (
                round(sum(r["candidate_hit"] for r in positives) / len(positives), 4)
                if positives
                else None
            ),
            "verdicts": dict(Counter(r["verdict"] for r in rs)),
            "latency_ms_p50": lat[n // 2],
            "latency_ms_p95": lat[min(n - 1, int(n * 0.95))],
        }

    calibration = []
    resolved = [r for r in rows if r["client_id"]]
    for lo, hi in CONFIDENCE_BUCKETS:
        bucket = [r for r in resolved if lo <= r["entity_confidence"] < hi]
        if bucket:
            correct = sum(r["client_id"] in r["acceptable_client_ids"] for r in bucket)
            calibration.append(
                {
                    "confidence": f"[{lo}, {min(hi, 1.0)})",
                    "n": len(bucket),
                    "precision": round(correct / len(bucket), 4),
                }
            )

    report = {
        "overall": summarize(rows),
        "by_category": {cat: summarize(rs) for cat, rs in sorted(by_cat.items())},
        "calibration": calibration,
        "failures": [r for r in rows if not r["ok"]],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'category':<16}{'n':>5}{'acc':>8}{'false_res':>11}{'cand_rec':>10}  verdicts")
    for cat, s in [*report["by_category"].items(), ("OVERALL", report["overall"])]:
        rec = "-" if s["candidate_recall"] is None else f"{s['candidate_recall']:.1%}"
        print(
            f"{cat:<16}{s['n']:>5}{s['accuracy']:>8.1%}{s['false_resolution_rate']:>11.1%}"
            f"{rec:>10}  {s['verdicts']}"
        )
    print("\nCalibration (resolved cases):")
    for b in calibration:
        print(f"  confidence {b['confidence']:<12} n={b['n']:<5} precision={b['precision']:.1%}")
    o = report["overall"]
    print(
        f"\nLatency p50={o['latency_ms_p50']}ms p95={o['latency_ms_p95']}ms  "
        f"-> {args.out.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
