from __future__ import annotations

import csv
import uuid
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    ensure_entity_access,
    ensure_same_organization,
    permitted_entity_ids,
    require_permission,
)
from app.db.session import get_db
from app.models import (
    AuditArea,
    AuditPlan,
    AuditPlanAssignment,
    ChecklistItem,
    Entity,
    ManagementReply,
    Observation,
    ObservationHistory,
    ObservationStatus,
    PlanStatus,
    ReportLock,
    User,
)
from app.schemas import (
    CarryForwardRequest,
    FullMonthPlanCreate,
    ObservationCreate,
    ObservationOut,
    ObservationUpdate,
    PlanCreate,
    PlanOut,
    PlanUpdate,
    ReplyCreate,
)
from app.services.audit import record_audit

router = APIRouter(tags=["audits"])


def locked(db: Session, entity_id: uuid.UUID, period: str) -> bool:
    return (
        db.scalar(
            select(ReportLock.id).where(
                ReportLock.entity_id == entity_id, ReportLock.period == period
            )
        )
        is not None
    )


def update_plan_completion(db: Session, observation: Observation) -> None:
    plan = db.scalar(
        select(AuditPlan).where(
            AuditPlan.entity_id == observation.entity_id,
            AuditPlan.audit_area_id == observation.audit_area_id,
            AuditPlan.period == observation.period,
            AuditPlan.is_active.is_(True),
        )
    )
    if not plan:
        return
    mandatory = (
        db.scalar(
            select(func.count(ChecklistItem.id)).where(
                ChecklistItem.audit_area_id == observation.audit_area_id,
                ChecklistItem.is_active.is_(True),
                ChecklistItem.is_mandatory.is_(True),
            )
        )
        or 0
    )
    completed = (
        db.scalar(
            select(func.count(Observation.id))
            .join(ChecklistItem, ChecklistItem.id == Observation.checklist_item_id)
            .where(
                Observation.entity_id == observation.entity_id,
                Observation.audit_area_id == observation.audit_area_id,
                Observation.period == observation.period,
                Observation.is_active.is_(True),
                ChecklistItem.is_mandatory.is_(True),
                func.length(func.trim(Observation.observation)) > 0,
            )
        )
        or 0
    )
    next_status = PlanStatus.COMPLETED if mandatory and completed >= mandatory else PlanStatus.IN_PROGRESS
    if plan.status != next_status:
        plan.status = next_status
        plan.version += 1


@router.get("/audit-plans", response_model=list[PlanOut])
def list_plans(
    period: str | None = None,
    user: User = Depends(require_permission("VIEW_AUDIT_PLAN")),
    db: Session = Depends(get_db),
):
    stmt = select(AuditPlan).where(
        AuditPlan.organization_id == user.organization_id, AuditPlan.is_active.is_(True)
    )
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        stmt = stmt.where(AuditPlan.entity_id.in_(allowed))
    if period:
        stmt = stmt.where(AuditPlan.period == period)
    return db.scalars(stmt.order_by(AuditPlan.period.desc(), AuditPlan.due_date)).all()


@router.post("/audit-plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    user: User = Depends(require_permission("CREATE_AUDIT_PLAN")),
    db: Session = Depends(get_db),
):
    ensure_entity_access(db, payload.entity_id, user)
    area = db.get(AuditArea, payload.audit_area_id)
    if not area or area.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity or audit area not found")
    if locked(db, payload.entity_id, payload.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "This entity and period is locked")
    plan = AuditPlan(
        organization_id=user.organization_id,
        entity_id=payload.entity_id,
        audit_area_id=payload.audit_area_id,
        period=payload.period,
        due_date=payload.due_date,
        created_by_id=user.id,
    )
    db.add(plan)
    db.flush()
    for assignee_id in set(payload.assigned_user_ids):
        assignee = db.get(User, assignee_id)
        assignee_scope = permitted_entity_ids(assignee) if assignee else set()
        if (
            not assignee
            or assignee.organization_id != user.organization_id
            or (assignee_scope is not None and entity.id not in assignee_scope)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid assignee")
        db.add(AuditPlanAssignment(audit_plan_id=plan.id, user_id=assignee_id))
    record_audit(
        db, user, "AUDIT_PLAN_CREATED", "audit_plan", plan.id, new_value={"period": plan.period}
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.post(
    "/audit-plans/full-month", response_model=list[PlanOut], status_code=status.HTTP_201_CREATED
)
def create_full_month_plan(
    payload: FullMonthPlanCreate,
    user: User = Depends(require_permission("CREATE_AUDIT_PLAN")),
    db: Session = Depends(get_db),
):
    entity = ensure_entity_access(db, payload.entity_id, user)
    if locked(db, entity.id, payload.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "This entity and period is locked")
    areas = db.scalars(
        select(AuditArea).where(
            AuditArea.organization_id == user.organization_id, AuditArea.is_active.is_(True)
        )
    ).all()
    created = []
    for area in areas:
        plan = db.scalar(
            select(AuditPlan).where(
                AuditPlan.entity_id == entity.id,
                AuditPlan.period == payload.period,
                AuditPlan.audit_area_id == area.id,
            )
        )
        if not plan:
            plan = AuditPlan(
                organization_id=user.organization_id,
                entity_id=entity.id,
                audit_area_id=area.id,
                period=payload.period,
                due_date=payload.due_date,
                created_by_id=user.id,
            )
            db.add(plan)
            db.flush()
            for assignee_id in set(payload.assigned_user_ids):
                assignee = db.get(User, assignee_id)
                assignee_scope = permitted_entity_ids(assignee) if assignee else set()
                if (
                    not assignee
                    or assignee.organization_id != user.organization_id
                    or (assignee_scope is not None and entity.id not in assignee_scope)
                ):
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid assignee")
                db.add(AuditPlanAssignment(audit_plan_id=plan.id, user_id=assignee_id))
        created.append(plan)
    record_audit(
        db,
        user,
        "FULL_MONTH_PLAN_CREATED",
        "entity",
        entity.id,
        new_value={"period": payload.period, "areas": len(created)},
    )
    db.commit()
    return created


@router.patch("/audit-plans/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    user: User = Depends(require_permission("EDIT_AUDIT_PLAN")),
    db: Session = Depends(get_db),
):
    plan = db.get(AuditPlan, plan_id)
    if not plan or plan.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit plan not found")
    ensure_entity_access(db, plan.entity_id, user)
    if locked(db, plan.entity_id, plan.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "This entity and period is locked")
    if payload.expected_version is not None and payload.expected_version != plan.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Audit plan was changed by another user; reload and retry"
        )
    old = {"status": plan.status.value, "due_date": plan.due_date.isoformat()}
    for key, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(plan, key, value)
    plan.version += 1
    record_audit(
        db,
        user,
        "AUDIT_PLAN_UPDATED",
        "audit_plan",
        plan.id,
        old_value=old,
        new_value={"status": plan.status.value, "due_date": plan.due_date.isoformat()},
    )
    db.commit()
    db.refresh(plan)
    return plan


def previous_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    month -= 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year:04d}-{month:02d}"


@router.post("/audit-plans/carry-forward")
def carry_forward(
    payload: CarryForwardRequest,
    user: User = Depends(require_permission("CREATE_OBSERVATION")),
    db: Session = Depends(get_db),
):
    entity = ensure_entity_access(db, payload.entity_id, user)
    if locked(db, entity.id, payload.target_period):
        raise HTTPException(status.HTTP_409_CONFLICT, "Target period is locked")
    source_period = previous_period(payload.target_period)
    source = db.scalars(
        select(Observation).where(
            Observation.entity_id == entity.id,
            Observation.period == source_period,
            Observation.status.in_([ObservationStatus.PENDING, ObservationStatus.REPEATED]),
            Observation.is_active.is_(True),
        )
    ).all()
    count = 0
    for old in source:
        exists = db.scalar(
            select(Observation.id).where(
                Observation.entity_id == entity.id,
                Observation.period == payload.target_period,
                Observation.checklist_item_id == old.checklist_item_id,
            )
        )
        if exists:
            continue
        item = Observation(
            organization_id=user.organization_id,
            entity_id=entity.id,
            audit_area_id=old.audit_area_id,
            checklist_item_id=old.checklist_item_id,
            predecessor_id=old.id,
            period=payload.target_period,
            risk=old.risk,
            status=ObservationStatus.REPEATED,
            observation=f"Carry forward from {source_period}: {old.observation}",
            remark=old.remark,
            responsible_person=old.responsible_person,
            due_date=old.due_date,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(item)
        db.flush()
        db.add(
            ObservationHistory(
                observation_id=item.id,
                changed_by_id=user.id,
                action="CARRIED_FORWARD",
                new_value={"predecessor_id": str(old.id), "source_period": source_period},
            )
        )
        count += 1
    record_audit(
        db,
        user,
        "OBSERVATIONS_CARRIED_FORWARD",
        "entity",
        entity.id,
        new_value={
            "source_period": source_period,
            "target_period": payload.target_period,
            "count": count,
        },
    )
    db.commit()
    return {"source_period": source_period, "target_period": payload.target_period, "count": count}


@router.get("/observations", response_model=list[ObservationOut])
def list_observations(
    entity_id: uuid.UUID | None = None,
    audit_area_id: uuid.UUID | None = None,
    period: str | None = None,
    observation_status: ObservationStatus | None = None,
    user: User = Depends(require_permission("VIEW_AUDIT_ENTRY")),
    db: Session = Depends(get_db),
):
    stmt = select(Observation).where(
        Observation.organization_id == user.organization_id, Observation.is_active.is_(True)
    )
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        stmt = stmt.where(Observation.entity_id.in_(allowed))
    if entity_id:
        stmt = stmt.where(Observation.entity_id == entity_id)
    if audit_area_id:
        stmt = stmt.where(Observation.audit_area_id == audit_area_id)
    if period:
        stmt = stmt.where(Observation.period == period)
    if observation_status:
        stmt = stmt.where(Observation.status == observation_status)
    return db.scalars(stmt.order_by(Observation.created_at.desc())).all()


@router.get("/observations-export.csv")
def export_observations(
    entity_id: uuid.UUID | None = None,
    period: str | None = None,
    user: User = Depends(require_permission("VIEW_AUDIT_ENTRY")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Observation, Entity.name, AuditArea.name, ChecklistItem.question)
        .join(Entity, Entity.id == Observation.entity_id)
        .join(AuditArea, AuditArea.id == Observation.audit_area_id)
        .join(ChecklistItem, ChecklistItem.id == Observation.checklist_item_id)
        .where(Observation.organization_id == user.organization_id, Observation.is_active.is_(True))
    )
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        stmt = stmt.where(Observation.entity_id.in_(allowed))
    if entity_id:
        stmt = stmt.where(Observation.entity_id == entity_id)
    if period:
        stmt = stmt.where(Observation.period == period)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Entity",
            "Period",
            "Audit Area",
            "Checklist Item",
            "Risk",
            "Observation",
            "Remark",
            "Responsible",
            "Due Date",
            "Status",
        ]
    )
    for observation, entity, area, question in db.execute(
        stmt.order_by(Observation.period.desc())
    ).all():
        writer.writerow(
            [
                entity,
                observation.period,
                area,
                question,
                observation.risk.value,
                observation.observation,
                observation.remark,
                observation.responsible_person,
                observation.due_date.isoformat() if observation.due_date else "",
                observation.status.value,
            ]
        )
    content = BytesIO(output.getvalue().encode("utf-8-sig"))
    record_audit(db, user, "OBSERVATIONS_EXPORTED", "organization", user.organization_id)
    db.commit()
    return StreamingResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_observation_register.csv"'},
    )


@router.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
def create_observation(
    payload: ObservationCreate,
    user: User = Depends(require_permission("CREATE_OBSERVATION")),
    db: Session = Depends(get_db),
):
    ensure_entity_access(db, payload.entity_id, user)
    area = db.get(AuditArea, payload.audit_area_id)
    item = db.get(ChecklistItem, payload.checklist_item_id)
    if (
        not area
        or not item
        or area.organization_id != user.organization_id
        or item.audit_area_id != area.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit scope not found")
    if locked(db, payload.entity_id, payload.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "Locked observations are read-only")
    existing = db.scalar(
        select(Observation).where(
            Observation.entity_id == payload.entity_id,
            Observation.period == payload.period,
            Observation.checklist_item_id == payload.checklist_item_id,
        )
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A response already exists for this checklist item"
        )
    observation = Observation(
        organization_id=user.organization_id,
        created_by_id=user.id,
        updated_by_id=user.id,
        **payload.model_dump(),
    )
    if payload.audit_plan_id:
        plan = db.get(AuditPlan, payload.audit_plan_id)
        if (
            not plan
            or plan.organization_id != user.organization_id
            or plan.entity_id != payload.entity_id
            or plan.audit_area_id != payload.audit_area_id
            or plan.period != payload.period
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Audit plan does not match the observation scope")
    db.add(observation)
    db.flush()
    update_plan_completion(db, observation)
    snapshot = {
        "status": observation.status.value,
        "risk": observation.risk.value,
        "observation": observation.observation,
    }
    db.add(
        ObservationHistory(
            observation_id=observation.id,
            changed_by_id=user.id,
            action="CREATED",
            new_value=snapshot,
        )
    )
    record_audit(db, user, "OBSERVATION_CREATED", "observation", observation.id, new_value=snapshot)
    db.commit()
    db.refresh(observation)
    return observation


@router.patch("/observations/{observation_id}", response_model=ObservationOut)
def update_observation(
    observation_id: uuid.UUID,
    payload: ObservationUpdate,
    user: User = Depends(require_permission("EDIT_OBSERVATION")),
    db: Session = Depends(get_db),
):
    observation = db.get(Observation, observation_id)
    if not observation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found")
    ensure_same_organization(observation.organization_id, user)
    ensure_entity_access(db, observation.entity_id, user)
    if observation.locked_at or locked(db, observation.entity_id, observation.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "Locked observations are read-only")
    if payload.expected_version is not None and payload.expected_version != observation.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Observation was changed by another user; reload and retry"
        )
    old = {
        "status": observation.status.value,
        "risk": observation.risk.value,
        "observation": observation.observation,
        "remark": observation.remark,
    }
    for key, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(observation, key, value)
    observation.version += 1
    observation.updated_by_id = user.id
    update_plan_completion(db, observation)
    new = {
        "status": observation.status.value,
        "risk": observation.risk.value,
        "observation": observation.observation,
        "remark": observation.remark,
    }
    db.add(
        ObservationHistory(
            observation_id=observation.id,
            changed_by_id=user.id,
            action="UPDATED",
            old_value=old,
            new_value=new,
        )
    )
    record_audit(db, user, "OBSERVATION_UPDATED", "observation", observation.id, old, new)
    db.commit()
    db.refresh(observation)
    return observation


@router.post("/observations/{observation_id}/replies", status_code=status.HTTP_201_CREATED)
def add_reply(
    observation_id: uuid.UUID,
    payload: ReplyCreate,
    user: User = Depends(require_permission("CREATE_CLIENT_REPLY")),
    db: Session = Depends(get_db),
):
    observation = db.get(Observation, observation_id)
    if not observation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found")
    ensure_same_organization(observation.organization_id, user)
    ensure_entity_access(db, observation.entity_id, user)
    if observation.locked_at or locked(db, observation.entity_id, observation.period):
        raise HTTPException(status.HTTP_409_CONFLICT, "Locked observations are read-only")
    old_status = observation.status.value
    reply = ManagementReply(
        observation_id=observation.id, submitted_by_id=user.id, **payload.model_dump()
    )
    observation.status = ObservationStatus.MANAGEMENT_RESPONDED
    observation.version += 1
    observation.updated_by_id = user.id
    db.add(reply)
    db.flush()
    db.add(
        ObservationHistory(
            observation_id=observation.id,
            changed_by_id=user.id,
            action="MANAGEMENT_REPLY_ADDED",
            old_value={"status": old_status},
            new_value={"status": observation.status.value, "reply_id": str(reply.id)},
        )
    )
    record_audit(
        db,
        user,
        "MANAGEMENT_REPLY_ADDED",
        "observation",
        observation.id,
        new_value={"reply_id": str(reply.id)},
    )
    db.commit()
    return {"id": reply.id, "status": observation.status.value}


@router.get("/observations/{observation_id}/history")
def observation_history(
    observation_id: uuid.UUID,
    user: User = Depends(require_permission("VIEW_AUDIT_ENTRY")),
    db: Session = Depends(get_db),
):
    observation = db.get(Observation, observation_id)
    if not observation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found")
    ensure_same_organization(observation.organization_id, user)
    ensure_entity_access(db, observation.entity_id, user)
    return db.scalars(
        select(ObservationHistory)
        .where(ObservationHistory.observation_id == observation_id)
        .order_by(ObservationHistory.created_at)
    ).all()


@router.get("/management-replies")
def list_management_replies(
    user: User = Depends(require_permission("VIEW_CLIENT_REPLY")), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(ManagementReply, Observation)
        .join(Observation, Observation.id == ManagementReply.observation_id)
        .where(Observation.organization_id == user.organization_id)
        .order_by(ManagementReply.submitted_at.desc())
    ).all()
    allowed = permitted_entity_ids(user)
    if allowed is not None:
        rows = [
            (reply, observation) for reply, observation in rows if observation.entity_id in allowed
        ]
    return [
        {
            "id": reply.id,
            "observation_id": observation.id,
            "observation": observation.observation,
            "comment": reply.comment,
            "action_taken": reply.action_taken,
            "submitted_at": reply.submitted_at,
        }
        for reply, observation in rows
    ]
