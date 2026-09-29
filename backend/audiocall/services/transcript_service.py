"""Append conversation turns to `conversation_messages`."""

from __future__ import annotations

import uuid
from datetime import datetime

from audiocall.db.models import ConversationMessage
from audiocall.db.session import get_session_factory


async def append_message(
    call_id: uuid.UUID, speaker: str, message: str, timestamp: datetime
) -> None:
    async with get_session_factory()() as session:
        session.add(
            ConversationMessage(
                call_id=call_id,
                speaker=speaker,
                message=message,
                timestamp=timestamp,
            )
        )
        await session.commit()
