"""SPLIT: map cardholders to entities. Origin is copied, never deleted."""

from __future__ import annotations

from cc_coder.models import EntityMapRow, Transaction
from cc_coder.normalize import slug_entity


def load_entity_map(rows: list[dict[str, str]]) -> list[EntityMapRow]:
    mapping: list[EntityMapRow] = []
    for row in rows:
        mapping.append(
            EntityMapRow(
                first_name=(row.get("first_name") or "").strip(),
                full_name=(row.get("full_name") or "").strip(),
                entity=(row.get("entity") or "").strip(),
            )
        )
    return mapping


def apply_entity_map(
    rows: list[Transaction], mapping: list[EntityMapRow]
) -> tuple[list[Transaction], dict[str, list[Transaction]], list[Transaction]]:
    by_first = {item.first_name.lower(): item.entity for item in mapping}
    tagged: list[Transaction] = []
    unmapped: list[Transaction] = []
    for row in rows:
        entity = by_first.get(row.cardholder_first.lower(), "")
        row.entity = entity
        tagged.append(row)
        if not entity:
            unmapped.append(row)

    by_entity: dict[str, list[Transaction]] = {}
    for row in tagged:
        key = row.entity or "UNMAPPED"
        by_entity.setdefault(key, []).append(row)
    return tagged, by_entity, unmapped


def entity_slug(entity: str) -> str:
    return slug_entity(entity)
