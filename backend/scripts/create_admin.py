"""One-off CLI to create the (single) admin dashboard user.

Usage:
    python scripts/create_admin.py <username> <password>

There is no self-registration flow by design — a single admin user, created
out-of-band by whoever operates the deployment.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")  # allow running as `python scripts/create_admin.py` from backend/

from audiocall.services import auth_service  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <username> <password>", file=sys.stderr)
        raise SystemExit(1)

    username, password = sys.argv[1], sys.argv[2]
    existing = await auth_service.get_admin_by_username(username)
    if existing is not None:
        print(f"Admin user {username!r} already exists.", file=sys.stderr)
        raise SystemExit(1)

    admin = await auth_service.create_admin_user(username, password)
    print(f"Created admin user {admin.username!r} ({admin.id}).")


if __name__ == "__main__":
    asyncio.run(main())
