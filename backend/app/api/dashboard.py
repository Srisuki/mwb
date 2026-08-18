from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import permitted_entity_ids, require_permission
from app.db.session import get_db
from app.models import (
    AuditPlan,
    Entity,
    Observation,
    ObservationStatus,
    Report,
    ReportLock,
    RiskLevel,
    User,
)
from app.schemas import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(
    user: User = Depends(require_permission("VIEW_DASHBOARD")), db: Session = Depends(get_db)
):
    org = user.organization_id
    allowed = permitted_entity_ids(user)

    def count(stmt):
        return db.scalar(stmt) or 0

    active = [Observation.organization_id == org, Observation.is_active.is_(True)]
    if allowed is not None:
        active.append(Observation.entity_id.in_(allowed))
    report_scope = [Report.organization_id == org]
    plan_scope = [AuditPlan.organization_id == org]
    if allowed is not None:
        report_scope.append(Report.entity_id.in_(allowed))
        plan_scope.append(AuditPlan.entity_id.in_(allowed))
    return DashboardSummary(
        total_observations=count(select(func.count(Observation.id)).where(*active)),
        pending_repeated=count(
            select(func.count(Observation.id)).where(
                *active,
                Observation.status.in_([ObservationStatus.PENDING, ObservationStatus.REPEATED]),
            )
        ),
        high_critical=count(
            select(func.count(Observation.id)).where(
                *active, Observation.risk.in_([RiskLevel.HIGH, RiskLevel.CRITICAL])
            )
        ),
        locked_reports=count(
            select(func.count(ReportLock.id))
            .join(Report, Report.id == ReportLock.report_id)
            .where(*report_scope)
        ),
        overdue_observations=count(
            select(func.count(Observation.id)).where(
                *active,
                Observation.due_date < date.today(),
                Observation.status.not_in([ObservationStatus.CLOSED, ObservationStatus.RESOLVED]),
            )
        ),
        due_plans=count(
            select(func.count(AuditPlan.id)).where(
                *plan_scope,
                AuditPlan.due_date >= date.today(),
                AuditPlan.status != "COMPLETED",
            )
        ),
    )


@router.get("/analytics")
def analytics(
    user: User = Depends(require_permission("VIEW_DASHBOARD")), db: Session = Depends(get_db)
):
    org = user.organization_id
    allowed = permitted_entity_ids(user)
    observation_scope = [Observation.organization_id == org, Observation.is_active.is_(True)]
    entity_scope = [Entity.organization_id == org, Entity.is_active.is_(True)]
    plan_scope = [AuditPlan.organization_id == org, AuditPlan.is_active.is_(True)]
    if allowed is not None:
        observation_scope.append(Observation.entity_id.in_(allowed))
        entity_scope.append(Entity.id.in_(allowed))
        plan_scope.append(AuditPlan.entity_id.in_(allowed))
    risk = db.execute(
        select(Observation.risk, func.count(Observation.id))
        .where(*observation_scope)
        .group_by(Observation.risk)
    ).all()
    statuses = db.execute(
        select(Observation.status, func.count(Observation.id))
        .where(*observation_scope)
        .group_by(Observation.status)
    ).all()
    entities = db.execute(
        select(Entity.name, func.count(Observation.id))
        .join(Observation, Observation.entity_id == Entity.id, isouter=True)
        .where(*entity_scope)
        .group_by(Entity.id, Entity.name)
        .order_by(func.count(Observation.id).desc(), Entity.name)
        .limit(12)
    ).all()
    periods = db.execute(
        select(Observation.period, func.count(Observation.id))
        .where(*observation_scope)
        .group_by(Observation.period)
        .order_by(Observation.period.desc())
        .limit(12)
    ).all()
    upcoming = db.execute(
        select(AuditPlan.period, AuditPlan.due_date, Entity.name)
        .join(Entity, Entity.id == AuditPlan.entity_id)
        .where(
            *plan_scope,
            AuditPlan.status != "COMPLETED",
        )
        .order_by(AuditPlan.due_date)
        .limit(10)
    ).all()
    return {
        "risk_distribution": [{"label": key.value, "count": count} for key, count in risk],
        "status_distribution": [{"label": key.value, "count": count} for key, count in statuses],
        "entity_status": [{"label": name, "count": count} for name, count in entities],
        "period_status": [{"label": period, "count": count} for period, count in periods],
        "upcoming_audits": [
            {"period": period, "due_date": due_date.isoformat(), "entity": entity}
            for period, due_date, entity in upcoming
        ],
    }
