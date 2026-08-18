from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import permitted_entity_ids, require_permission
from app.db.session import get_db
from app.models import AppSetting, AuditArea, ChecklistItem, Entity, User
from app.schemas import (
    AreaCreate,
    AreaOut,
    AreaUpdate,
    ChecklistCreate,
    ChecklistOut,
    ChecklistUpdate,
    EntityCreate,
    EntityOut,
    EntityUpdate,
    SettingUpdate,
)
from app.services.audit import record_audit

router = APIRouter(tags=["masters"])


@router.get("/entities", response_model=list[EntityOut])
def list_entities(
    user: User = Depends(require_permission("VIEW_DASHBOARD")), db: Session = Depends(get_db)
):
    stmt = select(Entity).where(
        Entity.organization_id == user.organization_id, Entity.is_active.is_(True)
    )
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        stmt = stmt.where(Entity.id.in_(allowed))
    return db.scalars(stmt.order_by(Entity.name)).all()


@router.post("/entities", response_model=EntityOut, status_code=status.HTTP_201_CREATED)
def create_entity(
    payload: EntityCreate,
    user: User = Depends(require_permission("MANAGE_ENTITIES")),
    db: Session = Depends(get_db),
):
    duplicate = db.scalar(
        select(Entity).where(
            Entity.organization_id == user.organization_id, Entity.name == payload.name.strip()
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "An entity with this name already exists")
    entity = Entity(
        organization_id=user.organization_id, name=payload.name.strip(), code=payload.code
    )
    db.add(entity)
    db.flush()
    record_audit(db, user, "ENTITY_CREATED", "entity", entity.id, new_value={"name": entity.name})
    db.commit()
    db.refresh(entity)
    return entity


@router.patch("/entities/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    user: User = Depends(require_permission("MANAGE_ENTITIES")),
    db: Session = Depends(get_db),
):
    entity = db.get(Entity, entity_id)
    if not entity or entity.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    old = {"name": entity.name, "code": entity.code, "is_active": entity.is_active}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entity, key, value.strip() if isinstance(value, str) else value)
    record_audit(
        db, user, "ENTITY_UPDATED", "entity", entity.id, old, payload.model_dump(exclude_unset=True)
    )
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/audit-areas", response_model=list[AreaOut])
def list_areas(
    user: User = Depends(require_permission("VIEW_AUDIT_ENTRY")), db: Session = Depends(get_db)
):
    return db.scalars(
        select(AuditArea)
        .where(AuditArea.organization_id == user.organization_id, AuditArea.is_active.is_(True))
        .order_by(AuditArea.sort_order, AuditArea.name)
    ).all()


@router.post("/audit-areas", response_model=AreaOut, status_code=status.HTTP_201_CREATED)
def create_area(
    payload: AreaCreate,
    user: User = Depends(require_permission("MANAGE_AUDIT_AREAS")),
    db: Session = Depends(get_db),
):
    duplicate = db.scalar(
        select(AuditArea).where(
            AuditArea.organization_id == user.organization_id,
            AuditArea.name == payload.name.strip(),
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "An audit area with this name already exists")
    area = AuditArea(organization_id=user.organization_id, **payload.model_dump())
    db.add(area)
    db.flush()
    record_audit(
        db, user, "AUDIT_AREA_CREATED", "audit_area", area.id, new_value={"name": area.name}
    )
    db.commit()
    db.refresh(area)
    return area


@router.patch("/audit-areas/{area_id}", response_model=AreaOut)
def update_area(
    area_id: uuid.UUID,
    payload: AreaUpdate,
    user: User = Depends(require_permission("MANAGE_AUDIT_AREAS")),
    db: Session = Depends(get_db),
):
    area = db.get(AuditArea, area_id)
    if not area or area.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit area not found")
    old = {"name": area.name, "sort_order": area.sort_order, "is_active": area.is_active}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(area, key, value.strip() if isinstance(value, str) else value)
    record_audit(
        db,
        user,
        "AUDIT_AREA_UPDATED",
        "audit_area",
        area.id,
        old,
        payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(area)
    return area


@router.get("/checklists", response_model=list[ChecklistOut])
def list_checklists(
    audit_area_id: uuid.UUID | None = None,
    user: User = Depends(require_permission("VIEW_AUDIT_ENTRY")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ChecklistItem)
        .join(AuditArea)
        .where(AuditArea.organization_id == user.organization_id, ChecklistItem.is_active.is_(True))
    )
    if audit_area_id:
        stmt = stmt.where(ChecklistItem.audit_area_id == audit_area_id)
    return db.scalars(stmt.order_by(ChecklistItem.sort_order)).all()


@router.post("/checklists", response_model=ChecklistOut, status_code=status.HTTP_201_CREATED)
def create_checklist_item(
    payload: ChecklistCreate,
    user: User = Depends(require_permission("MANAGE_CHECKLISTS")),
    db: Session = Depends(get_db),
):
    area = db.get(AuditArea, payload.audit_area_id)
    if not area or area.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit area not found")
    duplicate = db.scalar(
        select(ChecklistItem).where(
            ChecklistItem.audit_area_id == area.id,
            ChecklistItem.question == payload.question.strip(),
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "This checklist item already exists")
    item = ChecklistItem(**payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(db, user, "CHECKLIST_ITEM_CREATED", "checklist_item", item.id)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/checklists/{item_id}", response_model=ChecklistOut)
def update_checklist_item(
    item_id: uuid.UUID,
    payload: ChecklistUpdate,
    user: User = Depends(require_permission("MANAGE_CHECKLISTS")),
    db: Session = Depends(get_db),
):
    item = db.get(ChecklistItem, item_id)
    area = db.get(AuditArea, item.audit_area_id) if item else None
    if not item or not area or area.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checklist item not found")
    old = {
        "question": item.question,
        "is_mandatory": item.is_mandatory,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
    }
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    record_audit(
        db,
        user,
        "CHECKLIST_ITEM_UPDATED",
        "checklist_item",
        item.id,
        old,
        payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/settings")
def list_settings(
    user: User = Depends(require_permission("VIEW_DASHBOARD")), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(AppSetting).where(AppSetting.organization_id == user.organization_id)
    ).all()
    return {row.key: row.value for row in rows}


@router.put("/settings/{key}")
def update_setting(
    key: str,
    payload: SettingUpdate,
    user: User = Depends(require_permission("MANAGE_SETTINGS")),
    db: Session = Depends(get_db),
):
    if key not in {"firm", "client", "report_prefix", "financial_year"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported setting key")
    setting = db.scalar(
        select(AppSetting).where(
            AppSetting.organization_id == user.organization_id, AppSetting.key == key
        )
    )
    if not setting:
        setting = AppSetting(organization_id=user.organization_id, key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    record_audit(db, user, "SETTING_UPDATED", "setting", setting.id, new_value={"key": key})
    db.commit()
    return {"key": key, "value": setting.value}
