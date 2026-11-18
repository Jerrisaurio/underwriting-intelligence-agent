"""Related-entities lookup from a curated YAML (corporate groups, historical names)."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from uw_agent.data.repository import DataRepository
from uw_agent.schema.profile import RelatedEntity

log = logging.getLogger(__name__)
DEFAULT_RELATED_FILE = Path(__file__).with_name("related_entities.yaml")


class RelatedEntities:
    def __init__(self, repo: DataRepository, path: Path | None = DEFAULT_RELATED_FILE) -> None:
        names_to_ids = repo.portfolio.groupby("client_name")["ClientId"].agg(set).to_dict()
        self._groups: list[dict] = []
        raw = (
            (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("groups", [])
            if path
            else []
        )
        for group in raw:
            members = []
            for name in group.get("members", []):
                ids = sorted(names_to_ids.get(name, set()))
                if not ids:
                    log.warning("Related entity %r not found in portfolio", name)
                members.append((name, ids))
            self._groups.append({**group, "members": members})

    def for_client(self, client_id: str) -> list[RelatedEntity]:
        out: list[RelatedEntity] = []
        for group in self._groups:
            if not any(client_id in ids for _, ids in group["members"]):
                continue
            for name, ids in group["members"]:
                if client_id in ids:
                    continue
                out.append(
                    RelatedEntity(
                        name=name,
                        relation=group["relation"],
                        group=group["group"],
                        client_ids=ids,
                        note=group.get("note"),
                    )
                )
        return out
