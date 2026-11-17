"""Web-research evaluation on the hand-labelled set eval/web_cases.yaml.

Without OPENAI_API_KEY and UW_OPENAI_MODEL it reports "not run" and exits 0 (the web layer is
optional; the internal evaluation does not depend on it). With them, it runs each case through
the full pipeline (cache bypassed, so cost and latency are real) and reports identity accuracy,
industry accuracy, synthetic-control false positives, dropped findings, cost and latency, and
prints the watchlist checks for human review.

Run:  uv run python eval/run_web_eval.py [--as-of 2025-09-28]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uw_agent.agent import ProfilePipeline  # noqa: E402
from uw_agent.agent.conflicts import WEB_CATEGORY_TO_FLAG  # noqa: E402
from uw_agent.config import Settings  # noqa: E402
from uw_agent.data import DataRepository  # noqa: E402
from uw_agent.schema.profile import ResearchStatus  # noqa: E402
from uw_agent.web import build_researcher  # noqa: E402

CASES = ROOT / "eval" / "web_cases.yaml"
OUT = ROOT / "eval" / "results" / "web.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2025-09-28")
    args = ap.parse_args()

    settings = Settings.from_env()
    researcher = build_researcher(settings, use_cache=False)
    if not researcher.available:
        report = {
            "status": "not_run",
            "reason": getattr(researcher, "reason", "web research unavailable"),
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Web evaluation NOT RUN: {report['reason']}")
        return

    repo = DataRepository.load(settings.data_dir)
    pipeline = ProfilePipeline(repo, researcher=researcher, settings=settings)
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    rows = []
    for case in cases:
        t0 = time.perf_counter()
        p = pipeline.build(case["name"], as_of=date.fromisoformat(args.as_of))
        web = p.public_information
        found = bool(web.identity and web.identity.found_publicly)
        confirmed = [f for f in web.findings if f.entity_match == "confirmed"]
        rows.append(
            {
                "name": case["name"],
                "web_status": web.status.value,
                "depth": web.depth,
                "found_ok": found == case["expect_found"]
                if web.status is ResearchStatus.DONE
                else None,
                "industry": web.identity.industry if web.identity else None,
                "industry_ok": (
                    None
                    if not case.get("industries") or web.status is not ResearchStatus.DONE
                    else (web.identity.industry if web.identity else None) in case["industries"]
                ),
                "synthetic_false_positive": bool(case.get("synthetic") and confirmed),
                "findings": len(web.findings),
                "dropped_unverified": web.dropped_unverified,
                "dropped_other_entity": web.dropped_other_entity,
                "cost_usd": p.trace.cost_usd,
                "latency_s": round(time.perf_counter() - t0, 2),
                "watchlist_review": [
                    {
                        "watchlist_id": flag.watchlist_id,
                        "flag": f"{flag.flag_type}/{flag.severity}/{flag.status}",
                        "link": flag.link.value,
                        "public_findings": [
                            {
                                "claim": f.claim,
                                "stance": f.stance,
                                "date": str(f.published_date),
                                "url": f.url,
                            }
                            for f in web.findings
                            if WEB_CATEGORY_TO_FLAG.get(f.risk_category) == flag.flag_type
                        ],
                    }
                    for flag in p.risk_flags
                ],
                "action": p.assessment.recommended_action.value,
            }
        )

    def rate(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    costs = [r["cost_usd"] for r in rows]
    report = {
        "status": "done",
        "model": researcher.model,
        "cases": len(rows),
        "failed": sum(r["web_status"] == "failed" for r in rows),
        "identity_accuracy": rate("found_ok"),
        "industry_accuracy": rate("industry_ok"),
        "synthetic_false_positives": sum(r["synthetic_false_positive"] for r in rows),
        "dropped_unverified_total": sum(r["dropped_unverified"] for r in rows),
        "dropped_other_entity_total": sum(r["dropped_other_entity"] for r in rows),
        "cost_per_lookup_usd": (
            round(sum(costs) / len(costs), 6) if all(c is not None for c in costs) else None
        ),
        "latency_s_avg": round(sum(r["latency_s"] for r in rows) / len(rows), 2),
        "cases_detail": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases_detail"}, indent=2))
    print(f"Watchlist checks for human review -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
