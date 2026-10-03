"""Phone-number pool REST endpoints, mounted under /api/numbers.

Outbound calls take their caller ID from these numbers (the profile's own
first, then the shared pool); inbound calls are routed by the number dialled.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from audiocall.api.auth import require_admin
from audiocall.api.schemas import PhoneNumberCreate, PhoneNumberOut, PhoneNumberUpdate
from audiocall.services import numbers_service, profiles_service

router = APIRouter(
    prefix="/api/numbers", tags=["phone numbers"], dependencies=[Depends(require_admin)]
)


async def _check_profile(profile_id: uuid.UUID | None) -> None:
    if profile_id is not None and await profiles_service.get_profile(profile_id) is None:
        raise HTTPException(status_code=422, detail="Business profile not found")


@router.get("", response_model=list[PhoneNumberOut])
async def list_numbers() -> list[PhoneNumberOut]:
    return [PhoneNumberOut.model_validate(n) for n in await numbers_service.list_numbers()]


@router.post("", response_model=PhoneNumberOut, status_code=201)
async def create_number(payload: PhoneNumberCreate) -> PhoneNumberOut:
    await _check_profile(payload.profile_id)
    try:
        row = await numbers_service.create_number(payload.model_dump())
    except numbers_service.NumberConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PhoneNumberOut.model_validate(row)


@router.patch("/{number_id}", response_model=PhoneNumberOut)
async def update_number(number_id: uuid.UUID, payload: PhoneNumberUpdate) -> PhoneNumberOut:
    data = payload.model_dump(exclude_unset=True)
    for required in ("number", "inbound_enabled", "outbound_enabled", "is_active"):
        if data.get(required) is None:
            data.pop(required, None)
    await _check_profile(data.get("profile_id"))
    try:
        row = await numbers_service.update_number(number_id, data)
    except numbers_service.NumberConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Number not found")
    return PhoneNumberOut.model_validate(row)


@router.delete("/{number_id}", status_code=204)
async def delete_number(number_id: uuid.UUID) -> Response:
    if not await numbers_service.delete_number(number_id):
        raise HTTPException(status_code=404, detail="Number not found")
    return Response(status_code=204)


@router.post("/{number_id}/sync-twilio", response_model=PhoneNumberOut)
async def sync_number_to_twilio(number_id: uuid.UUID) -> PhoneNumberOut:
    """Point the number's incoming-call and status webhooks at this server."""
    try:
        row = await numbers_service.sync_twilio(number_id)
    except numbers_service.TwilioSyncFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PhoneNumberOut.model_validate(row)
