"""Business profile REST endpoints, mounted under /api/profiles.

A profile configures the calling agent for one business (persona, products,
call objective, checklist of fields to collect). Customers are assigned a
profile; calls run with their customer's profile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from audiocall.api.auth import require_admin
from audiocall.api.schemas import ProfileCreate, ProfileOut, ProfileUpdate
from audiocall.services import profiles_service
from audiocall.templates import TEMPLATES

router = APIRouter(
    prefix="/api/profiles", tags=["business profiles"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[ProfileOut])
async def list_profiles() -> list[ProfileOut]:
    profiles = await profiles_service.list_profiles()
    if not profiles:
        profiles = [await profiles_service.get_default_profile()]
    return [ProfileOut.model_validate(p) for p in profiles]


@router.get("/templates")
async def list_templates() -> list[dict]:
    """Industry starting points for a new profile (see audiocall/templates.py)."""
    return TEMPLATES


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(payload: ProfileCreate) -> ProfileOut:
    profile = await profiles_service.create_profile(payload.model_dump())
    return ProfileOut.model_validate(profile)


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: uuid.UUID) -> ProfileOut:
    profile = await profiles_service.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileOut.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(profile_id: uuid.UUID, payload: ProfileUpdate) -> ProfileOut:
    data = payload.model_dump(exclude_unset=True)
    for required in ("name", "agent_name", "call_objective", "fields", "is_default"):
        if data.get(required) is None:
            data.pop(required, None)
    if data.get("is_default") is False:
        # "Un-defaulting" is done by making another profile the default.
        data.pop("is_default")
    profile = await profiles_service.update_profile(profile_id, data)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileOut.model_validate(profile)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: uuid.UUID) -> Response:
    try:
        deleted = await profiles_service.delete_profile(profile_id)
    except profiles_service.ProfileInUse as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    return Response(status_code=204)
