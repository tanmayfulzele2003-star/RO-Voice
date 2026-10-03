"""Account lookups for login. Creating users lives in team_service (first
admin, invites)."""

from __future__ import annotations

from sqlalchemy import select

from audiocall.db.models import AdminUser
from audiocall.db.session import get_session_factory


async def get_admin_by_username(username: str) -> AdminUser | None:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        return result.scalar_one_or_none()
