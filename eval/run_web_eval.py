"""Web-research evaluation on the hand-labelled set eval/web_cases.yaml.

Without OPENAI_API_KEY and a model it reports "not run" and exits 0 (the web layer is optional;
the internal evaluation does not depend on it). With them, it runs each case through the full
pipeline (cache bypassed, so cost and latency are real) ``--runs`` times and reports:

- identity accuracy (verified identity matches the label), industry accuracy (closed list),
  synthetic-control false positives (a fictitious company must not be verified);
- depth used, web-search calls, input/output tokens, cost (when prices are configured);
- run-to-run agreement on verified identity, industry and recommended action;
- for every watchlist flag linked to a profile, the public findings of the same risk category,
  for human review (flags are read from the data at run time; nothing is stored in the case file).

Run:  uv run python eval/run_web_eval.py [--model gpt-4o-mini] [--runs 2] [--as-of 2025-09-28]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import replace
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


def one_run(pipeline, case, as_of):
    t0 = time.perf_counter()
    p = pipeline.build(case["name"], as_of=as_of)
    web, tr = p.public_information, p.trace
    done = web.status is ResearchStatus.DONE
    verified = web.identity_verified
    industry = web.identity.industry if web.identity else None
    return {
        "web_status": web.status.value,
        "depth": web.depth,
        "identity_verified": verified,
        "found_ok": (verified == case["expect_found"]) if done else None,
        "industry": industry,
        "industry_ok": (
            None if not case.get("industries") or not done else industry in case["industries"]
        ),
        "synthetic_false_positive": bool(case.get("synthetic") and verified),
        "findings": len(web.findings),
        "adverse_findings": sum(f.stance == "negative" for f in web.findings),
        "dropped_unverified": web.dropped_unverified,
        "dropped_other_entity": web.dropped_other_entity,
        "web_search_calls": tr.web_search_calls,
        "input_tokens": tr.input_tokens,
        "output_tokens": tr.output_tokens,
        "cost_usd": tr.cost_usd,
        "latency_s": round(time.perf_counter() - t0, 2),
        "action": p.assessment.recommended_action.value,
        "rules": [r.rule_id for r in p.assessment.triggered_rules],
        "conflicts": [c.type.value for c in p.conflicts],
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
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2025-09-28")
    ap.add_argument("--model", default=None, help="override UW_OPENAI_MODEL")
    ap.add_argument("--runs", type=int, default=1, help="runs per company (consistency)")
    args = ap.parse_args()

    settings = Settings.from_env()
    if args.model:
        settings = replace(settings, openai_model=args.model)
    researcher = build_researcher(settings, use_cache=False)
    slug = re.sub(r"[^a-z0-9.-]+", "-", (settings.openai_model or "none").lower())
    out = ROOT / "eval" / "results" / f"web_{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not researcher.available:
        report = {"status": "not_run", "reason": getattr(researcher, "reason", "unavailable")}
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Web evaluation NOT RUN: {report['reason']}")
        return

    repo = DataRepository.load(settings.data_dir)
    pipeline = ProfilePipeline(repo, researcher=researcher, settings=settings)
    as_of = date.fromisoformat(args.as_of)
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]

    detail = []
    for case in cases:
        runs = [one_run(pipeline, case, as_of) for _ in range(args.runs)]
        keys = [(r["identity_verified"], r["industry"], r["action"]) for r in runs]
        detail.append({"name": case["name"], "agree": len(set(keys)) == 1, "runs": runs})

    researched = [r for d in detail for r in d["runs"] if r["web_status"] == "done"]
    every = [r for d in detail for r in d["runs"]]

    def rate(key, rows=researched):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    def avg(key, rows=researched):
        return round(sum(r[key] for r in rows) / len(rows), 2) if rows else None

    costs = [r["cost_usd"] for r in researched]
    t2 = [r for r in researched if r["depth"] == "T2"]
    report = {
        "status": "done",
        "model": settings.openai_model,
        "cases": len(detail),
        "runs_per_case": args.runs,
        "lookups": len(every),
        "researched_lookups": len(researched),
        "failed": sum(r["web_status"] == "failed" for r in every),
        "identity_accuracy": rate("found_ok"),
        "industry_accuracy": rate("industry_ok"),
        "synthetic_false_positives": sum(r["synthetic_false_positive"] for r in every),
        "run_agreement": round(sum(d["agree"] for d in detail) / len(detail), 4),
        "avg_web_search_calls": avg("web_search_calls"),
        "avg_web_search_calls_t2": avg("web_search_calls", t2),
        "avg_findings": avg("findings"),
        "adverse_findings_total": sum(r["adverse_findings"] for r in researched),
        "dropped_unverified_total": sum(r["dropped_unverified"] for r in researched),
        "dropped_other_entity_total": sum(r["dropped_other_entity"] for r in researched),
        "avg_input_tokens": avg("input_tokens"),
        "avg_output_tokens": avg("output_tokens"),
        "cost_per_lookup_usd": (
            round(sum(costs) / len(costs), 6)
            if costs and all(c is not None for c in costs)
            else None
        ),
        "avg_latency_s": avg("latency_s"),
        "cases_detail": detail,
    }
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases_detail"}, indent=2))
    print(f"Detail and watchlist review -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
