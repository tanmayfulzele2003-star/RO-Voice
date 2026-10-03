"""Telephony features against a real Postgres: the number pool, inbound
routing, the campaign dialer and the transfer webhooks.

Twilio and Gemini stay faked. Runs only with RUN_DB_TESTS=1 and a migrated
database at DATABASE_URL (CI provides both); every row it creates is deleted
afterwards.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="needs RUN_DB_TESTS=1 and a migrated Postgres"
)

from audiocall import dialer  # noqa: E402
from audiocall.core import config  # noqa: E402
from audiocall.db import session as db_session  # noqa: E402
from audiocall.db.models import Call, CampaignContact  # noqa: E402
from audiocall.services import (  # noqa: E402
    calls_service,
    campaigns_service,
    numbers_service,
    profiles_service,
)
from audiocall.profiles import DEFAULT_RO_PROFILE  # noqa: E402


def _phone() -> str:
    return "+1555" + str(uuid.uuid4().int)[:7]


@pytest.fixture
async def db():
    # The engine is cached per process, but each test has its own event loop.
    db_session.get_engine.cache_clear()
    created = {"customers": [], "profiles": [], "numbers": [], "campaigns": []}
    yield created
    async with db_session.get_engine().begin() as conn:
        customers = created["customers"]
        if created["campaigns"]:
            await conn.execute(
                text("DELETE FROM campaigns WHERE id = ANY(:ids)"), {"ids": created["campaigns"]}
            )
        if customers:
            calls = "SELECT id FROM calls WHERE customer_id = ANY(:ids)"
            for table in ("call_events", "conversation_messages", "requirements", "call_summaries"):
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE call_id IN ({calls})"), {"ids": customers}
                )
            await conn.execute(
                text("DELETE FROM campaign_contacts WHERE customer_id = ANY(:ids)"), {"ids": customers}
            )
            await conn.execute(text("DELETE FROM calls WHERE customer_id = ANY(:ids)"), {"ids": customers})
            await conn.execute(text("DELETE FROM customers WHERE id = ANY(:ids)"), {"ids": customers})
        if created["numbers"]:
            await conn.execute(
                text("DELETE FROM phone_numbers WHERE id = ANY(:ids)"), {"ids": created["numbers"]}
            )
        if created["profiles"]:
            await conn.execute(
                text("DELETE FROM business_profiles WHERE id = ANY(:ids)"), {"ids": created["profiles"]}
            )
    await db_session.get_engine().dispose()


async def _profile(db, **extra):
    profile = await profiles_service.create_profile(
        {**DEFAULT_RO_PROFILE, "name": f"Test {uuid.uuid4().hex[:6]}", **extra}
    )
    db["profiles"].append(profile.id)
    return profile


async def _number(db, **data):
    row = await numbers_service.create_number({"number": _phone(), **data})
    db["numbers"].append(row.id)
    return row


async def _customer(db, phone=None, profile_id=None):
    from audiocall.services import customers_service

    customer = await customers_service.create_customer(
        {"name": "Test Customer", "phone": phone or _phone(), "profile_id": profile_id}
    )
    db["customers"].append(customer.id)
    return customer


# ── Number pool ──────────────────────────────────────────────────────────────
async def test_outbound_number_round_robin_then_shared_pool_then_env(db, monkeypatch):
    sales = await _profile(db)
    other = await _profile(db)
    a = await _number(db, profile_id=sales.id)
    b = await _number(db, profile_id=sales.id)
    await _number(db, profile_id=sales.id, outbound_enabled=False)  # never picked
    picks = [(await numbers_service.pick_outbound_number(sales.id))[0] for _ in range(3)]
    assert picks == [a.number, b.number, a.number]

    # Another profile with no numbers of its own uses the shared pool …
    shared = await _number(db)
    assert await numbers_service.pick_outbound_number(other.id) == (shared.number, shared.id)

    # … and with nothing usable in the pool, the env number.
    await numbers_service.update_number(shared.id, {"is_active": False})
    monkeypatch.setattr(config, "TWILIO_PHONE_NUMBER", "+15550000000")
    picked = await numbers_service.pick_outbound_number(other.id)
    if picked[1] is None:  # other shared numbers may exist in a dev database
        assert picked == ("+15550000000", None)


# ── Inbound routing + transfer webhooks ──────────────────────────────────────
async def _post(path, data):
    from audiocall.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(path, data=data)


async def test_inbound_call_routed_by_dialled_number(db):
    solar = await _profile(db)
    number = await _number(db, profile_id=solar.id)
    caller = _phone()

    res = await _post("/voice", {"CallSid": f"CA{uuid.uuid4().hex}", "From": caller, "To": number.number})
    assert res.status_code == 200
    root = ElementTree.fromstring(res.text)
    call_id = uuid.UUID(root.find("./Connect/Stream/Parameter").get("value"))

    call = await calls_service.get_call(call_id)
    db["customers"].append(call.customer_id)
    assert call.direction == "inbound"
    assert call.profile_id == solar.id  # the dialled business answers
    assert (call.from_number, call.to_number, call.phone_number_id) == (caller, number.number, number.id)
    ctx = await calls_service.load_call_context(call_id)
    assert ctx["direction"] == "inbound"


async def test_inbound_to_disabled_number_is_declined(db):
    number = await _number(db, inbound_enabled=False)
    res = await _post("/voice", {"CallSid": f"CA{uuid.uuid4().hex}", "From": _phone(), "To": number.number})
    root = ElementTree.fromstring(res.text)
    assert root.find("Say") is not None and root.find("Hangup") is not None
    assert root.find("Connect") is None


async def test_inbound_over_capacity_goes_to_a_person(db, monkeypatch):
    from audiocall import main

    monkeypatch.setattr(main, "MAX_CONCURRENT_CALLS", 0)
    profile = await _profile(db, transfer_number="+15559990000")
    number = await _number(db, profile_id=profile.id)
    customer = await _customer(db)

    res = await _post("/voice", {"CallSid": f"CA{uuid.uuid4().hex}", "From": customer.phone, "To": number.number})
    root = ElementTree.fromstring(res.text)
    assert root.find("./Dial/Number").text == "+15559990000"
    call_id = uuid.UUID(root.find("Dial").get("action").split("call_id=")[1])
    call = await calls_service.get_call(call_id)
    assert call.transferred_to == "+15559990000" and call.outcome == "transferred"
    assert call.status == "queued"  # not "failed": the caller is being helped


async def test_transfer_status_fallback_and_whisper(db):
    customer = await _customer(db)
    call = await calls_service.create_call(customer.id, direction="outbound")
    from audiocall.services import events_service

    await events_service.record(call.id, "transfer_requested", "Wants a 500 LPH quote")

    whisper = await _post(f"/transfer-whisper?call_id={call.id}", {})
    assert "Wants a 500 LPH quote" in ElementTree.fromstring(whisper.text).find("Say").text

    res = await _post(f"/transfer-status?call_id={call.id}", {"DialCallStatus": "no-answer"})
    assert ElementTree.fromstring(res.text).find("Say") is not None
    assert (await calls_service.get_call(call.id)).outcome == "callback"

    res = await _post(f"/transfer-status?call_id={call.id}", {"DialCallStatus": "completed"})
    assert ElementTree.fromstring(res.text).find("Hangup") is not None


# ── Campaign dialer ──────────────────────────────────────────────────────────
async def test_campaign_dials_in_parallel_retries_and_completes(db, monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", 1000)
    monkeypatch.setattr(config, "DIAL_CALLS_PER_SECOND", 0)
    dialled = []

    async def fake_start(customer_id, profile_id=None, campaign_id=None):
        call = await calls_service.create_call(customer_id, "outbound", campaign_id=campaign_id)
        dialled.append(customer_id)
        return call

    monkeypatch.setattr(dialer.calls_service, "start_outbound_call", fake_start)

    customers = [await _customer(db) for _ in range(3)]
    campaign = await campaigns_service.create_campaign(
        {"name": "Test", "max_concurrent": 2, "max_attempts": 2, "retry_delay_minutes": 1},
        [c.id for c in customers] + [customers[0].id],  # duplicate ignored
    )
    db["campaigns"].append(campaign.id)
    assert await dialer.tick() == 0  # draft: nothing dials

    await campaigns_service.set_campaign_status(campaign.id, "start")
    assert await dialer.tick() == 2  # capped by max_concurrent
    assert await dialer.tick() == 0  # both lines still busy

    _, counts, contacts = await campaigns_service.get_campaign_detail(campaign.id)
    assert counts == {"dialing": 2, "pending": 1}
    first, second = [c for c in contacts if c.status == "dialing"]
    await calls_service.set_status(first.last_call_id, "no_answer")
    await calls_service.set_status(second.last_call_id, "completed")

    assert await dialer.tick() == 1  # third customer takes a freed line
    _, counts, contacts = await campaigns_service.get_campaign_detail(campaign.id)
    retry = next(c for c in contacts if c.id == first.id)
    assert retry.status == "pending" and retry.attempts == 1
    assert retry.next_attempt_at > datetime.now(timezone.utc)  # not before the retry delay
    assert next(c for c in contacts if c.id == second.id).status == "completed"

    # Retry becomes due; the third call ends; the retry is dialled and fails for good.
    async with db_session.get_session_factory()() as session:
        row = await session.get(CampaignContact, first.id)
        row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    third = next(c for c in contacts if c.status == "dialing")
    await calls_service.set_status(third.last_call_id, "completed")
    assert await dialer.tick() == 1
    _, _, contacts = await campaigns_service.get_campaign_detail(campaign.id)
    retry = next(c for c in contacts if c.id == first.id)
    assert retry.attempts == 2
    await calls_service.set_status(retry.last_call_id, "no_answer")

    await dialer.tick()
    found, counts, _ = await campaigns_service.get_campaign_detail(campaign.id)
    assert counts == {"completed": 2, "failed": 1}
    assert found.status == "completed" and found.completed_at is not None
    # Everyone once, plus one retry for the unanswered customer.
    assert sorted(map(str, dialled)) == sorted(map(str, [*[c.id for c in customers], first.customer_id]))


async def test_dialer_respects_global_line_limit(db, monkeypatch):
    monkeypatch.setattr(config, "DIAL_CALLS_PER_SECOND", 0)
    busy = await calls_service.count_active_phone_calls()
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", busy + 1)

    async def fake_start(customer_id, profile_id=None, campaign_id=None):
        return await calls_service.create_call(customer_id, "outbound", campaign_id=campaign_id)

    monkeypatch.setattr(dialer.calls_service, "start_outbound_call", fake_start)
    customers = [await _customer(db) for _ in range(3)]
    campaign = await campaigns_service.create_campaign(
        {"name": "Test", "max_concurrent": 10, "max_attempts": 1, "retry_delay_minutes": 1},
        [c.id for c in customers],
    )
    db["campaigns"].append(campaign.id)
    await campaigns_service.set_campaign_status(campaign.id, "start")
    assert await dialer.tick() == 1


async def test_cancel_drops_pending_contacts(db):
    customers = [await _customer(db) for _ in range(2)]
    campaign = await campaigns_service.create_campaign(
        {"name": "Test", "max_concurrent": 1, "max_attempts": 1, "retry_delay_minutes": 1},
        [c.id for c in customers],
    )
    db["campaigns"].append(campaign.id)
    await campaigns_service.set_campaign_status(campaign.id, "start")
    await campaigns_service.set_campaign_status(campaign.id, "cancel")
    _, counts, _ = await campaigns_service.get_campaign_detail(campaign.id)
    assert counts == {"cancelled": 2}
    with pytest.raises(campaigns_service.InvalidTransition):
        await campaigns_service.set_campaign_status(campaign.id, "start")


async def test_failed_dial_is_linked_for_retry(db, monkeypatch):
    """A rejection specific to one number still creates a (failed) call row;
    the contact keeps it so reconcile can decide on a retry."""
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", 1000)
    monkeypatch.setattr(config, "DIAL_CALLS_PER_SECOND", 0)
    customer = await _customer(db, phone="12345")  # not E.164: fails for this customer only
    campaign = await campaigns_service.create_campaign(
        {"name": "Test", "max_concurrent": 1, "max_attempts": 2, "retry_delay_minutes": 1},
        [customer.id],
    )
    db["campaigns"].append(campaign.id)
    await campaigns_service.set_campaign_status(campaign.id, "start")
    await dialer.tick()
    await dialer.tick()  # reconcile the failed call
    _, _, contacts = await campaigns_service.get_campaign_detail(campaign.id)
    assert contacts[0].status == "pending" and contacts[0].last_outcome == "failed"
    async with db_session.get_session_factory()() as session:
        call = await session.get(Call, contacts[0].last_call_id)
        assert call.status == "failed" and call.campaign_id == campaign.id


async def test_config_error_pauses_campaign_without_spending_attempts(db, monkeypatch):
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", 1000)
    monkeypatch.setattr(config, "DIAL_CALLS_PER_SECOND", 0)
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "")  # every call would fail
    customers = [await _customer(db) for _ in range(3)]
    campaign = await campaigns_service.create_campaign(
        {"name": "Test", "max_concurrent": 3, "max_attempts": 2, "retry_delay_minutes": 1},
        [c.id for c in customers],
    )
    db["campaigns"].append(campaign.id)
    await campaigns_service.set_campaign_status(campaign.id, "start")
    assert await dialer.tick() == 0  # stops at the first config failure, nothing placed

    found, counts, contacts = await campaigns_service.get_campaign_detail(campaign.id)
    assert found.status == "paused" and "not configured" in found.status_reason
    assert counts == {"pending": 3}
    assert all(c.attempts == 0 for c in contacts)
    assert sum(1 for c in contacts if c.last_call_id) == 1  # the failed call is still linked

    await campaigns_service.set_campaign_status(campaign.id, "start")  # after fixing config
    found, _, _ = await campaigns_service.get_campaign_detail(campaign.id)
    assert found.status == "running" and found.status_reason is None
