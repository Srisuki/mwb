from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AuditArea,
    AuditPlan,
    ChecklistItem,
    Entity,
    Observation,
    ObservationHistory,
    ObservationStatus,
    Report,
    ReportLock,
    ReportStatus,
    RiskLevel,
    User,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/migrations", tags=["migration"])


def enum_value(enum_class, value, fallback):
    try:
        return enum_class(value)
    except (ValueError, TypeError):
        return fallback


@router.post("/legacy-json")
async def import_legacy_json(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("MANAGE_SETTINGS")),
    db: Session = Depends(get_db),
):
    payload = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Backup exceeds import limit")
    try:
        source = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid JSON backup") from None
    if not isinstance(source, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Backup root must be an object")
    report = {
        "users_imported": 0,
        "entities_imported": 0,
        "plans_imported": 0,
        "observations_imported": 0,
        "documents_imported": 0,
        "locks_imported": 0,
        "errors": [],
        "warnings": [],
    }
    if source.get("users"):
        report["warnings"].append(
            "Legacy users and plaintext PINs were not imported; provision users securely."
        )

    entities = {}
    for raw_name in source.get("entities", []):
        name = str(raw_name).strip()
        if not name:
            report["warnings"].append("Skipped blank entity name")
            continue
        entity = db.scalar(
            select(Entity).where(
                Entity.organization_id == user.organization_id, Entity.name == name
            )
        )
        if not entity:
            entity = Entity(organization_id=user.organization_id, name=name)
            db.add(entity)
            db.flush()
            report["entities_imported"] += 1
        entities[name] = entity
    for entity in db.scalars(
        select(Entity).where(Entity.organization_id == user.organization_id)
    ).all():
        entities.setdefault(entity.name, entity)

    areas = {
        item.name: item
        for item in db.scalars(
            select(AuditArea).where(AuditArea.organization_id == user.organization_id)
        ).all()
    }
    checklists = {
        (area.name, item.question): item
        for area, item in db.execute(
            select(AuditArea, ChecklistItem)
            .join(ChecklistItem)
            .where(AuditArea.organization_id == user.organization_id)
        ).all()
    }
    plans = {}
    for index, raw in enumerate(source.get("plans", []), start=1):
        entity, area = entities.get(raw.get("entity")), areas.get(raw.get("area"))
        if not entity or not area:
            report["errors"].append(f"Plan {index}: unmatched entity or audit area")
            continue
        period = str(raw.get("period", ""))
        try:
            due_date = date.fromisoformat(raw.get("due") or date.today().isoformat())
        except ValueError:
            due_date = date.today()
            report["warnings"].append(f"Plan {index}: invalid due date replaced")
        plan = db.scalar(
            select(AuditPlan).where(
                AuditPlan.entity_id == entity.id,
                AuditPlan.period == period,
                AuditPlan.audit_area_id == area.id,
            )
        )
        if not plan:
            plan = AuditPlan(
                organization_id=user.organization_id,
                entity_id=entity.id,
                audit_area_id=area.id,
                period=period,
                due_date=due_date,
                status="COMPLETED" if raw.get("status") == "Completed" else "PENDING",
                created_by_id=user.id,
            )
            db.add(plan)
            db.flush()
            report["plans_imported"] += 1
        plans[(entity.name, period, area.name)] = plan

    for index, raw in enumerate(source.get("obs", []), start=1):
        entity, area = entities.get(raw.get("entity")), areas.get(raw.get("area"))
        checklist = checklists.get((raw.get("area"), raw.get("check")))
        if not entity or not area or not checklist:
            report["errors"].append(
                f"Observation {index}: unmatched entity, area, or checklist text"
            )
            continue
        period = str(raw.get("period", ""))
        if db.scalar(
            select(Observation.id).where(
                Observation.entity_id == entity.id,
                Observation.period == period,
                Observation.checklist_item_id == checklist.id,
            )
        ):
            report["warnings"].append(f"Observation {index}: duplicate skipped")
            continue
        observation = Observation(
            organization_id=user.organization_id,
            entity_id=entity.id,
            audit_plan_id=(
                plans.get((entity.name, period, area.name))
                or plans.get((entity.name, period, "All Areas"))
            ).id
            if (
                plans.get((entity.name, period, area.name))
                or plans.get((entity.name, period, "All Areas"))
            )
            else None,
            audit_area_id=area.id,
            checklist_item_id=checklist.id,
            period=period,
            risk=enum_value(RiskLevel, raw.get("risk"), RiskLevel.LOW),
            status=enum_value(ObservationStatus, raw.get("status"), ObservationStatus.PENDING),
            observation=str(raw.get("observation") or "").strip() or "Legacy response unavailable",
            remark=str(raw.get("remark") or ""),
            responsible_person=str(raw.get("responsible") or ""),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(observation)
        db.flush()
        db.add(
            ObservationHistory(
                observation_id=observation.id,
                changed_by_id=user.id,
                action="LEGACY_IMPORTED",
                new_value={"legacy_id": str(raw.get("id", ""))},
            )
        )
        report["observations_imported"] += 1

    if source.get("docs"):
        report["warnings"].append(
            f"{len(source['docs'])} legacy document references require manual file reconciliation; no file bytes existed in the backup."
        )
    for index, raw in enumerate(source.get("locks", []), start=1):
        entity = entities.get(raw.get("entity"))
        period = str(raw.get("period", ""))
        if not entity or not period:
            report["errors"].append(f"Lock {index}: unmatched entity or period")
            continue
        if db.scalar(
            select(ReportLock.id).where(
                ReportLock.entity_id == entity.id, ReportLock.period == period
            )
        ):
            report["warnings"].append(f"Lock {index}: existing lock skipped")
            continue
        report_number = str(raw.get("reportNo") or f"LEGACY/{entity.id}/{period}")
        locked_report = Report(
            organization_id=user.organization_id,
            entity_id=entity.id,
            period=period,
            report_type=str(raw.get("type") or "Monthly Internal Audit Report"),
            report_number=report_number,
            status=ReportStatus.LOCKED,
            snapshot={"legacy_import": True},
            generated_by_id=user.id,
            approved_by_id=user.id,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(locked_report)
        db.flush()
        db.add(
            ReportLock(
                report_id=locked_report.id, entity_id=entity.id, period=period, locked_by_id=user.id
            )
        )
        db.query(Observation).filter(
            Observation.entity_id == entity.id, Observation.period == period
        ).update({"locked_at": datetime.now(timezone.utc)})
        report["locks_imported"] += 1
    record_audit(
        db,
        user,
        "LEGACY_JSON_IMPORTED",
        "organization",
        user.organization_id,
        new_value={
            key: value for key, value in report.items() if key not in {"errors", "warnings"}
        },
    )
    db.commit()
    return report
