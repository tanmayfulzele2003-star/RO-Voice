"""Platform administration, mounted under /api/platform: the companies using
this installation. Platform admins only. (Platform-wide settings live in
api/settings.py under /api/platform/settings.)"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from audiocall.api.auth import require_platform_admin
from audiocall.api.team import InviteCreated, InviteOut
from audiocall.services import team_service
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/platform", tags=["platform"])


class OrgListItem(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    max_concurrent_calls: int | None
    users: int
    calls: int
    created_at: datetime


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_concurrent_calls: int | None = Field(default=None, ge=1, le=500)


class OrgCreated(BaseModel):
    organization: OrgListItem
    owner_invite: InviteCreated


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    max_concurrent_calls: int | None = Field(default=None, ge=1, le=500)


def _item(org, users: int = 0, calls: int = 0) -> OrgListItem:  # noqa: ANN001
    return OrgListItem(
        id=org.id,
        name=org.name,
        is_active=org.is_active,
        max_concurrent_calls=org.max_concurrent_calls,
        users=users,
        calls=calls,
        created_at=org.created_at,
    )


@router.get("/organizations", response_model=list[OrgListItem], dependencies=[Depends(require_platform_admin)])
async def list_organizations() -> list[OrgListItem]:
    return [_item(org, users, calls) for org, users, calls in await team_service.list_orgs()]


@router.post("/organizations", response_model=OrgCreated, status_code=201)
async def create_organization(
    payload: OrgCreate, admin: UserContext = Depends(require_platform_admin)
) -> OrgCreated:
    """A new customer company, with a single-use link for its first owner."""
    org = await team_service.create_org(payload.name.strip(), payload.max_concurrent_calls)
    invite, token = await team_service.create_invite(org.id, "owner", "First owner", admin.id)
    return OrgCreated(
        organization=_item(org),
        owner_invite=InviteCreated(**InviteOut.model_validate(invite).model_dump(), token=token),
    )


@router.patch("/organizations/{org_id}", response_model=OrgListItem)
async def update_organization(
    org_id: uuid.UUID, payload: OrgUpdate, admin: UserContext = Depends(require_platform_admin)
) -> OrgListItem:
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_active") is False and org_id == admin.org_id:
        raise HTTPException(status_code=409, detail="You can't deactivate your own company.")
    if "name" in data and data["name"] is None:
        data.pop("name")
    try:
        org = await team_service.update_org(org_id, data)
    except team_service.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _item(org)


@router.post("/organizations/{org_id}/invites", response_model=InviteCreated, status_code=201)
async def invite_owner(
    org_id: uuid.UUID, admin: UserContext = Depends(require_platform_admin)
) -> InviteCreated:
    """Another owner link for a customer company (e.g. the first one expired)."""
    if await team_service.get_org(org_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    invite, token = await team_service.create_invite(org_id, "owner", "Owner", admin.id)
    return InviteCreated(**InviteOut.model_validate(invite).model_dump(), token=token)
