"""The signed-in user's company and team.

* `/api/organization` — company name (owners rename it).
* `/api/users` — teammates: change role, deactivate, remove (admins and up,
  within their rights: only owners manage owners).
* `/api/invites` — single-use invite links (admins and up).
* `/api/join/{token}` (public) — see and accept an invite.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from audiocall.api.auth import me_response, require_role, require_user, set_session_cookie
from audiocall.db.models import ROLES
from audiocall.services import team_service
from audiocall.services.team_service import UserContext

router = APIRouter(tags=["team"])

_RolePattern = "^(" + "|".join(ROLES) + ")$"


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    max_concurrent_calls: int | None
    created_at: datetime


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=_RolePattern)
    is_active: bool | None = None


class InviteCreate(BaseModel):
    role: str = Field(default="member", pattern=_RolePattern)
    note: str | None = Field(default=None, max_length=200)


class InviteOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    role: str
    note: str | None
    expires_at: datetime
    created_at: datetime


class InviteCreated(InviteOut):
    token: str = Field(description="Shown once: the invite link is /join?token=<token>")


class JoinInfo(BaseModel):
    organization: str
    role: str
    expires_at: datetime


class JoinRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)


def _team_error(exc: Exception) -> HTTPException:
    if isinstance(exc, team_service.NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


# ── Organization ─────────────────────────────────────────────────────────────
@router.get("/api/organization", response_model=OrganizationOut)
async def get_organization(user: UserContext = Depends(require_user)) -> OrganizationOut:
    org = await team_service.get_org(user.org_id)
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.patch("/api/organization", response_model=OrganizationOut)
async def update_organization(
    payload: OrganizationUpdate, user: UserContext = Depends(require_role("owner"))
) -> OrganizationOut:
    org = await team_service.update_org(user.org_id, {"name": payload.name.strip()})
    return OrganizationOut.model_validate(org, from_attributes=True)


# ── Users ────────────────────────────────────────────────────────────────────
@router.get("/api/users", response_model=list[UserOut])
async def list_users(user: UserContext = Depends(require_role("admin"))) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await team_service.list_users(user.org_id)]


@router.patch("/api/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, user: UserContext = Depends(require_role("admin"))
) -> UserOut:
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if user_id == user.id and data:
        raise HTTPException(status_code=409, detail="Ask another admin to change your own role or access.")
    try:
        updated = await team_service.update_user(user, user_id, data)
    except (team_service.TeamError, team_service.NotFound) as exc:
        raise _team_error(exc) from exc
    return UserOut.model_validate(updated)


@router.delete("/api/users/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, user: UserContext = Depends(require_role("admin"))) -> Response:
    try:
        await team_service.delete_user(user, user_id)
    except (team_service.TeamError, team_service.NotFound) as exc:
        raise _team_error(exc) from exc
    return Response(status_code=204)


# ── Invites ──────────────────────────────────────────────────────────────────
@router.get("/api/invites", response_model=list[InviteOut])
async def list_invites(user: UserContext = Depends(require_role("admin"))) -> list[InviteOut]:
    return [InviteOut.model_validate(i) for i in await team_service.list_invites(user.org_id)]


@router.post("/api/invites", response_model=InviteCreated, status_code=201)
async def create_invite(
    payload: InviteCreate, user: UserContext = Depends(require_role("admin"))
) -> InviteCreated:
    if not team_service.can_manage(user.role, payload.role):
        raise HTTPException(status_code=403, detail="Only an owner can invite another owner.")
    invite, token = await team_service.create_invite(user.org_id, payload.role, payload.note, user.id)
    return InviteCreated(**InviteOut.model_validate(invite).model_dump(), token=token)


@router.delete("/api/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: uuid.UUID, user: UserContext = Depends(require_role("admin"))
) -> Response:
    try:
        await team_service.revoke_invite(user.org_id, invite_id)
    except team_service.NotFound as exc:
        raise _team_error(exc) from exc
    return Response(status_code=204)


# ── Joining (public) ─────────────────────────────────────────────────────────
@router.get("/api/join/{token}", response_model=JoinInfo)
async def describe_invite(token: str) -> JoinInfo:
    found = await team_service.describe_invite(token)
    if found is None:
        raise HTTPException(status_code=404, detail="This invite link is invalid, used or expired.")
    invite, org = found
    return JoinInfo(organization=org.name, role=invite.role, expires_at=invite.expires_at)


@router.post("/api/join/{token}", status_code=201)
async def accept_invite(token: str, payload: JoinRequest, response: Response) -> dict:
    try:
        created = await team_service.accept_invite(token, payload.username, payload.password)
    except team_service.TeamError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    set_session_cookie(response, created.username)
    user = await team_service.get_user_context(created.username)
    return me_response(user).model_dump() if user else {}
