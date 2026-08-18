from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RiskLevel(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ObservationStatus(str, enum.Enum):
    PENDING = "Pending"
    MANAGEMENT_RESPONDED = "Management Responded"
    RESOLVED = "Resolved"
    REPEATED = "Repeated"
    CLOSED = "Closed"


class PlanStatus(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    OVERDUE = "Overdue"


class ReportStatus(str, enum.Enum):
    DRAFT = "Draft"
    GENERATED = "Generated"
    APPROVED = "Approved"
    LOCKED = "Locked"


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
)

user_entity_access = Table(
    "user_entity_access",
    Base.metadata,
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "entity_id",
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Organization(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    mobile: Mapped[Optional[str]] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    role = relationship("Role", lazy="selectin")
    roles = relationship("Role", secondary=user_roles, lazy="selectin")
    entities = relationship("Entity", secondary=user_entity_access, lazy="selectin")


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Entity(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_entity_org_name"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(40))


class AuditArea(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "audit_areas"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_area_org_name"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ChecklistItem(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "checklist_items"
    __table_args__ = (
        UniqueConstraint("audit_area_id", "question", name="uq_checklist_area_question"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    audit_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_areas.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AuditPlan(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "audit_plans"
    __table_args__ = (
        UniqueConstraint("entity_id", "period", "audit_area_id", name="uq_plan_scope"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    audit_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_areas.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.PENDING)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class AuditPlanAssignment(Base):
    __tablename__ = "audit_plan_assignments"
    __table_args__ = (UniqueConstraint("audit_plan_id", "user_id", name="uq_plan_assignment"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    audit_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_plans.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Observation(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("entity_id", "period", "checklist_item_id", name="uq_observation_scope"),
        Index("ix_observation_dashboard", "organization_id", "period", "status", "risk"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    audit_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("audit_plans.id"))
    audit_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_areas.id"), index=True)
    checklist_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("checklist_items.id"), index=True
    )
    predecessor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("observations.id"))
    period: Mapped[str] = mapped_column(String(7), index=True)
    risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.LOW)
    status: Mapped[ObservationStatus] = mapped_column(
        Enum(ObservationStatus), default=ObservationStatus.PENDING
    )
    observation: Mapped[str] = mapped_column(Text)
    remark: Mapped[str] = mapped_column(Text, default="")
    responsible_person: Mapped[str] = mapped_column(String(200), default="")
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ObservationHistory(Base):
    __tablename__ = "observation_history"
    id: Mapped[uuid.UUID] = uuid_pk()
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id"), index=True)
    changed_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagementReply(Base):
    __tablename__ = "management_replies"
    id: Mapped[uuid.UUID] = uuid_pk()
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id"), index=True)
    comment: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text, default="")
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("organization_id", "report_number", name="uq_report_number"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    report_type: Mapped[str] = mapped_column(String(120))
    report_number: Mapped[Optional[str]] = mapped_column(String(160))
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.DRAFT)
    snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    generated_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ReportLock(Base):
    __tablename__ = "report_locks"
    __table_args__ = (UniqueConstraint("entity_id", "period", name="uq_report_lock_scope"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id"), unique=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    locked_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportSequence(Base):
    __tablename__ = "report_sequences"
    __table_args__ = (
        UniqueConstraint("organization_id", "financial_year", name="uq_report_sequence"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    financial_year: Mapped[str] = mapped_column(String(20))
    next_value: Mapped[int] = mapped_column(Integer, default=1)


class Document(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), index=True)
    audit_area_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("audit_areas.id"))
    observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("observations.id"))
    checklist_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("checklist_items.id"))
    period: Mapped[str] = mapped_column(String(7), index=True)
    document_type: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(150))
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    remarks: Mapped[str] = mapped_column(Text, default="")
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AppSetting(Base, TimestampMixin):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_setting_org_key"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict] = mapped_column(JSONB)
