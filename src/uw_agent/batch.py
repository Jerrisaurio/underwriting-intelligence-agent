"""Batch mode: profile a list of companies and write one JSON profile per line.

Reliability rules:
- Every company runs inside its own try/except: a failure becomes a ``status: ERROR`` line and
  the batch continues.
- Identical inputs (same normalized name and state) are profiled once per run.
- Output is appended in input order; re-running with an existing output file resumes, skipping
  inputs already written (unless ``overwrite``).
- The summary is computed from the whole output file, so totals are right after a resume.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from uw_agent.agent.pipeline import ProfilePipeline
from uw_agent.resolution import normalize_name
from uw_agent.resolution.normalize import normalize_state

log = logging.getLogger(__name__)


class BatchInputError(ValueError):
    """The input file is missing, empty or malformed."""


@dataclass(frozen=True)
class BatchItem:
    name: str
    state: str | None = None

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        n = normalize_name(self.name)
        return n.core, n.legal_family, normalize_state(self.state)

    @property
    def output_key(self) -> tuple[str, str | None]:
        return self.name, self.state


def read_inputs(path: Path) -> list[BatchItem]:
    if not path.exists():
        raise BatchInputError(f"No existe el archivo de entrada: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(text.splitlines())
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise BatchInputError("El CSV debe tener una columna 'name' (y opcionalmente 'state')")
        items = [
            BatchItem(row["name"].strip(), (row.get("state") or "").strip() or None)
            for row in reader
            if (row.get("name") or "").strip()
        ]
    else:
        items = [
            BatchItem(line.strip())
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if not items:
        raise BatchInputError(f"El archivo de entrada no contiene nombres: {path}")
    return items


def _done_keys(out: Path) -> set[tuple[str, str | None]]:
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                q = json.loads(line)["query"]
                done.add((q["input_name"], q["state_hint"]))
    return done


def run_batch(
    pipeline: ProfilePipeline,
    items: list[BatchItem],
    out: Path,
    as_of: date,
    workers: int = 4,
    overwrite: bool = False,
) -> dict:
    if overwrite and out.exists():
        out.unlink()
    done = _done_keys(out)
    pending = [i for i in items if i.output_key not in done]
    unique: dict[tuple, BatchItem] = {}
    for item in pending:
        unique.setdefault(item.key, item)
    log.info(
        "Batch: %d inputs, %d already done, %d unique to profile",
        len(items),
        len(items) - len(pending),
        len(unique),
    )

    def profile(item: BatchItem):
        try:
            return pipeline.build(item.name, as_of=as_of, state=item.state)
        except Exception as exc:  # noqa: BLE001 - isolation is the point of batch mode
            log.exception("Profile failed for %r", item.name)
            return pipeline.error_profile(item.name, as_of, item.state, exc)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = dict(zip(unique, pool.map(profile, unique.values()), strict=True))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for item in pending:
            profile_ = results[item.key]
            if (item.name, item.state) != (profile_.query.input_name, profile_.query.state_hint):
                # A duplicate reuses the computation but keeps its own query echo.
                profile_ = profile_.model_copy(
                    update={
                        "query": profile_.query.model_copy(
                            update={"input_name": item.name, "state_hint": item.state}
                        )
                    }
                )
            fh.write(profile_.model_dump_json() + "\n")

    summary = summarize(out)
    summary["this_run"] = {
        "inputs": len(items),
        "skipped_already_done": len(items) - len(pending),
        "profiled": len(unique),
        "deduplicated": len(pending) - len(unique),
    }
    out.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def summarize(out: Path) -> dict:
    profiles = [
        json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    traces = [p["trace"] for p in profiles]
    latencies = sorted(t["duration_ms"] for t in traces)
    costs = [t["cost_usd"] for t in traces]
    priced = all(c is not None for c in costs)
    n = len(profiles)

    def pct(q: float):
        return latencies[min(n - 1, int(n * q))] if latencies else None

    return {
        "profiles": n,
        "by_status": dict(Counter(p["status"] for p in profiles)),
        "by_action": dict(Counter(p["assessment"]["recommended_action"] for p in profiles)),
        "by_web_status": dict(Counter(p["public_information"]["status"] for p in profiles)),
        "errors": [p["query"]["input_name"] for p in profiles if p["status"] == "ERROR"],
        "llm_calls": sum(t["llm_calls"] for t in traces),
        "web_search_calls": sum(t["web_search_calls"] for t in traces),
        "input_tokens": sum(t["input_tokens"] for t in traces),
        "output_tokens": sum(t["output_tokens"] for t in traces),
        "total_cost_usd": round(sum(costs), 6) if priced else None,
        "cost_per_lookup_usd": round(sum(costs) / n, 6) if priced and n else None,
        "latency_ms_p50": pct(0.5),
        "latency_ms_p95": pct(0.95),
    }
