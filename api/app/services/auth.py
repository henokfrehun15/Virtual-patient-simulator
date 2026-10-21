from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User


class IssuedTokens(NamedTuple):
    access_token: str
    access_ttl_seconds: int
    refresh_token: str
    refresh_expires_at: datetime


def register_user(db: DbSession, *, email: str, password: str, full_name: str | None) -> User:
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise AppError("AUTH_EMAIL_TAKEN", "An account with this email already exists.", status_code=409)

    user = User(email=normalized_email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: DbSession, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(user.password_hash, password):
        raise AppError("AUTH_INVALID_CREDENTIALS", "Invalid email or password.", status_code=401)
    if not user.is_active:
        raise AppError("AUTH_ACCOUNT_DISABLED", "This account is disabled.", status_code=403)
    return user


def issue_session_tokens(db: DbSession, user: User) -> IssuedTokens:
    settings = get_settings()
    access_token, access_ttl = create_access_token(user.id)
    raw_refresh, refresh_expires_at = generate_refresh_token(settings.jwt_refresh_ttl_seconds)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expires_at,
        )
    )
    db.commit()
    return IssuedTokens(access_token, access_ttl, raw_refresh, refresh_expires_at)


def rotate_refresh_token(db: DbSession, raw_refresh_token: str) -> tuple[User, IssuedTokens]:
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh_token))
    )
    now = datetime.now(timezone.utc)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        raise AppError("AUTH_TOKEN_EXPIRED", "Refresh token is invalid or expired.", status_code=401)

    stored.revoked_at = now
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AppError("AUTH_ACCOUNT_DISABLED", "This account is disabled.", status_code=403)

    issued = issue_session_tokens(db, user)
    return user, issued


def revoke_refresh_token(db: DbSession, raw_refresh_token: str) -> None:
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh_token))
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        db.commit()
