"""Append-only log of notable call events (`call_events`).

Event types written by the app:
    call_initiated, call_status, provider_error, invalid_number, stream_started,
    stream_ended, customer_silence, silence_timeout, interruption,
    speech_not_recognized, ai_error, field_collected, agent_end_call,
    analysis_failed
"""

from __future__ import annotations

import logging
import uuid

from audiocall.db.models import CallEvent
from audiocall.db.session import get_session_factory

logger = logging.getLogger(__name__)


async def record(call_id: uuid.UUID, event_type: str, detail: str | None = None) -> None:
    """Never raises — event logging must not break call handling."""
    try:
        async with get_session_factory()() as session:
            session.add(CallEvent(call_id=call_id, event_type=event_type, detail=detail))
            await session.commit()
    except Exception:
        logger.exception("Failed to record call event %s for call %s", event_type, call_id)
