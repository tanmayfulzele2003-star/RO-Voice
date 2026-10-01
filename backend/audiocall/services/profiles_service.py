"""DB-backed CRUD for `business_profiles`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update

from audiocall.db.models import BusinessProfile, Call, Customer
from audiocall.db.session import get_session_factory
from audiocall.profiles import DEFAULT_RO_PROFILE


class ProfileInUse(Exception):
    pass


async def list_profiles() -> list[BusinessProfile]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(BusinessProfile).order_by(
                BusinessProfile.is_default.desc(), BusinessProfile.created_at
            )
        )
        return list(result.scalars().all())


async def get_profile(profile_id: uuid.UUID) -> BusinessProfile | None:
    async with get_session_factory()() as session:
        return await session.get(BusinessProfile, profile_id)


async def get_default_profile() -> BusinessProfile:
    """The default profile; re-created from the built-in RO template if an
    admin somehow removed every profile."""
    async with get_session_factory()() as session:
        profile = await session.scalar(
            select(BusinessProfile).where(BusinessProfile.is_default.is_(True))
        )
        if profile is None:
            profile = await session.scalar(
                select(BusinessProfile).order_by(BusinessProfile.created_at).limit(1)
            )
        if profile is None:
            profile = BusinessProfile(is_default=True, **DEFAULT_RO_PROFILE)
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
        return profile


async def resolve_profile(profile_id: uuid.UUID | None) -> BusinessProfile:
    """The given profile, or the default when unset/deleted."""
    if profile_id is not None:
        profile = await get_profile(profile_id)
        if profile is not None:
            return profile
    return await get_default_profile()


async def _clear_other_defaults(session, keep_id: uuid.UUID) -> None:  # noqa: ANN001
    await session.execute(
        update(BusinessProfile)
        .where(BusinessProfile.id != keep_id, BusinessProfile.is_default.is_(True))
        .values(is_default=False)
    )


async def create_profile(data: dict[str, Any]) -> BusinessProfile:
    async with get_session_factory()() as session:
        profile = BusinessProfile(**data)
        session.add(profile)
        await session.flush()
        if profile.is_default:
            await _clear_other_defaults(session, profile.id)
            await session.flush()
        await session.commit()
        await session.refresh(profile)
        return profile


async def update_profile(profile_id: uuid.UUID, data: dict[str, Any]) -> BusinessProfile | None:
    async with get_session_factory()() as session:
        profile = await session.get(BusinessProfile, profile_id)
        if profile is None:
            return None
        if data.get("is_default"):
            await _clear_other_defaults(session, profile_id)
            await session.flush()
        for key, value in data.items():
            setattr(profile, key, value)
        await session.commit()
        await session.refresh(profile)
        return profile


async def delete_profile(profile_id: uuid.UUID) -> bool:
    """Deletes a profile. The default profile, or one still assigned to
    customers, can't be deleted (calls keep working: their profile_id is set
    NULL and they render with the default)."""
    async with get_session_factory()() as session:
        profile = await session.get(BusinessProfile, profile_id)
        if profile is None:
            return False
        if profile.is_default:
            raise ProfileInUse("The default profile can't be deleted — make another profile the default first.")
        customers = await session.scalar(
            select(func.count()).select_from(Customer).where(Customer.profile_id == profile_id)
        )
        if customers:
            raise ProfileInUse(
                f"{customers} customer(s) still use this profile — move them to another profile first."
            )
        await session.execute(
            update(Call).where(Call.profile_id == profile_id).values(profile_id=None)
        )
        await session.delete(profile)
        await session.commit()
        return True
