"""Each company's phone-number pool: outbound caller-ID selection, inbound
routing, and configuring a number's webhooks on the company's Twilio account.

A number is unique across the whole platform (a Twilio number can only send
its calls to one place), so inbound routing by the dialled number also tells
us which company the call is for. See ARCHITECTURE.md, "Several numbers".
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from audiocall.core import config
from audiocall.db.models import PhoneNumber
from audiocall.db.session import get_session_factory
from audiocall.services import settings_service


class NumberConflict(Exception):
    pass


class TwilioSyncFailed(Exception):
    pass


async def list_numbers(org_id: uuid.UUID) -> list[PhoneNumber]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(PhoneNumber).where(PhoneNumber.org_id == org_id).order_by(PhoneNumber.created_at)
        )
        return list(result.scalars().all())


async def get_number(number_id: uuid.UUID, org_id: uuid.UUID) -> PhoneNumber | None:
    async with get_session_factory()() as session:
        row = await session.get(PhoneNumber, number_id)
        return row if row is not None and row.org_id == org_id else None


async def get_by_number(number: str) -> PhoneNumber | None:
    """Platform-wide lookup (inbound routing): whichever company owns it."""
    async with get_session_factory()() as session:
        return await session.scalar(select(PhoneNumber).where(PhoneNumber.number == number))


async def create_number(org_id: uuid.UUID, data: dict[str, Any]) -> PhoneNumber:
    if await get_by_number(data["number"]) is not None:
        raise NumberConflict(f"{data['number']} is already registered")
    async with get_session_factory()() as session:
        row = PhoneNumber(org_id=org_id, **data)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def update_number(
    number_id: uuid.UUID, org_id: uuid.UUID, data: dict[str, Any]
) -> PhoneNumber | None:
    if "number" in data:
        existing = await get_by_number(data["number"])
        if existing is not None and existing.id != number_id:
            raise NumberConflict(f"{data['number']} is already registered")
    async with get_session_factory()() as session:
        row = await session.get(PhoneNumber, number_id)
        if row is None or row.org_id != org_id:
            return None
        for key, value in data.items():
            setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return row


async def delete_number(number_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        row = await session.get(PhoneNumber, number_id)
        if row is None or row.org_id != org_id:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def pick_outbound_number(
    org_id: uuid.UUID, profile_id: uuid.UUID | None
) -> tuple[str, uuid.UUID | None] | None:
    """Caller ID for one of a company's outbound calls: `(number, phone_number_id)`.

    The profile's own numbers first, then the company's shared pool, then the
    company's default caller number (its own, or the platform's TWILIO_PHONE_
    NUMBER; id None). The least recently used number wins and is claimed with
    SKIP LOCKED, so parallel dials spread across the pool instead of all
    taking the same row. None when nothing is configured.
    """
    tiers = []
    if profile_id is not None:
        tiers.append(PhoneNumber.profile_id == profile_id)
    tiers.append(PhoneNumber.profile_id.is_(None))

    async with get_session_factory()() as session:
        for tier in tiers:
            row = await session.scalar(
                select(PhoneNumber)
                .where(
                    PhoneNumber.org_id == org_id,
                    tier,
                    PhoneNumber.is_active.is_(True),
                    PhoneNumber.outbound_enabled.is_(True),
                )
                .order_by(PhoneNumber.last_used_at.asc().nulls_first(), PhoneNumber.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is not None:
                row.last_used_at = datetime.now(timezone.utc)
                number, number_id = row.number, row.id
                await session.commit()
                return number, number_id
    fallback = (await settings_service.twilio_for(org_id)).phone_number
    return (fallback, None) if fallback else None


async def sync_twilio(number_id: uuid.UUID, org_id: uuid.UUID) -> PhoneNumber:
    """Point the Twilio number's incoming-call webhook at /voice and its
    status callback at /call-status, so inbound calls reach the agent
    without editing the Twilio console by hand."""
    row = await get_number(number_id, org_id)
    if row is None:
        raise TwilioSyncFailed("Number not found")
    account = await settings_service.twilio_for(org_id)
    if not account.configured:
        raise TwilioSyncFailed("Twilio isn't connected yet — add the account in Settings.")
    if config.is_local_host():
        raise TwilioSyncFailed(
            f"SERVER_HOST is '{config.SERVER_HOST}', which Twilio can't reach. "
            "Set it to your public host first."
        )
    base = config.public_url()

    def _sync() -> None:
        matches = account.client.incoming_phone_numbers.list(phone_number=row.number, limit=1)
        if not matches:
            raise TwilioSyncFailed(f"{row.number} is not a number on this Twilio account.")
        account.client.incoming_phone_numbers(matches[0].sid).update(
            voice_url=f"{base}/voice",
            voice_method="POST",
            status_callback=f"{base}/call-status",
            status_callback_method="POST",
        )

    try:
        await asyncio.to_thread(_sync)
    except TwilioSyncFailed:
        raise
    except Exception as exc:  # Twilio REST / network errors
        raise TwilioSyncFailed(f"Twilio rejected the update: {exc}") from exc
    return row
