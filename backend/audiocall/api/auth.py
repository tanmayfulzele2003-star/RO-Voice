"""Session auth: login/logout/me/password, and the dependencies that guard
every other /api/* route.

`require_user` resolves the session cookie to the signed-in user *and their
organization* on every request (one indexed query), so a deactivated user or
company is locked out immediately, and every route can scope its data with
`user.org_id`. `require_role("admin")` and `require_platform_admin` add role
checks on top.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from audiocall.core import config
from audiocall.core.security import create_session_token, verify_password, verify_session_token
from audiocall.services import auth_service, team_service
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class OrgOut(BaseModel):
    id: str
    name: str


class MeResponse(BaseModel):
    username: str
    role: str
    is_platform_admin: bool
    organization: OrgOut


class LoginResponse(MeResponse):
    pass


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


async def require_user(request: Request) -> UserContext:
    """FastAPI dependency: raises 401 unless a valid session cookie belongs to
    an active user in an active organization."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = verify_session_token(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Session invalid or expired")
    user = await team_service.get_user_context(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Account disabled — ask your admin.")
    return user


def require_role(minimum: str) -> Callable[..., Awaitable[UserContext]]:
    """Dependency factory: the signed-in user, if their role is at least `minimum`."""

    async def dependency(user: UserContext = Depends(require_user)) -> UserContext:
        if not user.at_least(minimum):
            raise HTTPException(
                status_code=403, detail=f"This needs the {minimum} role or higher."
            )
        return user

    return dependency


async def require_platform_admin(user: UserContext = Depends(require_user)) -> UserContext:
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Only the platform admin can do this.")
    return user


def me_response(user: UserContext) -> MeResponse:
    return MeResponse(
        username=user.username,
        role=user.role,
        is_platform_admin=user.is_platform_admin,
        organization=OrgOut(id=str(user.org_id), name=user.org_name),
    )


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=create_session_token(username),
        httponly=True,
        secure=config.USE_TLS,
        samesite="lax",
        max_age=config.SESSION_TTL_SECONDS,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response) -> MeResponse:
    admin = await auth_service.get_admin_by_username(payload.username)
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = await team_service.get_user_context(admin.username)
    if user is None:
        raise HTTPException(status_code=403, detail="This account is disabled — ask your admin.")
    set_session_cookie(response, admin.username)
    return me_response(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    # Must mutate and return the SAME injected `response` object — returning a
    # newly constructed Response() here would silently discard the
    # delete_cookie() call below (FastAPI uses whatever Response instance the
    # route actually returns as the final response).
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeResponse)
async def me(user: UserContext = Depends(require_user)) -> MeResponse:
    return me_response(user)


@router.post("/password", status_code=204)
async def change_password(payload: PasswordChange, user: UserContext = Depends(require_user)) -> Response:
    admin = await auth_service.get_admin_by_username(user.username)
    if admin is None or not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong.")
    await team_service.change_password(user.id, payload.new_password)
    return Response(status_code=204)
