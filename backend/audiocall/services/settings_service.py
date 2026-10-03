"""Settings saved from the dashboard, applied to the running server.

A business setting up the product enters its Twilio credentials, caller
number, Gemini key and public URL in the setup wizard instead of editing
environment variables. Saved values override the environment (which stays the
fallback), secrets are encrypted at rest (core/secrets_box.py), and applying
them updates `audiocall.core.config` in place, rebuilds the Twilio client and
points the Gemini clients at the new key — no restart.

Every process loads settings at startup and refreshes them periodically, so a
change saved through one server process reaches the others within
REFRESH_SECONDS.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from twilio.rest import Client as TwilioClient

from audiocall.core import config, secrets_box
from audiocall.db.models import AppSetting
from audiocall.db.session import get_session_factory

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 30


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    secret: bool = False


SPECS: dict[str, SettingSpec] = {
    s.key: s
    for s in (
        SettingSpec("twilio_account_sid", "Twilio Account SID"),
        SettingSpec("twilio_auth_token", "Twilio Auth Token", secret=True),
        SettingSpec("twilio_phone_number", "Default caller number"),
        SettingSpec("google_api_key", "Gemini API key", secret=True),
        SettingSpec("public_url", "Public URL"),
    )
}

# What was last applied, so a refresh only rebuilds clients when something
# actually changed.
_applied: dict[str, str] = {}
# Keys whose current value came from the dashboard rather than the environment.
_from_dashboard: set[str] = set()


def _effective(saved: dict[str, str]) -> dict[str, str]:
    return {key: saved.get(key) or config.ENV_DEFAULTS.get(key, "") for key in SPECS}


def apply(values: dict[str, str]) -> None:
    """Put effective setting values into the running process."""
    global _applied
    if values == _applied:
        return
    old = _applied
    _applied = dict(values)

    config.TWILIO_ACCOUNT_SID = values["twilio_account_sid"]
    config.TWILIO_AUTH_TOKEN = values["twilio_auth_token"]
    config.TWILIO_PHONE_NUMBER = values["twilio_phone_number"]
    if (old.get("twilio_account_sid"), old.get("twilio_auth_token")) != (
        values["twilio_account_sid"],
        values["twilio_auth_token"],
    ):
        config.twilio_client = TwilioClient(values["twilio_account_sid"], values["twilio_auth_token"])

    if values["public_url"]:
        config.set_public_url(values["public_url"])

    if old.get("google_api_key") != values["google_api_key"]:
        if values["google_api_key"]:
            os.environ["GOOGLE_API_KEY"] = values["google_api_key"]
        else:
            os.environ.pop("GOOGLE_API_KEY", None)
        from audiocall.agent import reset_model_clients

        reset_model_clients()


async def _read_saved() -> dict[str, str]:
    async with get_session_factory()() as session:
        rows = (await session.execute(select(AppSetting))).scalars().all()
    saved: dict[str, str] = {}
    for row in rows:
        if row.key not in SPECS:
            continue
        if row.is_secret:
            try:
                saved[row.key] = secrets_box.decrypt(row.value)
            except secrets_box.SecretUnreadable:
                logger.warning(
                    "Setting %s can't be decrypted (SESSION_SECRET / SETTINGS_ENCRYPTION_KEY "
                    "changed?) — ignoring it; re-enter it in Settings.",
                    row.key,
                )
                continue
        else:
            saved[row.key] = row.value
    return saved


async def load() -> None:
    """Read saved settings from the database and apply them."""
    global _from_dashboard
    saved = await _read_saved()
    _from_dashboard = {k for k, v in saved.items() if v}
    apply(_effective(saved))


async def save(updates: dict[str, str | None]) -> None:
    """Save settings. An empty value or None removes the saved value, so the
    environment's applies again."""
    async with get_session_factory()() as session:
        for key, value in updates.items():
            spec = SPECS[key]
            value = (value or "").strip()
            if not value:
                await session.execute(delete(AppSetting).where(AppSetting.key == key))
                continue
            stored = secrets_box.encrypt(value) if spec.secret else value
            await session.execute(
                insert(AppSetting)
                .values(key=key, value=stored, is_secret=spec.secret)
                .on_conflict_do_update(
                    index_elements=[AppSetting.key],
                    set_={"value": stored, "is_secret": spec.secret},
                )
            )
        await session.commit()
    await load()


# Non-secret flags (setup progress) share the table; keys outside SPECS.
async def get_flags() -> dict[str, str]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(select(AppSetting).where(AppSetting.key.not_in(list(SPECS))))
        ).scalars()
        return {row.key: row.value for row in rows if not row.is_secret}


async def set_flag(key: str, value: str) -> None:
    if key in SPECS:
        raise ValueError(f"{key} is a setting, not a flag")
    async with get_session_factory()() as session:
        await session.execute(
            insert(AppSetting)
            .values(key=key, value=value, is_secret=False)
            .on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
        )
        await session.commit()


def mask(value: str) -> str:
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 8 else "•" * len(value)


def public_view() -> dict[str, dict]:
    """Current settings for the dashboard. Secrets are masked."""
    view = {}
    for key, spec in SPECS.items():
        value = _applied.get(key, config.ENV_DEFAULTS.get(key, ""))
        source = "dashboard" if key in _from_dashboard else ("environment" if value else "unset")
        view[key] = {
            "label": spec.label,
            "secret": spec.secret,
            "value": mask(value) if spec.secret else value,
            "is_set": bool(value),
            "source": source,
        }
    return view


async def refresh_forever() -> None:
    while True:
        await asyncio.sleep(REFRESH_SECONDS)
        try:
            await load()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Settings refresh failed")


def start_refresher() -> asyncio.Task:
    return asyncio.create_task(refresh_forever(), name="settings-refresh")


async def stop_refresher(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
