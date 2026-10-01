"""Call REST endpoints, mounted under /api/calls."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from audiocall.api.auth import require_admin
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
    SERVER_HOST,
    WS_SCHEME,
)
from audiocall.core.rate_limit import check_rate_limit
from audiocall.core.security import create_stream_token
from audiocall.services import calls_service
from audiocall.services.outcome import OUTCOMES

router = APIRouter(prefix="/api/calls", tags=["calls"], dependencies=[Depends(require_admin)])


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
    payload: CallStartRequest, admin_username: str = Depends(require_admin)
) -> CallStartResponse:
    """Place a real outbound phone call through Twilio."""
    _enforce_rate_limit(admin_username)

    try:
        call = await calls_service.start_outbound_call(payload.customer_id)
    except calls_service.CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except calls_service.TwilioCallFailed as exc:
        raise HTTPException(
            status_code=502, detail=f"Twilio could not place the call: {exc}"
        ) from exc

    return CallStartResponse(call_id=call.id, call_sid=call.twilio_call_sid, status=call.status)


@router.post("/browser", response_model=BrowserCallStartResponse, status_code=201)
async def start_browser_call(
    payload: CallStartRequest, admin_username: str = Depends(require_admin)
) -> BrowserCallStartResponse:
    """Start a browser (WebRTC microphone) call — the same AI conversation
    without a telephony provider. Open `stream_url` within 2 minutes."""
    _enforce_rate_limit(admin_username)
    try:
        call = await calls_service.start_browser_call(payload.customer_id)
    except calls_service.CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    token = create_stream_token(call.id)
    return BrowserCallStartResponse(
        call_id=call.id,
        token=token,
        stream_url=f"{WS_SCHEME}://{SERVER_HOST}/browser-stream?call_id={call.id}&token={token}",
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
) -> Paginated[CallListItem]:
    rows, total = await calls_service.list_calls(
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
    )
    profile_names = await calls_service.profile_names()
    items = [
        CallListItem(
            id=call.id,
            customer_id=call.customer_id,
            customer_name=customer.name,
            customer_phone=customer.phone,
            profile_name=profile_names.get(call.profile_id),
            direction=call.direction,
            channel=call.channel,
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
async def get_call_detail(call_id: uuid.UUID) -> CallDetailOut:
    detail = await calls_service.get_call_detail(call_id)
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
