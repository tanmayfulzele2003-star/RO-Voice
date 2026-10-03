"""Call REST endpoints, mounted under /api/calls."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from audiocall.api.auth import require_role, require_user
from audiocall.api.schemas import (
    BrowserCallStartResponse,
    CallDetailOut,
    CallEventOut,
    CallListItem,
    CallStartRequest,
    CallStartResponse,
    CallSummaryOut,
    ConversationMessageOut,
    Paginated,
    ProfileField,
    RequirementsOut,
)
from audiocall.core.config import (
    CALL_RATE_LIMIT_MAX,
    CALL_RATE_LIMIT_WINDOW_SECONDS,
)
from audiocall.core import config
from audiocall.core.rate_limit import check_rate_limit
from audiocall.core.security import create_stream_token
from audiocall.services import calls_service
from audiocall.services.outcome import OUTCOMES
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/calls", tags=["calls"])


def _enforce_rate_limit(admin_username: str) -> None:
    if not check_rate_limit(
        admin_username, CALL_RATE_LIMIT_MAX, CALL_RATE_LIMIT_WINDOW_SECONDS
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many calls started recently — please wait a moment and try again.",
        )


@router.post("", response_model=CallStartResponse, status_code=201)
async def start_call(
    payload: CallStartRequest, user: UserContext = Depends(require_role("member"))
) -> CallStartResponse:
    """Place a real outbound phone call through the company's Twilio account."""
    _enforce_rate_limit(user.username)
    if await calls_service.free_lines(user.org_id) <= 0:
        raise HTTPException(
            status_code=429,
            detail="All call lines are busy — try again when a call ends.",
        )

    try:
        call = await calls_service.start_outbound_call(payload.customer_id, org_id=user.org_id)
    except calls_service.CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except calls_service.TwilioCallFailed as exc:
        raise HTTPException(
            status_code=502, detail=f"Twilio could not place the call: {exc}"
        ) from exc

    return CallStartResponse(call_id=call.id, call_sid=call.twilio_call_sid, status=call.status)


@router.post("/browser", response_model=BrowserCallStartResponse, status_code=201)
async def start_browser_call(
    payload: CallStartRequest, user: UserContext = Depends(require_role("member"))
) -> BrowserCallStartResponse:
    """Start a browser (WebRTC microphone) call — the same AI conversation
    without a telephony provider. Open `stream_url` within 2 minutes."""
    _enforce_rate_limit(user.username)
    try:
        call = await calls_service.start_browser_call(payload.customer_id, user.org_id)
    except calls_service.CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    token = create_stream_token(call.id)
    return BrowserCallStartResponse(
        call_id=call.id,
        token=token,
        stream_url=f"{config.WS_SCHEME}://{config.SERVER_HOST}/browser-stream?call_id={call.id}&token={token}",
    )


@router.get("", response_model=Paginated[CallListItem])
async def list_calls(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    lead_status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    customer_name: str | None = Query(default=None),
    follow_up: bool | None = Query(default=None),
    outcome: str | None = Query(default=None, description=f"One of: {', '.join(OUTCOMES)}"),
    channel: str | None = Query(default=None, description="phone | browser"),
    profile_id: uuid.UUID | None = Query(default=None),
    direction: str | None = Query(default=None, description="outbound | inbound"),
    campaign_id: uuid.UUID | None = Query(default=None),
    user: UserContext = Depends(require_user),
) -> Paginated[CallListItem]:
    rows, total = await calls_service.list_calls(
        user.org_id,
        limit=limit,
        offset=offset,
        status=status,
        lead_status=lead_status,
        date_from=date_from,
        date_to=date_to,
        customer_name=customer_name,
        follow_up=follow_up,
        outcome=outcome,
        channel=channel,
        profile_id=profile_id,
        direction=direction,
        campaign_id=campaign_id,
    )
    profile_names = await calls_service.profile_names(user.org_id)
    items = [
        CallListItem(
            id=call.id,
            customer_id=call.customer_id,
            customer_name=customer.name,
            customer_phone=customer.phone,
            profile_name=profile_names.get(call.profile_id),
            direction=call.direction,
            channel=call.channel,
            from_number=call.from_number,
            to_number=call.to_number,
            campaign_id=call.campaign_id,
            transferred_to=call.transferred_to,
            status=call.status,
            outcome=call.outcome,
            lead_status=summary.lead_status if summary else None,
            follow_up=summary.follow_up if summary else None,
            start_time=call.start_time,
            end_time=call.end_time,
            duration_seconds=call.duration_seconds,
            error_reason=call.error_reason,
            created_at=call.created_at,
        )
        for call, customer, summary in rows
    ]
    return Paginated(items=items, total=total, limit=limit, offset=offset)


@router.get("/{call_id}", response_model=CallDetailOut)
async def get_call_detail(
    call_id: uuid.UUID, user: UserContext = Depends(require_user)
) -> CallDetailOut:
    detail = await calls_service.get_call_detail(call_id, user.org_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Call not found")

    call = detail["call"]
    customer = detail["customer"]
    requirements = detail["requirements"]
    summary = detail["summary"]
    profile = detail["profile"]

    return CallDetailOut(
        id=call.id,
        customer_id=call.customer_id,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_company=customer.company,
        customer_purpose=customer.purpose,
        customer_product=customer.product,
        profile_id=call.profile_id,
        profile_name=profile.name if profile else None,
        profile_fields=[ProfileField(**f) for f in (profile.fields if profile else [])],
        twilio_call_sid=call.twilio_call_sid,
        direction=call.direction,
        channel=call.channel,
        from_number=call.from_number,
        to_number=call.to_number,
        campaign_id=call.campaign_id,
        transferred_to=call.transferred_to,
        status=call.status,
        outcome=call.outcome,
        start_time=call.start_time,
        end_time=call.end_time,
        duration_seconds=call.duration_seconds,
        error_reason=call.error_reason,
        created_at=call.created_at,
        messages=[ConversationMessageOut.model_validate(m) for m in detail["messages"]],
        events=[CallEventOut.model_validate(e) for e in detail["events"]],
        requirements=RequirementsOut.model_validate(requirements) if requirements else None,
        summary=CallSummaryOut.model_validate(summary) if summary else None,
    )
