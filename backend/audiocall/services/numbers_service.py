"""The phone-number pool: outbound caller-ID selection, inbound routing, and
configuring a number's webhooks on Twilio.

See ARCHITECTURE.md, "Several numbers".
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


class NumberConflict(Exception):
    pass


class TwilioSyncFailed(Exception):
    pass


async def list_numbers() -> list[PhoneNumber]:
    async with get_session_factory()() as session:
        result = await session.execute(select(PhoneNumber).order_by(PhoneNumber.created_at))
        return list(result.scalars().all())


async def get_number(number_id: uuid.UUID) -> PhoneNumber | None:
    async with get_session_factory()() as session:
        return await session.get(PhoneNumber, number_id)


async def get_by_number(number: str) -> PhoneNumber | None:
    async with get_session_factory()() as session:
        return await session.scalar(select(PhoneNumber).where(PhoneNumber.number == number))


async def create_number(data: dict[str, Any]) -> PhoneNumber:
    if await get_by_number(data["number"]) is not None:
        raise NumberConflict(f"{data['number']} is already registered")
    async with get_session_factory()() as session:
        row = PhoneNumber(**data)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def update_number(number_id: uuid.UUID, data: dict[str, Any]) -> PhoneNumber | None:
    if "number" in data:
        existing = await get_by_number(data["number"])
        if existing is not None and existing.id != number_id:
            raise NumberConflict(f"{data['number']} is already registered")
    async with get_session_factory()() as session:
        row = await session.get(PhoneNumber, number_id)
        if row is None:
            return None
        for key, value in data.items():
            setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return row


async def delete_number(number_id: uuid.UUID) -> bool:
    async with get_session_factory()() as session:
        row = await session.get(PhoneNumber, number_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def pick_outbound_number(profile_id: uuid.UUID | None) -> tuple[str, uuid.UUID | None] | None:
    """Caller ID for an outbound call: `(number, phone_number_id)`.

    The profile's own numbers first, then the shared pool, then
    TWILIO_PHONE_NUMBER (id None). The least recently used number wins and
    is claimed with SKIP LOCKED, so parallel dials spread across the pool
    instead of all taking the same row. None when nothing is configured.
    """
    tiers = []
    if profile_id is not None:
        tiers.append(PhoneNumber.profile_id == profile_id)
    tiers.append(PhoneNumber.profile_id.is_(None))

    async with get_session_factory()() as session:
        for tier in tiers:
            row = await session.scalar(
                select(PhoneNumber)
                .where(tier, PhoneNumber.is_active.is_(True), PhoneNumber.outbound_enabled.is_(True))
                .order_by(PhoneNumber.last_used_at.asc().nulls_first(), PhoneNumber.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is not None:
                row.last_used_at = datetime.now(timezone.utc)
                number, number_id = row.number, row.id
                await session.commit()
                return number, number_id
    if config.TWILIO_PHONE_NUMBER:
        return config.TWILIO_PHONE_NUMBER, None
    return None


async def sync_twilio(number_id: uuid.UUID) -> PhoneNumber:
    """Point the Twilio number's incoming-call webhook at /voice and its
    status callback at /call-status, so inbound calls reach the agent
    without editing the Twilio console by hand."""
    row = await get_number(number_id)
    if row is None:
        raise TwilioSyncFailed("Number not found")
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        raise TwilioSyncFailed("Twilio is not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).")
    if config.is_local_host():
        raise TwilioSyncFailed(
            f"SERVER_HOST is '{config.SERVER_HOST}', which Twilio can't reach. "
            "Set it to your public host first."
        )
    base = config.public_url()

    def _sync() -> None:
        matches = config.twilio_client.incoming_phone_numbers.list(phone_number=row.number, limit=1)
        if not matches:
            raise TwilioSyncFailed(f"{row.number} is not a number on this Twilio account.")
        config.twilio_client.incoming_phone_numbers(matches[0].sid).update(
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
