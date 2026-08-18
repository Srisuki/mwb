from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import ObservationStatus, PlanStatus, ReportStatus, RiskLevel


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    mobile: str | None
    is_active: bool
    is_verified: bool
    role: str
    permissions: list[str]
    must_change_password: bool
    entity_ids: list[uuid.UUID]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    mobile: str | None = Field(default=None, max_length=30, pattern=r"^[0-9+()\- ]*$")
    role_name: str
    temporary_password: str = Field(min_length=12, max_length=128)
    entity_ids: list[uuid.UUID] = Field(default_factory=list)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    mobile: str | None = Field(default=None, max_length=30, pattern=r"^[0-9+()\- ]*$")
    role_name: str | None = None
    is_active: bool | None = None
    entity_ids: list[uuid.UUID] | None = None


class ClientAccessUpdate(BaseModel):
    entity_ids: list[uuid.UUID]


class RoleOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    is_system_role: bool
    is_active: bool
    permissions: list[str]


class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    description: str


class AuditActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime


class EntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    code: str | None = Field(default=None, max_length=40)


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    code: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class EntityOut(ORMModel):
    id: uuid.UUID
    name: str
    code: str | None
    is_active: bool


class UserDetailOut(UserOut):
    effective_permissions: list[str]
    clients: list[EntityOut]
    recent_activity: list[AuditActivityOut]


class AreaOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    sort_order: int


class AreaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    sort_order: int = Field(default=0, ge=0)


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ChecklistOut(ORMModel):
    id: uuid.UUID
    audit_area_id: uuid.UUID
    question: str
    description: str
    is_mandatory: bool
    sort_order: int


class ChecklistCreate(BaseModel):
    audit_area_id: uuid.UUID
    question: str = Field(min_length=1)
    description: str = ""
    is_mandatory: bool = True
    sort_order: int = Field(default=0, ge=0)


class ChecklistUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1)
    description: str | None = None
    is_mandatory: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class PlanCreate(BaseModel):
    entity_id: uuid.UUID
    audit_area_id: uuid.UUID
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    due_date: date
    assigned_user_ids: list[uuid.UUID] = Field(default_factory=list)


class PlanOut(ORMModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    audit_area_id: uuid.UUID
    period: str
    due_date: date
    status: PlanStatus
    version: int


class PlanUpdate(BaseModel):
    due_date: date | None = None
    status: PlanStatus | None = None
    expected_version: int | None = Field(default=None, ge=1)


class FullMonthPlanCreate(BaseModel):
    entity_id: uuid.UUID
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    due_date: date
    assigned_user_ids: list[uuid.UUID] = Field(default_factory=list)


class CarryForwardRequest(BaseModel):
    entity_id: uuid.UUID
    target_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class ObservationCreate(BaseModel):
    entity_id: uuid.UUID
    audit_plan_id: uuid.UUID | None = None
    audit_area_id: uuid.UUID
    checklist_item_id: uuid.UUID
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    risk: RiskLevel = RiskLevel.LOW
    status: ObservationStatus = ObservationStatus.PENDING
    observation: str = Field(min_length=1)
    remark: str = ""
    responsible_person: str = ""
    due_date: date | None = None


class ObservationUpdate(BaseModel):
    risk: RiskLevel | None = None
    status: ObservationStatus | None = None
    observation: str | None = Field(default=None, min_length=1)
    remark: str | None = None
    responsible_person: str | None = None
    due_date: date | None = None
    expected_version: int | None = Field(default=None, ge=1)


class ObservationOut(ORMModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    audit_area_id: uuid.UUID
    checklist_item_id: uuid.UUID
    period: str
    risk: RiskLevel
    status: ObservationStatus
    observation: str
    remark: str
    responsible_person: str
    due_date: date | None
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class ReplyCreate(BaseModel):
    comment: str = Field(min_length=1)
    action_taken: str = ""


class ReportGenerate(BaseModel):
    entity_id: uuid.UUID
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    report_type: str = Field(min_length=1, max_length=120)


class ReportOut(ORMModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    period: str
    report_type: str
    report_number: str | None
    status: ReportStatus
    created_at: datetime


class DashboardSummary(BaseModel):
    total_observations: int
    pending_repeated: int
    high_critical: int
    locked_reports: int
    overdue_observations: int
    due_plans: int


class DocumentOut(ORMModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    audit_area_id: uuid.UUID | None
    observation_id: uuid.UUID | None
    checklist_item_id: uuid.UUID | None
    period: str
    document_type: str
    file_name: str
    mime_type: str
    file_size: int
    checksum: str
    remarks: str
    created_at: datetime


class SettingUpdate(BaseModel):
    value: dict
