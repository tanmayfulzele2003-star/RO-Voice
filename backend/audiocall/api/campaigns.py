"""Campaign REST endpoints, mounted under /api/campaigns.

A campaign is a list of customers the background dialer (audiocall/dialer.py)
calls in parallel, within its own concurrency cap and the global
MAX_CONCURRENT_CALLS, retrying unanswered calls.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response

from audiocall.api.auth import require_admin
from audiocall.api.schemas import (
    CampaignContactOut,
    CampaignCounts,
    CampaignCreate,
    CampaignDetailOut,
    CampaignOut,
)
from audiocall.services import campaigns_service, profiles_service

router = APIRouter(
    prefix="/api/campaigns", tags=["campaigns"], dependencies=[Depends(require_admin)]
)


def _counts(raw: dict[str, int]) -> CampaignCounts:
    return CampaignCounts(**raw, total=sum(raw.values()))


def _out(campaign, counts: dict[str, int]) -> CampaignOut:  # noqa: ANN001
    return CampaignOut(
        id=campaign.id,
        name=campaign.name,
        profile_id=campaign.profile_id,
        status=campaign.status,
        status_reason=campaign.status_reason,
        max_concurrent=campaign.max_concurrent,
        max_attempts=campaign.max_attempts,
        retry_delay_minutes=campaign.retry_delay_minutes,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        created_at=campaign.created_at,
        counts=_counts(counts),
    )


async def _detail(campaign_id: uuid.UUID) -> CampaignDetailOut:
    found = await campaigns_service.get_campaign_detail(campaign_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign, counts, contacts = found
    return CampaignDetailOut(
        **_out(campaign, counts).model_dump(),
        contacts=[
            CampaignContactOut(
                id=c.id,
                customer_id=c.customer_id,
                customer_name=c.customer.name,
                customer_phone=c.customer.phone,
                status=c.status,
                attempts=c.attempts,
                last_call_id=c.last_call_id,
                last_outcome=c.last_outcome,
                next_attempt_at=c.next_attempt_at,
            )
            for c in contacts
        ],
    )


@router.get("", response_model=list[CampaignOut])
async def list_campaigns() -> list[CampaignOut]:
    return [_out(c, counts) for c, counts in await campaigns_service.list_campaigns()]


@router.post("", response_model=CampaignDetailOut, status_code=201)
async def create_campaign(payload: CampaignCreate) -> CampaignDetailOut:
    if payload.profile_id is not None and await profiles_service.get_profile(payload.profile_id) is None:
        raise HTTPException(status_code=422, detail="Business profile not found")
    data = payload.model_dump(exclude={"customer_ids"})
    campaign = await campaigns_service.create_campaign(data, payload.customer_ids)
    detail = await _detail(campaign.id)
    if not detail.contacts:
        await campaigns_service.delete_campaign(campaign.id)
        raise HTTPException(status_code=422, detail="None of the selected customers exist")
    return detail


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(campaign_id: uuid.UUID) -> CampaignDetailOut:
    return await _detail(campaign_id)


@router.post("/{campaign_id}/{action}", response_model=CampaignDetailOut)
async def change_campaign_status(
    campaign_id: uuid.UUID, action: Literal["start", "pause", "cancel"]
) -> CampaignDetailOut:
    try:
        await campaigns_service.set_campaign_status(campaign_id, action)
    except campaigns_service.CampaignNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except campaigns_service.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _detail(campaign_id)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID) -> Response:
    try:
        deleted = await campaigns_service.delete_campaign(campaign_id)
    except campaigns_service.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return Response(status_code=204)
