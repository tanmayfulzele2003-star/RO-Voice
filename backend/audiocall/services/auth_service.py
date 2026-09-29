"""DB-backed operations on `admin_users`."""

from __future__ import annotations

from sqlalchemy import select

from audiocall.core.security import hash_password
from audiocall.db.models import AdminUser
from audiocall.db.session import get_session_factory


async def get_admin_by_username(username: str) -> AdminUser | None:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        return result.scalar_one_or_none()


async def create_admin_user(username: str, password: str) -> AdminUser:
    async with get_session_factory()() as session:
        admin = AdminUser(username=username, password_hash=hash_password(password))
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin
