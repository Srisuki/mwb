from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Entity, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        user_id = uuid.UUID(decode_access_token(credentials.credentials))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from None
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive or unavailable")
    return user


def permission_codes(user: User) -> set[str]:
    roles = [user.role, *user.roles]
    return {permission.code for role in roles if role.is_active for permission in role.permissions}


def require_permission(code: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Password change required before using the application"
            )
        if code not in permission_codes(user):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "You do not have permission for this action"
            )
        return user

    return dependency


def ensure_same_organization(resource_org_id, user: User) -> None:
    if resource_org_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")


def has_all_entity_access(user: User) -> bool:
    return "CLIENT_MANAGE" in permission_codes(user)


def ensure_entity_access(db: Session, entity_id: uuid.UUID, user: User) -> Entity:
    entity = db.get(Entity, entity_id)
    if not entity or entity.organization_id != user.organization_id or not entity.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    if not has_all_entity_access(user) and entity.id not in {item.id for item in user.entities}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    return entity


def permitted_entity_ids(user: User) -> set[uuid.UUID] | None:
    return None if has_all_entity_access(user) else {entity.id for entity in user.entities}
