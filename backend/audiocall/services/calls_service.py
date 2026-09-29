"""DB-backed operations on `customers` and `calls`.

Each function opens and closes its own short-lived session. Call handling is
long-lived (a phone call, not a single request/response), so there is no single
request-scoped session to share — callers invoke these as one-off operations
at each lifecycle event (call created, Twilio status update, stream started,
stream ended, ...).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from twilio.base.exceptions import TwilioRestException

from audiocall.core import config
from audiocall.db.models import Call, CallSummary, Customer
from audiocall.db.session import get_session_factory

logger = logging.getLogger(__name__)

# Twilio call statuses -> our lifecycle enum (queued|ringing|in_progress|
# completed|failed|no_answer|disconnected).
_TWILIO_STATUS_MAP = {
    "queued": "queued",
    "initiated": "queued",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "answered": "in_progress",
    "completed": "completed",
    "busy": "no_answer",
    "no-answer": "no_answer",
    "failed": "failed",
    "canceled": "failed",
}

_TERMINAL_STATUSES = {"completed", "failed", "no_answer", "disconnected"}


class CustomerNotFound(Exception):
    """Raised when a customer_id does not resolve to a row."""


class TwilioCallFailed(Exception):
    """Raised when Twilio rejects/fails an outbound call creation request."""


def map_twilio_status(twilio_status: str) -> str:
    return _TWILIO_STATUS_MAP.get(twilio_status, "failed")


async def _maybe_trigger_analysis(
    previous_status: str | None, new_status: str, call_id: uuid.UUID
) -> None:
    """Fire post-call AI analysis exactly once, the moment a call first
    becomes terminal — never on a later, redundant status write.

    Fire-and-forget (`asyncio.create_task`, not awaited): the caller (a
    webhook handler or the /stream teardown) must return immediately —
    analysis runs asynchronously in the background.
    """
    if new_status not in _TERMINAL_STATUSES or previous_status in _TERMINAL_STATUSES:
        return

    # Local import: summary_service doesn't import calls_service, so this
    # isn't a real cycle, but importing here keeps module import order
    # (and any future refactor) simple to reason about.
    from audiocall.services import summary_service

    def _log_if_failed(task: asyncio.Task) -> None:
        exc = task.exception()
        if exc is not None:
            logger.error("post_call_processing(%s) raised: %s", call_id, exc)

    task = asyncio.create_task(summary_service.post_call_processing(call_id))
    task.add_done_callback(_log_if_failed)


async def get_customer(customer_id: uuid.UUID) -> Customer:
    async with get_session_factory()() as session:
        customer = await session.get(Customer, customer_id)
        if customer is None:
            raise CustomerNotFound(f"No customer with id {customer_id}")
        return customer


async def get_or_create_customer_by_phone(phone: str) -> Customer:
    """Used for inbound calls, where there is no prior /call request to look up."""
    async with get_session_factory()() as session:
        result = await session.execute(select(Customer).where(Customer.phone == phone))
        customer = result.scalar_one_or_none()
        if customer is not None:
            return customer

        customer = Customer(name="Unknown caller", phone=phone)
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer


async def create_call(customer_id: uuid.UUID, direction: str) -> Call:
    async with get_session_factory()() as session:
        call = Call(customer_id=customer_id, direction=direction, status="queued")
        session.add(call)
        await session.commit()
        await session.refresh(call)
        return call


async def set_twilio_sid(call_id: uuid.UUID, twilio_call_sid: str) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.twilio_call_sid = twilio_call_sid
        await session.commit()


async def set_status(
    call_id: uuid.UUID, status: str, error_reason: str | None = None
) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        previous_status = call.status
        call.status = status
        if error_reason is not None:
            call.error_reason = error_reason
        await session.commit()
    await _maybe_trigger_analysis(previous_status, status, call_id)


async def set_status_by_twilio_sid(
    twilio_call_sid: str, status: str, error_reason: str | None = None
) -> None:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Call).where(Call.twilio_call_sid == twilio_call_sid)
        )
        call = result.scalar_one_or_none()
        if call is None:
            return
        previous_status = call.status
        call_id = call.id
        call.status = status
        if error_reason is not None:
            call.error_reason = error_reason
        await session.commit()
    await _maybe_trigger_analysis(previous_status, status, call_id)


async def mark_stream_started(call_id: uuid.UUID, start_time: datetime) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.start_time = start_time
        if call.status in ("queued", "ringing"):
            call.status = "in_progress"
        await session.commit()


async def mark_stream_ended(
    call_id: uuid.UUID,
    end_time: datetime,
    status_override: str | None = None,
    error_reason: str | None = None,
) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        previous_status = call.status
        call.end_time = end_time
        if call.start_time is not None:
            call.duration_seconds = int((end_time - call.start_time).total_seconds())
        if status_override is not None:
            call.status = status_override
        elif call.status not in _TERMINAL_STATUSES:
            call.status = "disconnected"
        if error_reason is not None:
            call.error_reason = error_reason
        new_status = call.status
        await session.commit()
    await _maybe_trigger_analysis(previous_status, new_status, call_id)


async def start_outbound_call(customer_id: uuid.UUID) -> Call:
    """Look up the customer, create a `calls` row, and dial via Twilio.

    Shared by the legacy `POST /call` endpoint and the dashboard's
    `POST /api/calls` — both are thin wrappers around this. Raises
    `CustomerNotFound` or `TwilioCallFailed`; callers translate these to the
    appropriate HTTP response.
    """
    customer = await get_customer(customer_id)
    call = await create_call(customer.id, direction="outbound")

    try:
        twilio_call = config.twilio_client.calls.create(
            to=customer.phone,
            from_=config.TWILIO_PHONE_NUMBER,
            url=f"{config.HTTP_SCHEME}://{config.SERVER_HOST}/voice?call_id={call.id}",
            status_callback=f"{config.HTTP_SCHEME}://{config.SERVER_HOST}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
    except TwilioRestException as exc:
        logger.error("Twilio call creation failed for call_id=%s: %s", call.id, exc)
        await set_status(call.id, "failed", error_reason=str(exc))
        raise TwilioCallFailed(str(exc)) from exc

    await set_twilio_sid(call.id, twilio_call.sid)
    call.twilio_call_sid = twilio_call.sid

    logger.info(
        "Outbound call initiated: call_id=%s  SID=%s  to=%s",
        call.id,
        twilio_call.sid,
        customer.phone,
    )
    return call


async def list_calls(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    lead_status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    customer_name: str | None = None,
) -> tuple[list[tuple[Call, str, str | None]], int]:
    """Returns `(rows, total)`, where each row is `(Call, customer_name,
    lead_status)`. All filters combine with AND semantics."""
    async with get_session_factory()() as session:
        base_query = (
            select(Call, Customer.name, CallSummary.lead_status)
            .join(Customer, Call.customer_id == Customer.id)
            .outerjoin(CallSummary, CallSummary.call_id == Call.id)
        )
        count_query = (
            select(func.count(func.distinct(Call.id)))
            .select_from(Call)
            .join(Customer, Call.customer_id == Customer.id)
            .outerjoin(CallSummary, CallSummary.call_id == Call.id)
        )

        conditions = []
        if status is not None:
            conditions.append(Call.status == status)
        if lead_status is not None:
            conditions.append(CallSummary.lead_status == lead_status)
        if date_from is not None:
            conditions.append(Call.created_at >= date_from)
        if date_to is not None:
            conditions.append(Call.created_at <= date_to)
        if customer_name:
            conditions.append(Customer.name.ilike(f"%{customer_name}%"))

        for condition in conditions:
            base_query = base_query.where(condition)
            count_query = count_query.where(condition)

        total = await session.scalar(count_query) or 0
        result = await session.execute(
            base_query.order_by(Call.created_at.desc()).limit(limit).offset(offset)
        )
        rows = [(row[0], row[1], row[2]) for row in result.all()]
        return rows, total


async def get_call_detail(call_id: uuid.UUID) -> dict | None:
    """Returns a dict with the call, its customer, transcript, requirements,
    and summary — or None if the call doesn't exist."""
    async with get_session_factory()() as session:
        call = await session.get(
            Call,
            call_id,
            options=[
                selectinload(Call.customer),
                selectinload(Call.messages),
                selectinload(Call.requirements),
                selectinload(Call.summary),
            ],
        )
        if call is None:
            return None
        return {
            "call": call,
            "customer": call.customer,
            "messages": call.messages,
            "requirements": call.requirements,
            "summary": call.summary,
        }
