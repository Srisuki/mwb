from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditArea, ChecklistItem, Entity, Organization


def _literal(source: str, name: str, terminator: str = ";"):
    match = re.search(rf"const\s+{re.escape(name)}\s*=", source)
    if not match:
        raise ValueError(f"Legacy constant not found: {name}")
    start = match.end()
    if name == "checklist":
        end = source.index("\n};", start) + 2
    else:
        end = source.index(terminator, start)
    return ast.literal_eval(source[start:end].strip())


def read_legacy_baseline(path: str | Path) -> tuple[list[str], list[str], dict[str, list[str]]]:
    source = Path(path).read_text(encoding="utf-8")
    entities = _literal(source, "defaultEntities")
    areas = _literal(source, "defaultAreas")
    checklist = _literal(source, "checklist")
    if (
        not isinstance(entities, list)
        or not isinstance(areas, list)
        or not isinstance(checklist, dict)
    ):
        raise TypeError("Legacy baseline has an unexpected structure")
    return entities, areas, checklist


def seed_legacy_baseline(
    db: Session, organization: Organization, path: str | Path
) -> dict[str, int]:
    entity_names, area_names, checklist = read_legacy_baseline(path)
    for name in entity_names:
        existing = db.scalar(
            select(Entity).where(Entity.organization_id == organization.id, Entity.name == name)
        )
        if not existing:
            db.add(Entity(organization_id=organization.id, name=name))
    db.flush()

    for area_order, name in enumerate(area_names, start=1):
        area = db.scalar(
            select(AuditArea).where(
                AuditArea.organization_id == organization.id, AuditArea.name == name
            )
        )
        if not area:
            area = AuditArea(organization_id=organization.id, name=name, sort_order=area_order)
            db.add(area)
            db.flush()
        else:
            area.sort_order = area_order
        questions = checklist.get(name, ["General verification completed"])
        for item_order, question in enumerate(questions, start=1):
            item = db.scalar(
                select(ChecklistItem).where(
                    ChecklistItem.audit_area_id == area.id, ChecklistItem.question == question
                )
            )
            if not item:
                db.add(
                    ChecklistItem(
                        audit_area_id=area.id,
                        question=question,
                        is_mandatory=True,
                        sort_order=item_order,
                    )
                )
            else:
                item.sort_order = item_order
    db.commit()
    return {
        "entities": len(entity_names),
        "areas": len(area_names),
        "checklist_items": sum(len(items) for items in checklist.values()),
    }
