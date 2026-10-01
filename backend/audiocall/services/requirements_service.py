"""Live write-through of fields the agent collects during a call.

The agent's `save_customer_info` tool lands here, so `requirements.fields`
fills in while the call is still going. Post-call analysis later re-extracts
everything from the full transcript and fills any gaps.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from audiocall.db.models import Requirement
from audiocall.db.session import get_session_factory
from audiocall.profiles import FIXED_REQUIREMENT_COLUMNS


async def get_collected(call_id: uuid.UUID) -> dict[str, str]:
    async with get_session_factory()() as session:
        requirement = await session.scalar(
            select(Requirement).where(Requirement.call_id == call_id)
        )
        return dict(requirement.fields or {}) if requirement else {}


def apply_fields(requirement: Requirement, fields: dict[str, str | None]) -> None:
    """Merge `fields` into a Requirement row (JSONB + matching fixed columns).
    None values never overwrite something already collected."""
    merged = dict(requirement.fields or {})
    for key, value in fields.items():
        if value is None or not str(value).strip():
            continue
        merged[key] = str(value).strip()
        if key in FIXED_REQUIREMENT_COLUMNS:
            setattr(requirement, key, merged[key])
    # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
    requirement.fields = merged


async def save_fields(call_id: uuid.UUID, fields: dict[str, str | None]) -> dict[str, str]:
    """Upsert and return the full collected set."""
    async with get_session_factory()() as session:
        requirement = await session.scalar(
            select(Requirement).where(Requirement.call_id == call_id)
        )
        if requirement is None:
            requirement = Requirement(call_id=call_id, fields={})
            session.add(requirement)
        apply_fields(requirement, fields)
        await session.commit()
        return dict(requirement.fields or {})
