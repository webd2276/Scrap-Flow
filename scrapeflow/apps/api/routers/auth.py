"""Signup, login, refresh, logout, and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from packages.core.db import get_db
from packages.core.errors import AppError, ErrorCode
from packages.core.models import User
from packages.core.settings import Settings
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    AuthContext,
    auth_ip_rate_limit,
    client_ip,
    get_app_settings,
    get_jwt_auth,
    hash_ip,
)
from apps.api.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrgSummary,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from apps.api.services import auth as auth_service
from apps.api.services.audit import add_audit

router = APIRouter(prefix="/v1/auth", tags=["auth"])

REFRESH_COOKIE = "sf_refresh"


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.jwt_refresh_ttl_days * 86400,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/v1/auth",
    )


def _token_response(tokens: auth_service.IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user_id=tokens.user_id,
        org_id=tokens.org_id,
        role=tokens.role,
    )


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(auth_ip_rate_limit)],
)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    tokens = await auth_service.signup(
        db,
        settings,
        org_name=body.org_name,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
    )
    add_audit(
        db,
        action="org.created",
        resource_type="organization",
        org_id=tokens.org_id,
        user_id=tokens.user_id,
        resource_id=str(tokens.org_id),
        ip_hash=hash_ip(client_ip(request), settings.api_key_pepper.get_secret_value()),
        details={"tos_version": settings.tos_version},
    )
    await db.commit()
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return _token_response(tokens)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(auth_ip_rate_limit)],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    tokens = await auth_service.login(
        db,
        settings,
        email=body.email,
        password=body.password,
        org_slug=body.org_slug,
    )
    add_audit(
        db,
        action="auth.login",
        resource_type="user",
        org_id=tokens.org_id,
        user_id=tokens.user_id,
        resource_id=str(tokens.user_id),
        ip_hash=hash_ip(client_ip(request), settings.api_key_pepper.get_secret_value()),
    )
    await db.commit()
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return _token_response(tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(auth_ip_rate_limit)],
)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AppError(401, ErrorCode.UNAUTHORIZED, "Missing refresh token")
    tokens = await auth_service.refresh(db, settings, refresh_token=token)
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return _token_response(tokens)


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if token:
        await auth_service.logout(db, token)
    response.delete_cookie(REFRESH_COOKIE, path="/v1/auth")
    return {"status": "logged_out"}


@router.get("/me", response_model=MeResponse)
async def me(
    context: AuthContext = Depends(get_jwt_auth),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    user = await db.get(User, context.user_id)
    if user is None:
        raise AppError(404, ErrorCode.NOT_FOUND, "User not found")
    memberships = await auth_service.memberships_for_user(db, user.id)
    return MeResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        tos_accepted_at=user.tos_accepted_at,
        tos_version=user.tos_version,
        orgs=[
            OrgSummary(
                id=org.id,
                name=org.name,
                slug=org.slug,
                role=role.value,
                plan=org.plan.value,
            )
            for org, role in memberships
        ],
    )
