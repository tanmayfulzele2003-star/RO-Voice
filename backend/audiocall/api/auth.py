"""Admin session auth: login/logout, and the `require_admin` dependency that
guards every other /api/* route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from audiocall.core import config
from audiocall.core.security import create_session_token, verify_password, verify_session_token
from audiocall.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str


async def require_admin(request: Request) -> str:
    """FastAPI dependency: raises 401 unless a valid, unexpired session
    cookie is present. Returns the authenticated username."""
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = verify_session_token(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Session invalid or expired")
    return username


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response) -> LoginResponse:
    admin = await auth_service.get_admin_by_username(payload.username)
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token(admin.username)
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=config.USE_TLS,
        samesite="lax",
        max_age=config.SESSION_TTL_SECONDS,
        path="/",
    )
    return LoginResponse(username=admin.username)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    # Must mutate and return the SAME injected `response` object — returning a
    # newly constructed Response() here would silently discard the
    # delete_cookie() call below (FastAPI uses whatever Response instance the
    # route actually returns as the final response).
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=LoginResponse)
async def me(username: str = Depends(require_admin)) -> LoginResponse:
    return LoginResponse(username=username)
