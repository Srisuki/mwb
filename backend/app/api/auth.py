import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, permission_codes
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import Session as UserSession
from app.models import User
from app.schemas import ChangePasswordRequest, LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def present_user(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        mobile=user.mobile,
        is_active=user.is_active,
        is_verified=user.is_verified,
        role=user.role.name,
        permissions=sorted(permission_codes(user)),
        must_change_password=user.must_change_password,
        entity_ids=sorted((entity.id for entity in user.entities), key=str),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    raw_refresh, token_hash, expires = create_refresh_token()
    db.add(UserSession(user_id=user.id, token_hash=token_hash, expires_at=expires))
    user.last_login_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user,
        "LOGIN",
        "user",
        user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return TokenResponse(access_token=create_access_token(str(user.id)), refresh_token=raw_refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or session.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive")
    session.revoked_at = now
    raw_refresh, new_hash, expires = create_refresh_token()
    db.add(UserSession(user_id=user.id, token_hash=new_hash, expires_at=expires))
    db.commit()
    return TokenResponse(access_token=create_access_token(str(user.id)), refresh_token=raw_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
    if session and not session.revoked_at:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return present_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.is_verified = True
    db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    record_audit(db, user, "PASSWORD_CHANGED", "user", user.id)
    db.commit()
