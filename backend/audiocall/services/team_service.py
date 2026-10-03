"""Organizations, their users and roles, and invite links.

Roles, lowest to highest: viewer (read only), member (customers, calls,
campaigns), admin (also profiles, numbers, settings, the team), owner
(everything, including other admins and owners). Separately, a platform admin
runs the platform itself: creates companies and sets platform-wide settings.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from audiocall.core.security import hash_password
from audiocall.db.models import (
    ROLES,
    AdminUser,
    Call,
    Invite,
    Organization,
)
from audiocall.db.session import get_session_factory

INVITE_TTL = timedelta(days=7)


class TeamError(Exception):
    """A request that breaks a team rule (shown to the user as-is)."""


class NotFound(Exception):
    pass


def role_rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else -1


def can_manage(actor_role: str, target_role: str) -> bool:
    """Admins manage viewers, members and admins; only owners manage owners."""
    if actor_role == "owner":
        return True
    return actor_role == "admin" and target_role != "owner"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class UserContext:
    """The signed-in user, resolved once per request."""

    id: uuid.UUID
    username: str
    org_id: uuid.UUID
    org_name: str
    role: str
    is_platform_admin: bool

    def at_least(self, role: str) -> bool:
        return role_rank(self.role) >= role_rank(role)


async def get_user_context(username: str) -> UserContext | None:
    """None when the user doesn't exist, is deactivated, or their company is."""
    async with get_session_factory()() as session:
        user = await session.scalar(
            select(AdminUser)
            .where(AdminUser.username == username)
            .options(selectinload(AdminUser.organization))
        )
    if user is None or not user.is_active or not user.organization.is_active:
        return None
    return UserContext(
        id=user.id,
        username=user.username,
        org_id=user.org_id,
        org_name=user.organization.name,
        role=user.role,
        is_platform_admin=user.is_platform_admin,
    )


# ── First run ────────────────────────────────────────────────────────────────
async def user_count() -> int:
    async with get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(AdminUser)) or 0


async def create_first_admin(username: str, password: str, company_name: str) -> AdminUser:
    """The installer's own account: owner of the first company and platform
    admin. Reuses the company an upgrade created for existing data. Raises
    TeamError if any user exists already (checked under a table lock, so only
    one concurrent attempt can win)."""
    async with get_session_factory()() as session:
        await session.execute(text("LOCK TABLE admin_users IN SHARE ROW EXCLUSIVE MODE"))
        if await session.scalar(select(func.count()).select_from(AdminUser)):
            raise TeamError("An admin already exists — sign in instead.")
        org = await session.scalar(select(Organization).order_by(Organization.created_at).limit(1))
        if org is None:
            org = Organization(name=company_name)
            session.add(org)
            await session.flush()
        else:
            org.name = company_name
        user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            org_id=org.id,
            role="owner",
            is_platform_admin=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def platform_org_id() -> uuid.UUID | None:
    """The platform operator's own company: where calls to numbers nobody
    registered land. The oldest company with a platform admin."""
    async with get_session_factory()() as session:
        org_id = await session.scalar(
            select(AdminUser.org_id)
            .where(AdminUser.is_platform_admin.is_(True))
            .order_by(AdminUser.created_at)
            .limit(1)
        )
        if org_id is None:
            org_id = await session.scalar(
                select(Organization.id).order_by(Organization.created_at).limit(1)
            )
        return org_id


# ── Organization ─────────────────────────────────────────────────────────────
async def get_org(org_id: uuid.UUID) -> Organization | None:
    async with get_session_factory()() as session:
        return await session.get(Organization, org_id)


async def update_org(org_id: uuid.UUID, data: dict) -> Organization:
    async with get_session_factory()() as session:
        org = await session.get(Organization, org_id)
        if org is None:
            raise NotFound("Organization not found")
        for key, value in data.items():
            setattr(org, key, value)
        await session.commit()
        await session.refresh(org)
        return org


async def list_orgs() -> list[tuple[Organization, int, int]]:
    """Every company with its user and call counts (platform admin view)."""
    users = (
        select(func.count()).select_from(AdminUser).where(AdminUser.org_id == Organization.id)
    ).scalar_subquery()
    calls = select(func.count()).select_from(Call).where(Call.org_id == Organization.id).scalar_subquery()
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(Organization, users, calls).order_by(Organization.created_at)
        )
        return [(org, n_users or 0, n_calls or 0) for org, n_users, n_calls in rows.all()]


async def create_org(name: str, max_concurrent_calls: int | None = None) -> Organization:
    async with get_session_factory()() as session:
        org = Organization(name=name, max_concurrent_calls=max_concurrent_calls)
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return org


# ── Users ────────────────────────────────────────────────────────────────────
async def list_users(org_id: uuid.UUID) -> list[AdminUser]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.org_id == org_id).order_by(AdminUser.created_at)
        )
        return list(result.scalars().all())


async def _owner_count(session, org_id: uuid.UUID) -> int:  # noqa: ANN001
    return (
        await session.scalar(
            select(func.count())
            .select_from(AdminUser)
            .where(
                AdminUser.org_id == org_id,
                AdminUser.role == "owner",
                AdminUser.is_active.is_(True),
            )
        )
        or 0
    )


async def update_user(actor: UserContext, user_id: uuid.UUID, data: dict) -> AdminUser:
    """Change a teammate's role or deactivate them, within the actor's rights.
    A company always keeps at least one active owner."""
    async with get_session_factory()() as session:
        user = await session.get(AdminUser, user_id, with_for_update=True)
        if user is None or user.org_id != actor.org_id:
            raise NotFound("User not found")
        new_role = data.get("role", user.role)
        if not (can_manage(actor.role, user.role) and can_manage(actor.role, new_role)):
            raise TeamError("Only an owner can change an owner, or make someone an owner.")
        losing_owner = user.role == "owner" and user.is_active and (
            new_role != "owner" or data.get("is_active") is False
        )
        if losing_owner and await _owner_count(session, actor.org_id) <= 1:
            raise TeamError("A company needs at least one owner. Make someone else an owner first.")
        for key, value in data.items():
            setattr(user, key, value)
        await session.commit()
        await session.refresh(user)
        return user


async def delete_user(actor: UserContext, user_id: uuid.UUID) -> None:
    if user_id == actor.id:
        raise TeamError("You can't remove yourself.")
    async with get_session_factory()() as session:
        user = await session.get(AdminUser, user_id, with_for_update=True)
        if user is None or user.org_id != actor.org_id:
            raise NotFound("User not found")
        if not can_manage(actor.role, user.role):
            raise TeamError("Only an owner can remove an owner.")
        if user.role == "owner" and await _owner_count(session, actor.org_id) <= 1:
            raise TeamError("A company needs at least one owner.")
        await session.delete(user)
        await session.commit()


async def change_password(user_id: uuid.UUID, new_password: str) -> None:
    async with get_session_factory()() as session:
        user = await session.get(AdminUser, user_id)
        if user is None:
            raise NotFound("User not found")
        user.password_hash = hash_password(new_password)
        await session.commit()


# ── Invites ──────────────────────────────────────────────────────────────────
async def create_invite(
    org_id: uuid.UUID, role: str, note: str | None, created_by: uuid.UUID | None
) -> tuple[Invite, str]:
    """A single-use invite. Returns the row and the raw token (only a hash is
    stored, so the link can be shown exactly once)."""
    if role not in ROLES:
        raise TeamError(f"Unknown role {role!r}")
    token = secrets.token_urlsafe(24)
    async with get_session_factory()() as session:
        invite = Invite(
            org_id=org_id,
            role=role,
            token_hash=_hash_token(token),
            note=note,
            created_by=created_by,
            expires_at=datetime.now(timezone.utc) + INVITE_TTL,
        )
        session.add(invite)
        await session.commit()
        await session.refresh(invite)
        return invite, token


async def list_invites(org_id: uuid.UUID) -> list[Invite]:
    """Open (not accepted, not expired) invites."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Invite)
            .where(
                Invite.org_id == org_id,
                Invite.accepted_at.is_(None),
                Invite.expires_at > datetime.now(timezone.utc),
            )
            .order_by(Invite.created_at.desc())
        )
        return list(result.scalars().all())


async def revoke_invite(org_id: uuid.UUID, invite_id: uuid.UUID) -> None:
    async with get_session_factory()() as session:
        invite = await session.get(Invite, invite_id)
        if invite is None or invite.org_id != org_id:
            raise NotFound("Invite not found")
        await session.delete(invite)
        await session.commit()


async def describe_invite(token: str) -> tuple[Invite, Organization] | None:
    """The open invite behind a token, for the join page."""
    async with get_session_factory()() as session:
        invite = await session.scalar(select(Invite).where(Invite.token_hash == _hash_token(token)))
        if (
            invite is None
            or invite.accepted_at is not None
            or invite.expires_at <= datetime.now(timezone.utc)
        ):
            return None
        org = await session.get(Organization, invite.org_id)
        if org is None or not org.is_active:
            return None
        return invite, org


async def accept_invite(token: str, username: str, password: str) -> AdminUser:
    """Create the account an invite is for. The invite row is locked, so a
    link can't be used twice even by simultaneous requests."""
    async with get_session_factory()() as session:
        invite = await session.scalar(
            select(Invite).where(Invite.token_hash == _hash_token(token)).with_for_update()
        )
        if (
            invite is None
            or invite.accepted_at is not None
            or invite.expires_at <= datetime.now(timezone.utc)
        ):
            raise TeamError("This invite link is invalid, used or expired. Ask for a new one.")
        if await session.scalar(select(AdminUser.id).where(AdminUser.username == username)):
            raise TeamError("That username is taken — pick another.")
        user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            org_id=invite.org_id,
            role=invite.role,
        )
        session.add(user)
        invite.accepted_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user)
        return user

