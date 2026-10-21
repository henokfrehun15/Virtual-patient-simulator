import uuid

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DbSession

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: DbSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError("AUTH_UNAUTHORIZED", "Authentication required.", status_code=401)

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise AppError("AUTH_INVALID_TOKEN", "Invalid access token.", status_code=401)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("AUTH_UNAUTHORIZED", "Authentication required.", status_code=401)
    return user


class PaginationParams:
    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
