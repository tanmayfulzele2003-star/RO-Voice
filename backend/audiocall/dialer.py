"""Campaign dialer: places many outbound calls at once, within limits.

Runs as a background task in the FastAPI lifespan. Every tick it
  1. reconciles contacts whose call has ended (done, or retry later);
  2. for each running campaign, claims as many due contacts as there are
     free lines — min(campaign.max_concurrent − its live calls,
     MAX_CONCURRENT_CALLS − all live phone calls) — and dials them, spaced to
     respect Twilio's calls-per-second limit;
  3. marks campaigns with nothing left to dial as completed.

The calls themselves run in parallel without extra work: each Twilio media
stream is its own WebSocket, CallBridge and Gemini Live session.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from audiocall.core import config
from audiocall.services import calls_service, campaigns_service

logger = logging.getLogger(__name__)


async def tick() -> int:
    """One dialer pass. Returns the number of calls placed."""
    await campaigns_service.reconcile_dialing_contacts()

    placed = 0
    spacing = 1.0 / config.DIAL_CALLS_PER_SECOND if config.DIAL_CALLS_PER_SECOND > 0 else 0.0
    for campaign in await campaigns_service.running_campaigns():
        global_free = config.MAX_CONCURRENT_CALLS - await calls_service.count_active_phone_calls()
        if global_free <= 0:
            break
        contacts = await campaigns_service.claim_contacts(campaign, global_free)
        for contact in contacts:
            if placed:
                await asyncio.sleep(spacing)
            try:
                call = await calls_service.start_outbound_call(
                    contact.customer_id, profile_id=campaign.profile_id, campaign_id=campaign.id
                )
                await campaigns_service.attach_call(contact.id, call.id)
            except calls_service.TwilioCallFailed as exc:
                # The failed call row is linked; reconcile decides on a retry.
                await campaigns_service.attach_call(contact.id, exc.call_id, failed=True)
            except calls_service.CustomerNotFound:
                await campaigns_service.attach_call(contact.id, None, failed=True)
            placed += 1

    await campaigns_service.complete_finished_campaigns()
    return placed


async def run_forever() -> None:
    logger.info(
        "Campaign dialer started (every %.1fs, max %d concurrent calls, %.1f calls/s)",
        config.DIALER_INTERVAL_SECONDS,
        config.MAX_CONCURRENT_CALLS,
        config.DIAL_CALLS_PER_SECOND,
    )
    while True:
        try:
            placed = await tick()
            if placed:
                logger.info("Dialer placed %d call(s)", placed)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed pass (DB hiccup, etc.) must never kill the dialer.
            logger.exception("Dialer tick failed")
        await asyncio.sleep(config.DIALER_INTERVAL_SECONDS)


def start() -> asyncio.Task | None:
    if not config.DIALER_ENABLED:
        logger.info("Campaign dialer disabled (DIALER_ENABLED=false)")
        return None
    return asyncio.create_task(run_forever(), name="campaign-dialer")


async def stop(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
