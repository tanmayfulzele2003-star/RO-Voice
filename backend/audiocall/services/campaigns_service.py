"""Campaigns: batches of outbound calls dialled by the background dialer.

This module holds the database side (CRUD, claiming contacts, reconciling
finished calls). The loop that drives it lives in audiocall/dialer.py. See
ARCHITECTURE.md, "Many calls at once: campaigns".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from audiocall.db.models import Call, Campaign, CampaignContact, Customer
from audiocall.db.session import get_session_factory
from audiocall.services.calls_service import TERMINAL_STATUSES, active_call_window

CAMPAIGN_STATUSES = ("draft", "running", "paused", "completed", "cancelled")
CONTACT_STATUSES = ("pending", "dialing", "completed", "failed", "cancelled")

# Call results worth another attempt.
_RETRYABLE_STATUSES = {"no_answer", "failed"}


class CampaignNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


def next_contact_state(
    call_status: str | None,
    call_outcome: str | None,
    attempts: int,
    max_attempts: int,
) -> str:
    """What a dialled contact becomes once its call is over.

    "pending" means retry later. Unanswered or failed calls are retried while
    attempts remain. A call that got through is done, whatever its outcome.
    """
    retryable = call_status in _RETRYABLE_STATUSES or call_outcome in ("no_answer", "failed")
    if not retryable:
        return "completed"
    if attempts < max_attempts:
        return "pending"
    return "failed"


# ── CRUD ─────────────────────────────────────────────────────────────────────
async def create_campaign(
    org_id: uuid.UUID, data: dict[str, Any], customer_ids: list[uuid.UUID]
) -> Campaign:
    """Customers outside the company are silently left out."""
    async with get_session_factory()() as session:
        found = set(
            (
                await session.execute(
                    select(Customer.id).where(
                        Customer.id.in_(customer_ids), Customer.org_id == org_id
                    )
                )
            )
            .scalars()
            .all()
        )
        campaign = Campaign(org_id=org_id, status="draft", **data)
        session.add(campaign)
        await session.flush()
        seen: set[uuid.UUID] = set()
        for customer_id in customer_ids:
            if customer_id in found and customer_id not in seen:
                seen.add(customer_id)
                session.add(CampaignContact(campaign_id=campaign.id, customer_id=customer_id))
        await session.commit()
        await session.refresh(campaign)
        return campaign


async def list_campaigns(org_id: uuid.UUID) -> list[tuple[Campaign, dict[str, int]]]:
    async with get_session_factory()() as session:
        campaigns = list(
            (
                await session.execute(
                    select(Campaign)
                    .where(Campaign.org_id == org_id)
                    .order_by(Campaign.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        counts = await _contact_counts(session, [c.id for c in campaigns])
        return [(c, counts.get(c.id, {})) for c in campaigns]


async def get_campaign_detail(
    campaign_id: uuid.UUID, org_id: uuid.UUID | None = None
) -> tuple[Campaign, dict[str, int], list[CampaignContact]] | None:
    """With `org_id`, None unless the campaign belongs to that company."""
    async with get_session_factory()() as session:
        campaign = await session.get(Campaign, campaign_id)
        if campaign is None or (org_id is not None and campaign.org_id != org_id):
            return None
        contacts = list(
            (
                await session.execute(
                    select(CampaignContact)
                    .where(CampaignContact.campaign_id == campaign_id)
                    .options(selectinload(CampaignContact.customer))
                    .order_by(CampaignContact.created_at)
                )
            )
            .scalars()
            .all()
        )
        counts = (await _contact_counts(session, [campaign_id])).get(campaign_id, {})
        return campaign, counts, contacts


async def _contact_counts(session, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:  # noqa: ANN001
    if not campaign_ids:
        return {}
    result = await session.execute(
        select(CampaignContact.campaign_id, CampaignContact.status, func.count())
        .where(CampaignContact.campaign_id.in_(campaign_ids))
        .group_by(CampaignContact.campaign_id, CampaignContact.status)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for campaign_id, status, n in result.all():
        counts.setdefault(campaign_id, {})[status] = n
    return counts


async def set_campaign_status(
    campaign_id: uuid.UUID, action: str, org_id: uuid.UUID | None = None
) -> Campaign:
    """start | pause | cancel. Pausing stops new dials; calls already
    connected finish normally. Cancelling also drops pending contacts."""
    allowed = {
        "start": {"draft", "paused"},
        "pause": {"running"},
        "cancel": {"draft", "running", "paused"},
    }
    async with get_session_factory()() as session:
        campaign = await session.get(Campaign, campaign_id, with_for_update=True)
        if campaign is None or (org_id is not None and campaign.org_id != org_id):
            raise CampaignNotFound(f"No campaign with id {campaign_id}")
        if campaign.status not in allowed[action]:
            raise InvalidTransition(f"Can't {action} a {campaign.status} campaign")
        now = datetime.now(timezone.utc)
        campaign.status_reason = None
        if action == "start":
            campaign.status = "running"
            campaign.started_at = campaign.started_at or now
        elif action == "pause":
            campaign.status = "paused"
        else:
            campaign.status = "cancelled"
            campaign.completed_at = now
            await session.execute(
                update(CampaignContact)
                .where(
                    CampaignContact.campaign_id == campaign_id,
                    CampaignContact.status == "pending",
                )
                .values(status="cancelled")
            )
        await session.commit()
        await session.refresh(campaign)
        return campaign


async def delete_campaign(campaign_id: uuid.UUID, org_id: uuid.UUID | None = None) -> bool:
    async with get_session_factory()() as session:
        campaign = await session.get(Campaign, campaign_id)
        if campaign is None or (org_id is not None and campaign.org_id != org_id):
            return False
        if campaign.status in ("running", "paused"):
            raise InvalidTransition("Cancel the campaign before deleting it")
        await session.delete(campaign)
        await session.commit()
        return True


# ── Dialer support ───────────────────────────────────────────────────────────
async def reconcile_dialing_contacts() -> int:
    """Settle contacts whose call has finished: done, or back to pending for
    a retry. Returns how many changed."""
    now = datetime.now(timezone.utc)
    stale_before = now - active_call_window()
    changed = 0
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(CampaignContact, Call, Campaign)
                .join(Campaign, Campaign.id == CampaignContact.campaign_id)
                .outerjoin(Call, Call.id == CampaignContact.last_call_id)
                .where(CampaignContact.status == "dialing")
                .with_for_update(of=CampaignContact, skip_locked=True)
            )
        ).all()
        for contact, call, campaign in rows:
            if call is None:
                # The dial itself crashed before a call row existed.
                status, outcome = "failed", "failed"
            elif call.status in TERMINAL_STATUSES:
                status, outcome = call.status, call.outcome
            elif call.transferred_to is not None:
                # With a person now: the agent's part (and the campaign slot) is done.
                status, outcome = "completed", call.outcome
            elif call.created_at < stale_before:
                status, outcome = "failed", call.outcome or "failed"
            else:
                continue  # still live
            contact.last_outcome = outcome or status
            contact.status = next_contact_state(
                status, outcome, contact.attempts, campaign.max_attempts
            )
            if contact.status == "pending":
                contact.next_attempt_at = now + timedelta(minutes=campaign.retry_delay_minutes)
            changed += 1
        await session.commit()
    return changed


async def running_campaigns() -> list[Campaign]:
    async with get_session_factory()() as session:
        return list(
            (
                await session.execute(
                    select(Campaign)
                    .where(Campaign.status == "running")
                    .order_by(Campaign.started_at)
                )
            )
            .scalars()
            .all()
        )


async def claim_contacts(campaign: Campaign, global_free: int) -> list[CampaignContact]:
    """Mark up to the free slots' worth of due contacts `dialing` and return
    them. SKIP LOCKED: two dialer processes never claim the same contact."""
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as session:
        dialing = (
            await session.scalar(
                select(func.count())
                .select_from(CampaignContact)
                .where(
                    CampaignContact.campaign_id == campaign.id,
                    CampaignContact.status == "dialing",
                )
            )
            or 0
        )
        slots = min(campaign.max_concurrent - dialing, global_free)
        if slots <= 0:
            return []
        contacts = list(
            (
                await session.execute(
                    select(CampaignContact)
                    .where(
                        CampaignContact.campaign_id == campaign.id,
                        CampaignContact.status == "pending",
                        (CampaignContact.next_attempt_at.is_(None))
                        | (CampaignContact.next_attempt_at <= now),
                    )
                    .order_by(CampaignContact.next_attempt_at.asc().nulls_first(), CampaignContact.created_at)
                    .limit(slots)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for contact in contacts:
            contact.status = "dialing"
            contact.attempts += 1
            contact.next_attempt_at = None
        await session.commit()
        return contacts


async def attach_call(contact_id: uuid.UUID, call_id: uuid.UUID | None, failed: bool = False) -> None:
    """Record the call placed for a claimed contact. `failed` with no call
    (e.g. the customer was deleted) ends the contact outright."""
    async with get_session_factory()() as session:
        contact = await session.get(CampaignContact, contact_id)
        if contact is None:
            return
        contact.last_call_id = call_id
        if failed and call_id is None:
            contact.status = "failed"
            contact.last_outcome = "failed"
        await session.commit()


async def pause_for_config_error(
    campaign_id: uuid.UUID,
    reason: str,
    contact_ids: list[uuid.UUID],
    failed_contact_id: uuid.UUID,
    call_id: uuid.UUID | None,
) -> None:
    """Every call would fail the same way (credentials, host, caller ID):
    pause instead of burning each customer's attempts, and hand the claimed
    contacts' attempts back. Resuming after the fix re-dials them."""
    async with get_session_factory()() as session:
        campaign = await session.get(Campaign, campaign_id, with_for_update=True)
        if campaign is not None and campaign.status == "running":
            campaign.status = "paused"
            campaign.status_reason = reason
        contacts = (
            await session.execute(
                select(CampaignContact).where(
                    CampaignContact.id.in_(contact_ids), CampaignContact.status == "dialing"
                )
            )
        ).scalars()
        for contact in contacts:
            contact.status = "pending"
            contact.attempts = max(0, contact.attempts - 1)
            contact.next_attempt_at = None
            if contact.id == failed_contact_id:
                contact.last_call_id = call_id
                contact.last_outcome = "failed"
        await session.commit()


async def complete_finished_campaigns() -> int:
    """Running campaigns with nothing pending or dialing are complete."""
    async with get_session_factory()() as session:
        open_contacts = (
            select(CampaignContact.id)
            .where(
                CampaignContact.campaign_id == Campaign.id,
                CampaignContact.status.in_(("pending", "dialing")),
            )
            .exists()
        )
        result = await session.execute(
            update(Campaign)
            .where(Campaign.status == "running", ~open_contacts)
            .values(status="completed", completed_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return result.rowcount or 0
