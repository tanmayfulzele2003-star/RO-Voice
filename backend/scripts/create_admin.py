"""CLI to create a dashboard account.

Usage:
    python scripts/create_admin.py <username> <password> [company name]

On a fresh install this creates the first company and its owner, who is also
the platform admin (the same as the /setup page). Afterwards it adds another
owner to the platform admin's company. Teammates and customer companies are
normally added from the dashboard with invite links instead.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")  # allow running as `python scripts/create_admin.py` from backend/

from audiocall.core.security import hash_password  # noqa: E402
from audiocall.db.models import AdminUser  # noqa: E402
from audiocall.db.session import get_session_factory  # noqa: E402
from audiocall.services import auth_service, team_service  # noqa: E402


async def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(f"Usage: python {sys.argv[0]} <username> <password> [company name]", file=sys.stderr)
        raise SystemExit(1)

    username, password = sys.argv[1], sys.argv[2]
    company = sys.argv[3] if len(sys.argv) == 4 else "My company"
    if await auth_service.get_admin_by_username(username) is not None:
        print(f"User {username!r} already exists.", file=sys.stderr)
        raise SystemExit(1)

    if await team_service.user_count() == 0:
        user = await team_service.create_first_admin(username, password, company)
        print(f"Created {user.username!r}: owner of {company!r} and platform admin.")
        return

    org_id = await team_service.platform_org_id()
    async with get_session_factory()() as session:
        session.add(
            AdminUser(username=username, password_hash=hash_password(password), org_id=org_id, role="owner")
        )
        await session.commit()
    print(f"Created owner {username!r} in the platform admin's company.")


if __name__ == "__main__":
    asyncio.run(main())
