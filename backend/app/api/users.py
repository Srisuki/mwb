from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import present_user
from app.api.deps import permission_codes, require_permission
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AuditLog, Entity, Permission, Role, Session as UserSession, User
from app.schemas import (
    ClientAccessUpdate,
    EntityOut,
    PermissionOut,
    RoleOut,
    UserCreate,
    UserDetailOut,
    UserOut,
    UserUpdate,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["users"])
catalog_router = APIRouter(tags=["roles and permissions"])
CLIENT_ROLE_NAMES = {"Client Management", "Client / Management"}


def resolve_entities(db: Session, organization_id: uuid.UUID, entity_ids: list[uuid.UUID]):
    unique_ids = set(entity_ids)
    if not unique_ids:
        return []
    entities = db.scalars(
        select(Entity).where(
            Entity.organization_id == organization_id,
            Entity.is_active.is_(True),
            Entity.id.in_(unique_ids),
        )
    ).all()
    if len(entities) != len(unique_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more clients are invalid")
    return entities


def resolve_role(db: Session, role_name: str) -> Role:
    normalized = "Client Management" if role_name == "Client / Management" else role_name
    role = db.scalar(select(Role).where(Role.name == normalized, Role.is_active.is_(True)))
    if not role:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown or inactive role")
    return role


def validate_scope(role: Role, entities: list[Entity]) -> None:
    if role.name in CLIENT_ROLE_NAMES and not entities:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Client Management users must have at least one client",
        )


def has_system_wide_client_access(role: Role) -> bool:
    return "CLIENT_MANAGE" in {permission.code for permission in role.permissions}


def snapshot(user: User) -> dict:
    return {
        "full_name": user.full_name,
        "mobile": user.mobile,
        "role": user.role.name,
        "is_active": user.is_active,
        "client_ids": sorted(str(item.id) for item in user.entities),
    }


def get_target(db: Session, actor: User, user_id: uuid.UUID) -> User:
    target = db.get(User, user_id)
    if not target or target.organization_id != actor.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return target


def present_detail(db: Session, user: User) -> UserDetailOut:
    base = present_user(user).model_dump()
    activity = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == user.organization_id,
            or_(
                AuditLog.user_id == user.id,
                and_(AuditLog.entity_type == "user", AuditLog.entity_id == user.id),
            ),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
    ).all()
    return UserDetailOut(
        **base,
        effective_permissions=sorted(permission_codes(user)),
        clients=user.entities,
        recent_activity=[
            {
                "id": item.id,
                "action": item.action,
                "old_value": item.old_value,
                "new_value": item.new_value,
                "created_at": item.created_at,
            }
            for item in activity
        ],
    )


@router.get("", response_model=list[UserOut])
def list_users(
    response: Response,
    search: str | None = None,
    role: str | None = None,
    client: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|inactive)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_permission("USER_VIEW")),
    db: Session = Depends(get_db),
):
    stmt = select(User).where(User.organization_id == actor.organization_id)
    count_stmt = select(func.count(func.distinct(User.id))).where(
        User.organization_id == actor.organization_id
    )
    conditions = []
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(User.full_name.ilike(term), User.email.ilike(term), User.mobile.ilike(term)))
    if role:
        conditions.append(User.role.has(Role.name == role))
    if client:
        conditions.append(User.entities.any(Entity.id == client))
    if status_filter:
        conditions.append(User.is_active.is_(status_filter == "active"))
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    rows = db.scalars(
        stmt.order_by(User.full_name, User.email).offset((page - 1) * page_size).limit(page_size)
    ).unique().all()
    return [present_user(item) for item in rows]


@router.get("/assignees", response_model=list[UserOut])
def list_audit_assignees(
    actor: User = Depends(require_permission("CREATE_AUDIT_PLAN")), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(User)
        .join(Role, Role.id == User.role_id)
        .where(
            User.organization_id == actor.organization_id,
            User.is_active.is_(True),
            Role.name.in_(["Audit Manager", "Audit Staff"]),
        )
        .order_by(User.full_name)
    ).all()
    return [present_user(item) for item in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_permission("USER_CREATE")),
    db: Session = Depends(get_db),
):
    email = payload.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    role = resolve_role(db, payload.role_name)
    entities = resolve_entities(db, actor.organization_id, payload.entity_ids)
    validate_scope(role, entities)
    if has_system_wide_client_access(role):
        entities = []
    created = User(
        organization_id=actor.organization_id,
        role_id=role.id,
        email=email,
        full_name=payload.full_name.strip(),
        mobile=payload.mobile.strip() if payload.mobile else None,
        password_hash=hash_password(payload.temporary_password),
        must_change_password=True,
        is_verified=False,
        is_active=payload.is_active,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    created.role = role
    created.roles = [role]
    created.entities = entities
    db.add(created)
    db.flush()
    record_audit(db, actor, "USER_CREATED", "user", created.id, new_value=snapshot(created))
    db.commit()
    db.refresh(created)
    return present_user(created)


@router.get("/{user_id}", response_model=UserDetailOut)
def get_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("USER_VIEW")),
    db: Session = Depends(get_db),
):
    return present_detail(db, get_target(db, actor, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    actor: User = Depends(require_permission("USER_EDIT")),
    db: Session = Depends(get_db),
):
    target = get_target(db, actor, user_id)
    old = snapshot(target)
    old_role = target.role.name
    old_clients = {entity.id for entity in target.entities}
    if payload.role_name is not None:
        if target.id == actor.id and payload.role_name != target.role.name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot change your own role")
        role = resolve_role(db, payload.role_name)
        target.role_id = role.id
        target.role = role
        target.roles = [role]
    if payload.entity_ids is not None:
        if target.id == actor.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot change your own client scope")
        target.entities = resolve_entities(db, actor.organization_id, payload.entity_ids)
    validate_scope(target.role, target.entities)
    if has_system_wide_client_access(target.role):
        target.entities = []
    if payload.full_name is not None:
        target.full_name = payload.full_name.strip()
    if payload.mobile is not None:
        target.mobile = payload.mobile.strip() or None
    if payload.is_active is not None and payload.is_active != target.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Use the dedicated activate or deactivate action",
        )
    target.updated_by_id = actor.id
    new = snapshot(target)
    record_audit(db, actor, "USER_UPDATED", "user", target.id, old, new)
    if old_role != target.role.name:
        record_audit(
            db,
            actor,
            "USER_ROLE_CHANGED",
            "user",
            target.id,
            {"role": old_role},
            {"role": target.role.name},
        )
    if old_clients != {entity.id for entity in target.entities}:
        record_audit(
            db,
            actor,
            "USER_CLIENT_ACCESS_CHANGED",
            "user",
            target.id,
            {"client_ids": sorted(map(str, old_clients))},
            {"client_ids": sorted(str(entity.id) for entity in target.entities)},
        )
    db.commit()
    db.refresh(target)
    return present_user(target)


def change_activation(db: Session, actor: User, target: User, active: bool) -> UserOut:
    permission = "USER_ACTIVATE" if active else "USER_DEACTIVATE"
    if permission not in permission_codes(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
    if target.id == actor.id and not active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot deactivate yourself")
    old = target.is_active
    target.is_active = active
    target.updated_by_id = actor.id
    if not active:
        db.query(UserSession).filter(
            UserSession.user_id == target.id, UserSession.revoked_at.is_(None)
        ).update({"revoked_at": func.now()})
    record_audit(
        db,
        actor,
        "USER_ACTIVATED" if active else "USER_DEACTIVATED",
        "user",
        target.id,
        {"is_active": old},
        {"is_active": active},
    )
    db.commit()
    db.refresh(target)
    return present_user(target)


@router.post("/{user_id}/activate", response_model=UserOut)
def activate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("USER_ACTIVATE")),
    db: Session = Depends(get_db),
):
    return change_activation(db, actor, get_target(db, actor, user_id), True)


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("USER_DEACTIVATE")),
    db: Session = Depends(get_db),
):
    return change_activation(db, actor, get_target(db, actor, user_id), False)


@router.get("/{user_id}/permissions", response_model=list[str])
def user_permissions(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("USER_VIEW")),
    db: Session = Depends(get_db),
):
    return sorted(permission_codes(get_target(db, actor, user_id)))


@router.get("/{user_id}/clients", response_model=list[EntityOut])
def user_clients(
    user_id: uuid.UUID,
    actor: User = Depends(require_permission("USER_VIEW")),
    db: Session = Depends(get_db),
):
    return [
        {"id": entity.id, "name": entity.name, "code": entity.code}
        for entity in get_target(db, actor, user_id).entities
    ]


@router.put("/{user_id}/clients", response_model=list[EntityOut])
def update_user_clients(
    user_id: uuid.UUID,
    payload: ClientAccessUpdate,
    actor: User = Depends(require_permission("USER_EDIT")),
    db: Session = Depends(get_db),
):
    target = get_target(db, actor, user_id)
    if target.id == actor.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot change your own client scope")
    old_ids = sorted(str(entity.id) for entity in target.entities)
    entities = resolve_entities(db, actor.organization_id, payload.entity_ids)
    if has_system_wide_client_access(target.role) and entities:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Admin / Partner has system-wide access and cannot be assigned individual clients",
        )
    target.entities = entities
    validate_scope(target.role, target.entities)
    target.updated_by_id = actor.id
    new_ids = sorted(str(entity.id) for entity in target.entities)
    record_audit(
        db,
        actor,
        "USER_CLIENT_ACCESS_CHANGED",
        "user",
        target.id,
        {"client_ids": old_ids},
        {"client_ids": new_ids},
    )
    db.commit()
    return [{"id": entity.id, "name": entity.name, "code": entity.code} for entity in target.entities]


@catalog_router.get("/roles", response_model=list[RoleOut])
def list_roles(
    actor: User = Depends(require_permission("ROLE_VIEW")), db: Session = Depends(get_db)
):
    roles = db.scalars(select(Role).where(Role.is_active.is_(True)).order_by(Role.name)).all()
    return [
        RoleOut(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_system_role=role.is_system_role,
            is_active=role.is_active,
            permissions=sorted(permission.code for permission in role.permissions),
        )
        for role in roles
    ]


@catalog_router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    actor: User = Depends(require_permission("ROLE_VIEW")), db: Session = Depends(get_db)
):
    return db.scalars(select(Permission).order_by(Permission.code)).all()
