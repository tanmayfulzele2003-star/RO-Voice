"""Create the first admin from ADMIN_USERNAME / ADMIN_PASSWORD, if set and no
admin exists yet. Used by the Docker entrypoint for unattended installs; does
nothing otherwise (the server then logs a one-time /setup link instead).
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, ".")  # allow running as `python scripts/bootstrap_admin.py` from backend/

from audiocall.api.setup import admin_count  # noqa: E402
from audiocall.services import auth_service  # noqa: E402


async def main() -> None:
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not (username and password):
        return
    if await admin_count():
        return
    if len(password) < 8:
        print("ADMIN_PASSWORD must be at least 8 characters; skipping admin creation.", file=sys.stderr)
        return
    await auth_service.create_admin_user(username, password)
    print(f"Created admin user {username!r} from ADMIN_USERNAME.")


if __name__ == "__main__":
    asyncio.run(main())
