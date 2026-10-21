from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth import (
    IssuedTokens,
    authenticate_user,
    issue_session_tokens,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE = "vps_refresh_token"


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/v1/auth",
    )


def _token_response(response: Response, issued: IssuedTokens, user: User) -> TokenResponse:
    _set_refresh_cookie(response, issued.refresh_token, issued.refresh_expires_at)
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.access_ttl_seconds,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    response: Response,
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    user = register_user(db, email=body.email, password=body.password, full_name=body.full_name)
    issued = issue_session_tokens(db, user)
    return _token_response(response, issued, user)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    user = authenticate_user(db, body.email, body.password)
    issued = issue_session_tokens(db, user)
    return _token_response(response, issued, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> TokenResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token is None:
        raise AppError("AUTH_TOKEN_EXPIRED", "Refresh token missing.", status_code=401)

    user, issued = rotate_refresh_token(db, raw_token)
    return _token_response(response, issued, user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token is not None:
        revoke_refresh_token(db, raw_token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
