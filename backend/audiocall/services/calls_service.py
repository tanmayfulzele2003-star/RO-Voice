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
from datetime import datetime, timedelta, timezone

from xml.sax.saxutils import escape as xml_escape

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from twilio.base.exceptions import TwilioRestException

from audiocall.core import config
from audiocall.db.models import Call, CallSummary, Customer
from audiocall.db.session import get_session_factory
from audiocall.phone import is_valid_e164
from audiocall.services import events_service, numbers_service, profiles_service, settings_service
from audiocall.services.outcome import outcome_from_analysis, outcome_from_status

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

# Twilio errors caused by our setup rather than the number being called.
_CONFIG_ERROR_CODES = {20003, 21210, 21212}

_TERMINAL_STATUSES = {"completed", "failed", "no_answer", "disconnected"}
TERMINAL_STATUSES = frozenset(_TERMINAL_STATUSES)
_ACTIVE_STATUSES = ("queued", "ringing", "in_progress")

# Twilio REST error codes -> (event_type, admin-facing explanation). These are
# the usual reasons an outbound call is rejected before the phone ever rings —
# most of them are trial-account restrictions.
# https://www.twilio.com/docs/api/errors
_TWILIO_ERROR_HINTS: dict[int, tuple[str, str]] = {
    20003: ("provider_error", "Twilio authentication failed — check TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN."),
    21210: ("provider_error", "TWILIO_PHONE_NUMBER is not a number owned by (or verified on) this Twilio account."),
    21211: ("invalid_number", "Invalid 'To' phone number — use E.164 format, e.g. +919876543210."),
    21212: ("provider_error", "TWILIO_PHONE_NUMBER is not a valid caller number."),
    21214: ("invalid_number", "The 'To' number can't be reached by Twilio."),
    21215: ("provider_error", "Calling this country is disabled — enable it under Twilio Console → Voice → Settings → Geo permissions."),
    13227: ("provider_error", "Calling this country is disabled — enable it under Twilio Console → Voice → Settings → Geo permissions."),
    21217: ("invalid_number", "The 'To' phone number is not valid."),
    21219: ("provider_error", "Twilio trial accounts can only call verified numbers — add this number under Phone Numbers → Verified Caller IDs."),
}


class CustomerNotFound(Exception):
    """Raised when a customer_id does not resolve to a row."""


class TwilioCallFailed(Exception):
    """Raised when Twilio rejects/fails an outbound call creation request.
    `call_id` is the (now failed) call row, so callers can link to it.
    `config_error` means every call would fail the same way (credentials,
    host, caller ID), not just this customer's — the dialer pauses on it."""

    def __init__(
        self, reason: str, call_id: uuid.UUID | None = None, config_error: bool = False
    ) -> None:
        super().__init__(reason)
        self.call_id = call_id
        self.config_error = config_error


def map_twilio_status(twilio_status: str) -> str:
    return _TWILIO_STATUS_MAP.get(twilio_status, "failed")


def describe_twilio_error(exc: TwilioRestException) -> tuple[str, str]:
    """(event_type, human explanation) for a Twilio REST failure."""
    event_type, hint = _TWILIO_ERROR_HINTS.get(exc.code or 0, ("provider_error", ""))
    detail = f"Twilio error {exc.code}: {exc.msg}"
    return event_type, f"{hint} ({detail})" if hint else detail


# Calls whose post-call analysis has already been scheduled in this process —
# guards against two terminal transitions (stream end + Twilio status
# callback) both scheduling it.
_analysis_scheduled: set[uuid.UUID] = set()


def _schedule_analysis(call_id: uuid.UUID) -> None:
    """Fire post-call AI analysis once per call, in the background.

    Fire-and-forget (`asyncio.create_task`, not awaited): the caller (a
    webhook handler or the stream teardown) must return immediately.
    """
    if call_id in _analysis_scheduled:
        return
    _analysis_scheduled.add(call_id)

    # Local import: keeps module import order simple (summary_service imports
    # calls_service helpers for outcome updates).
    from audiocall.services import summary_service

    def _log_if_failed(task: asyncio.Task) -> None:
        exc = task.exception()
        if exc is not None:
            logger.error("post_call_processing(%s) raised: %s", call_id, exc)

    task = asyncio.create_task(summary_service.post_call_processing(call_id))
    task.add_done_callback(_log_if_failed)


def _apply_terminal_outcome(call: Call) -> None:
    """Set the lifecycle-derived outcome when a call first becomes terminal.
    AI analysis may refine it later (see summary_service)."""
    if call.status in _TERMINAL_STATUSES and call.outcome is None:
        call.outcome = outcome_from_status(call.status, call.error_reason)


async def get_customer(customer_id: uuid.UUID, org_id: uuid.UUID | None = None) -> Customer:
    """The customer; with `org_id`, only if they belong to that company."""
    async with get_session_factory()() as session:
        customer = await session.get(Customer, customer_id)
        if customer is None or (org_id is not None and customer.org_id != org_id):
            raise CustomerNotFound(f"No customer with id {customer_id}")
        return customer


async def get_or_create_customer_by_phone(org_id: uuid.UUID, phone: str) -> Customer:
    """Used for inbound calls, where there is no prior /call request to look up."""
    async with get_session_factory()() as session:
        customer = await session.scalar(
            select(Customer)
            .where(Customer.org_id == org_id, Customer.phone == phone)
            .order_by(Customer.created_at)
            .limit(1)
        )
        if customer is not None:
            return customer

        customer = Customer(org_id=org_id, name="Unknown caller", phone=phone)
        session.add(customer)
        await session.commit()
        await session.refresh(customer)
        return customer


async def create_call(
    customer_id: uuid.UUID,
    direction: str,
    channel: str = "phone",
    profile_id: uuid.UUID | None = None,
    *,
    org_id: uuid.UUID,
    from_number: str | None = None,
    to_number: str | None = None,
    phone_number_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
) -> Call:
    async with get_session_factory()() as session:
        call = Call(
            org_id=org_id,
            customer_id=customer_id,
            direction=direction,
            channel=channel,
            profile_id=profile_id,
            status="queued",
            from_number=from_number,
            to_number=to_number,
            phone_number_id=phone_number_id,
            campaign_id=campaign_id,
        )
        session.add(call)
        await session.commit()
        await session.refresh(call)
        return call


def active_call_window() -> timedelta:
    """A phone call older than this can't still be live (ring timeout + max
    conversation + slack): a row stuck non-terminal past it, e.g. after a
    lost status callback or a server restart, no longer holds a line."""
    return timedelta(seconds=config.RING_TIMEOUT_SECONDS + config.MAX_CALL_SECONDS + 120)


async def count_active_phone_calls(org_id: uuid.UUID | None = None) -> int:
    """Phone calls currently holding an AI line (manual, campaign and inbound),
    across the platform or for one company."""
    cutoff = datetime.now(timezone.utc) - active_call_window()
    query = (
        select(func.count())
        .select_from(Call)
        .where(
            Call.channel == "phone",
            Call.status.in_(_ACTIVE_STATUSES),
            Call.created_at >= cutoff,
            # Handed to a person: the line is up but no AI session is used.
            Call.transferred_to.is_(None),
        )
    )
    if org_id is not None:
        query = query.where(Call.org_id == org_id)
    async with get_session_factory()() as session:
        return await session.scalar(query) or 0


async def free_lines(org_id: uuid.UUID) -> int:
    """How many more phone calls may start now for this company: the lower
    of the platform's free lines (MAX_CONCURRENT_CALLS) and the company's
    own plan limit, if it has one."""
    free = config.MAX_CONCURRENT_CALLS - await count_active_phone_calls()
    from audiocall.db.models import Organization

    async with get_session_factory()() as session:
        org_limit = await session.scalar(
            select(Organization.max_concurrent_calls).where(Organization.id == org_id)
        )
    if org_limit is not None:
        free = min(free, org_limit - await count_active_phone_calls(org_id))
    return max(free, 0)


async def set_outcome(call_id: uuid.UUID, outcome: str) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.outcome = outcome
        await session.commit()


async def mark_capacity_transfer(call_id: uuid.UUID, number: str) -> None:
    """Inbound call sent straight to a person because every AI line was busy."""
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.transferred_to = number
        call.outcome = "transferred"
        call.error_reason = "capacity"
        await session.commit()


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
        call.status = status
        if error_reason is not None:
            call.error_reason = error_reason
        _apply_terminal_outcome(call)
        await session.commit()


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
        if call.status == "failed" and status != "failed" and call.error_reason in ("ai_error", "capacity"):
            # Our own failure verdict outranks Twilio's later "completed".
            return
        call.status = status
        if error_reason is not None:
            call.error_reason = error_reason
        _apply_terminal_outcome(call)
        await session.commit()


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
    transferred_to: str | None = None,
) -> None:
    """The AI's part of the call is over. With `transferred_to`, the call
    itself goes on with a person: it stays `in_progress` until Twilio's final
    status callback, and the outcome is `transferred`."""
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.end_time = end_time
        if call.start_time is not None:
            call.duration_seconds = int((end_time - call.start_time).total_seconds())
        if transferred_to is not None:
            call.transferred_to = transferred_to
            call.outcome = "transferred"
        elif status_override is not None:
            call.status = status_override
        elif call.status not in _TERMINAL_STATUSES:
            call.status = "disconnected"
        if error_reason is not None:
            call.error_reason = error_reason
        _apply_terminal_outcome(call)
        await session.commit()
    # The stream ending is the one moment the transcript is known complete
    # (the bridge flushes pending writes before calling this), so analysis is
    # triggered here rather than from Twilio's status callback, which can
    # arrive while the last turns are still being written.
    _schedule_analysis(call_id)


async def record_agent_assessment(
    call_id: uuid.UUID, lead_status: str | None, follow_up: bool | None
) -> None:
    """The agent's own end-of-call verdict (from its `end_call` tool). Sets the
    outcome and a preliminary lead status / follow-up flag, which post-call
    analysis then refines — and which remain if that analysis fails."""
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.outcome = outcome_from_analysis(lead_status)
        summary = await session.scalar(select(CallSummary).where(CallSummary.call_id == call_id))
        if summary is None:
            summary = CallSummary(call_id=call_id)
            session.add(summary)
        if summary.summary is None:  # analysis hasn't run yet
            summary.lead_status = lead_status
            summary.follow_up = follow_up
        await session.commit()


async def start_outbound_call(
    customer_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
) -> Call:
    """Look up the customer, create a `calls` row, pick a caller ID from the
    company's number pool, and dial through the company's Twilio account.

    Shared by `POST /call`, the dashboard's `POST /api/calls` and the
    campaign dialer. With `org_id`, the customer must belong to that company.
    `profile_id` overrides the customer's profile (campaigns).
    Raises `CustomerNotFound` or `TwilioCallFailed`; callers translate these to
    the appropriate HTTP response. A failure is also recorded on the call row
    (status=failed + a call event) so it shows up in the dashboard.
    """
    customer = await get_customer(customer_id, org_id)
    org_id = customer.org_id
    profile = await profiles_service.resolve_profile(org_id, profile_id or customer.profile_id)
    call = await create_call(
        customer.id,
        direction="outbound",
        channel="phone",
        profile_id=profile.id,
        org_id=org_id,
        to_number=customer.phone,
        campaign_id=campaign_id,
    )
    account = await settings_service.twilio_for(org_id)

    async def fail(event_type: str, reason: str, config_error: bool = False) -> TwilioCallFailed:
        logger.error("Outbound call %s failed: %s", call.id, reason)
        await events_service.record(call.id, event_type, reason)
        await set_status(call.id, "failed", error_reason=reason)
        return TwilioCallFailed(reason, call.id, config_error)

    if not is_valid_e164(customer.phone):
        raise await fail(
            "invalid_number",
            f"'{customer.phone}' is not a valid E.164 phone number (e.g. +919876543210).",
        )
    if not account.configured:
        raise await fail(
            "provider_error",
            "Twilio is not configured — connect it in Settings. Use 'Browser call' "
            "to demo the agent without a telephony provider.",
            config_error=True,
        )
    if config.is_local_host():
        raise await fail(
            "provider_error",
            f"SERVER_HOST is '{config.SERVER_HOST}', which Twilio can't reach. Set it to your "
            "public tunnel/deploy host (e.g. abc123.ngrok-free.app).",
            config_error=True,
        )

    picked = await numbers_service.pick_outbound_number(org_id, profile.id)
    if picked is None:
        raise await fail(
            "provider_error",
            "No caller number available: add an outbound-enabled number under Phone numbers, "
            "or a default caller number in Settings.",
            config_error=True,
        )
    from_number, phone_number_id = picked
    await _set_caller(call.id, from_number, phone_number_id)

    try:
        # The Twilio SDK is synchronous — run it off the event loop so a slow
        # API round-trip doesn't stall live audio for calls already running.
        twilio_call = await asyncio.to_thread(
            account.client.calls.create,
            to=customer.phone,
            from_=from_number,
            url=f"{config.HTTP_SCHEME}://{config.SERVER_HOST}/voice?call_id={call.id}",
            status_callback=f"{config.HTTP_SCHEME}://{config.SERVER_HOST}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
            timeout=config.RING_TIMEOUT_SECONDS,
        )
    except TwilioRestException as exc:
        event_type, reason = describe_twilio_error(exc)
        raise await fail(event_type, reason, exc.code in _CONFIG_ERROR_CODES) from exc
    except Exception as exc:  # network errors etc.
        raise await fail("provider_error", f"Could not reach Twilio: {exc}", True) from exc

    await set_twilio_sid(call.id, twilio_call.sid)
    call.twilio_call_sid = twilio_call.sid
    await events_service.record(
        call.id, "call_initiated", f"Twilio SID {twilio_call.sid} from {from_number}"
    )

    logger.info(
        "Outbound call initiated: call_id=%s  SID=%s  from=%s  to=%s",
        call.id,
        twilio_call.sid,
        from_number,
        customer.phone,
    )
    return call


async def _set_caller(call_id: uuid.UUID, from_number: str, phone_number_id: uuid.UUID | None) -> None:
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.from_number = from_number
        call.phone_number_id = phone_number_id
        await session.commit()


async def start_browser_call(customer_id: uuid.UUID, org_id: uuid.UUID) -> Call:
    """Create a call row for the browser (WebRTC microphone) demo channel.

    No telephony provider is involved: the dashboard opens `/browser-stream`
    and plays the customer's side itself. Everything downstream — agent,
    transcript, events, analysis — is identical to a phone call.
    """
    customer = await get_customer(customer_id, org_id)
    profile = await profiles_service.resolve_profile(org_id, customer.profile_id)
    call = await create_call(
        customer.id, direction="outbound", channel="browser", profile_id=profile.id, org_id=org_id
    )
    await events_service.record(call.id, "call_initiated", "Browser (WebRTC) call")
    return call


async def get_call(call_id: uuid.UUID) -> Call | None:
    async with get_session_factory()() as session:
        return await session.get(Call, call_id)


async def _twilio_client_for_sid(twilio_call_sid: str):  # noqa: ANN202
    """The Twilio client of the company whose call this is."""
    async with get_session_factory()() as session:
        org_id = await session.scalar(
            select(Call.org_id).where(Call.twilio_call_sid == twilio_call_sid)
        )
    return (await settings_service.twilio_for(org_id)).client


async def redirect_phone_call(twilio_call_sid: str, twiml: str) -> bool:
    """Replace a live call's TwiML (ends its media stream). False on failure."""
    try:
        client = await _twilio_client_for_sid(twilio_call_sid)
        await asyncio.to_thread(client.calls(twilio_call_sid).update, twiml=twiml)
        return True
    except Exception:
        logger.exception("Could not redirect Twilio call %s", twilio_call_sid)
        return False


async def hang_up_phone_call(twilio_call_sid: str, apology: str | None = None) -> None:
    """End a live Twilio call. With `apology`, speak it first (used when the
    AI fails mid-call, so the customer isn't left in dead air)."""
    try:
        client = await _twilio_client_for_sid(twilio_call_sid)
        if apology:
            twiml = f"<Response><Say>{xml_escape(apology)}</Say><Hangup/></Response>"
            await asyncio.to_thread(client.calls(twilio_call_sid).update, twiml=twiml)
        else:
            await asyncio.to_thread(client.calls(twilio_call_sid).update, status="completed")
    except Exception:
        logger.exception("Could not hang up Twilio call %s", twilio_call_sid)


async def list_calls(
    org_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    lead_status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    customer_name: str | None = None,
    follow_up: bool | None = None,
    outcome: str | None = None,
    channel: str | None = None,
    profile_id: uuid.UUID | None = None,
    direction: str | None = None,
    campaign_id: uuid.UUID | None = None,
) -> tuple[list[tuple[Call, Customer, CallSummary | None]], int]:
    """Returns `(rows, total)`, where each row is `(Call, Customer,
    CallSummary | None)`. All filters combine with AND semantics."""
    async with get_session_factory()() as session:
        base_query = (
            select(Call, Customer, CallSummary)
            .join(Customer, Call.customer_id == Customer.id)
            .outerjoin(CallSummary, CallSummary.call_id == Call.id)
        )
        count_query = (
            select(func.count(func.distinct(Call.id)))
            .select_from(Call)
            .join(Customer, Call.customer_id == Customer.id)
            .outerjoin(CallSummary, CallSummary.call_id == Call.id)
        )

        conditions = [Call.org_id == org_id]
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
        if follow_up is not None:
            conditions.append(
                CallSummary.follow_up.is_(True)
                if follow_up
                else or_(CallSummary.follow_up.is_(False), CallSummary.follow_up.is_(None))
            )
        if outcome is not None:
            conditions.append(Call.outcome == outcome)
        if channel is not None:
            conditions.append(Call.channel == channel)
        if profile_id is not None:
            conditions.append(Call.profile_id == profile_id)
        if direction is not None:
            conditions.append(Call.direction == direction)
        if campaign_id is not None:
            conditions.append(Call.campaign_id == campaign_id)

        for condition in conditions:
            base_query = base_query.where(condition)
            count_query = count_query.where(condition)

        total = await session.scalar(count_query) or 0
        result = await session.execute(
            base_query.order_by(Call.created_at.desc()).limit(limit).offset(offset)
        )
        rows = [(row[0], row[1], row[2]) for row in result.all()]
        return rows, total


async def get_call_detail(call_id: uuid.UUID, org_id: uuid.UUID) -> dict | None:
    """Returns a dict with the call, its customer, transcript, requirements,
    and summary — or None if the call doesn't exist in this company."""
    async with get_session_factory()() as session:
        call = await session.get(
            Call,
            call_id,
            options=[
                selectinload(Call.customer),
                selectinload(Call.messages),
                selectinload(Call.requirements),
                selectinload(Call.summary),
                selectinload(Call.events),
                selectinload(Call.profile),
            ],
        )
        if call is None or call.org_id != org_id:
            return None
        profile = call.profile or await profiles_service.get_default_profile(org_id)
        return {
            "call": call,
            "customer": call.customer,
            "messages": call.messages,
            "requirements": call.requirements,
            "summary": call.summary,
            "events": call.events,
            "profile": profile,
        }


def profile_to_dict(profile) -> dict:  # noqa: ANN001
    return {
        "id": str(profile.id),
        "name": profile.name,
        "agent_name": profile.agent_name,
        "industry": profile.industry,
        "description": profile.description,
        "products": profile.products,
        "call_objective": profile.call_objective,
        "greeting": profile.greeting,
        "language": profile.language,
        "fields": profile.fields,
        "transfer_number": profile.transfer_number,
    }


async def load_call_context(call_id: uuid.UUID) -> dict | None:
    """Customer + business profile for a live call, as plain dicts for the
    agent's session state. None if the call doesn't exist."""
    async with get_session_factory()() as session:
        call = await session.get(Call, call_id, options=[selectinload(Call.customer)])
        if call is None:
            return None
        customer = call.customer
        profile_id = call.profile_id or customer.profile_id
    profile = await profiles_service.resolve_profile(call.org_id, profile_id)
    if call.profile_id is None:
        # Inbound calls (and calls from before profiles existed) — pin the
        # profile that actually ran.
        async with get_session_factory()() as session:
            row = await session.get(Call, call_id)
            if row is not None:
                row.profile_id = profile.id
                await session.commit()
    known_name = customer.name if customer.name != "Unknown caller" else None
    # Facts the dashboard already holds count as collected from the start, so
    # the agent confirms rather than asks for them.
    field_keys = {f["key"] for f in profile.fields}
    prefilled = {
        key: value
        for key, value in (("customer_name", known_name), ("company_name", customer.company))
        if value and key in field_keys
    }
    return {
        "collected": prefilled,
        "direction": call.direction or "outbound",
        "from_number": call.from_number,
        "to_number": call.to_number,
        "customer": {
            "name": known_name,
            "company": customer.company,
            "purpose": customer.purpose,
            "product": customer.product,
        },
        "profile": profile_to_dict(profile),
    }


async def get_call_by_twilio_sid(twilio_call_sid: str) -> Call | None:
    async with get_session_factory()() as session:
        return await session.scalar(select(Call).where(Call.twilio_call_sid == twilio_call_sid))


async def profile_names(org_id: uuid.UUID) -> dict[uuid.UUID, str]:
    from audiocall.db.models import BusinessProfile

    async with get_session_factory()() as session:
        result = await session.execute(
            select(BusinessProfile.id, BusinessProfile.name).where(BusinessProfile.org_id == org_id)
        )
        return {row.id: row.name for row in result}


async def transfer_context(call_id: uuid.UUID) -> tuple[str | None, str | None]:
    """(customer name, the agent's hand-off summary) for the transfer whisper."""
    from audiocall.db.models import CallEvent

    async with get_session_factory()() as session:
        call = await session.get(Call, call_id, options=[selectinload(Call.customer)])
        if call is None:
            return None, None
        name = call.customer.name if call.customer.name != "Unknown caller" else None
        summary = await session.scalar(
            select(CallEvent.detail)
            .where(CallEvent.call_id == call_id, CallEvent.event_type == "transfer_requested")
            .order_by(CallEvent.created_at.desc())
            .limit(1)
        )
        return name, summary
