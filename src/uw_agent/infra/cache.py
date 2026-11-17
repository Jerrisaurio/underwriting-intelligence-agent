"""SQLite cache for web research, as a decorator around any ``WebResearcher``.

The key includes provider, model and prompt version, so changing the prompt or the model
invalidates old entries automatically. Only successful research is cached (a transient
failure must be retried next time). A corrupt or unwritable cache disables itself with a
warning instead of failing the run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict
from pathlib import Path

from uw_agent.schema.profile import PublicFinding, PublicIdentity, ResearchStatus
from uw_agent.web.models import ResearchOutcome, ResearchRequest, Usage

log = logging.getLogger(__name__)


class CachedResearcher:
    def __init__(self, inner, path: Path, ttl_days: int) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.available = inner.available
        self._ttl_s = ttl_days * 86400
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS research (key TEXT PRIMARY KEY, created REAL, payload TEXT)"
            )
        except sqlite3.Error as exc:
            log.warning("Cache disabled (%s): %s", path, exc)
            self._conn = None

    def key(self, req: ResearchRequest) -> str:
        raw = json.dumps(
            [
                self.provider,
                self.model,
                getattr(self._inner, "prompt_version", ""),
                req.name.strip().lower(),
                (req.state or "").lower(),
                req.depth,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def research(self, request: ResearchRequest) -> ResearchOutcome:
        key = self.key(request)
        cached = self._get(key)
        if cached is not None:
            return cached
        outcome = self._inner.research(request)
        if outcome.status is ResearchStatus.DONE:
            self._put(key, outcome)
        return outcome

    def _get(self, key: str) -> ResearchOutcome | None:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT created, payload FROM research WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as exc:
            log.warning("Cache read failed, disabling cache: %s", exc)
            self._conn = None
            return None
        if row is None or time.time() - row[0] > self._ttl_s:
            return None
        data = json.loads(row[1])
        return ResearchOutcome(
            status=ResearchStatus(data["status"]),
            reason=data["reason"],
            identity=PublicIdentity(**data["identity"]) if data["identity"] else None,
            findings=[PublicFinding(**f) for f in data["findings"]],
            dropped_unverified=data["dropped_unverified"],
            dropped_other_entity=data["dropped_other_entity"],
            usage=Usage(),  # a cache hit costs nothing
            provider=data["provider"],
            model=data["model"],
            cache_hit=True,
        )

    def _put(self, key: str, outcome: ResearchOutcome) -> None:
        if self._conn is None:
            return
        payload = {
            **{
                k: v
                for k, v in asdict(outcome).items()
                if k not in ("identity", "findings", "usage")
            },
            "status": outcome.status.value,
            "identity": outcome.identity.model_dump(mode="json") if outcome.identity else None,
            "findings": [f.model_dump(mode="json") for f in outcome.findings],
        }
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO research VALUES (?, ?, ?)",
                    (key, time.time(), json.dumps(payload)),
                )
                self._conn.commit()
        except sqlite3.Error as exc:
            log.warning("Cache write failed: %s", exc)
