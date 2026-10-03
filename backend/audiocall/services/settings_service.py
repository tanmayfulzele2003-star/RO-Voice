"""Settings saved from the dashboard, applied to the running server.

Two scopes:

* **platform** — set by the platform admin: the Gemini key, the public URL,
  and a fallback Twilio account for companies that don't bring their own.
  Applying them updates `audiocall.core.config` in place, rebuilds the
  fallback Twilio client and points the Gemini clients at the new key — no
  restart.
* **organization** — each company's own Twilio account and default caller
  number (`twilio_for(org_id)`), plus its setup-progress flags.

Saved values override the environment (which stays the fallback), and secrets
are encrypted at rest (core/secrets_box.py). Every process loads platform
settings at startup and refreshes them every REFRESH_SECONDS; a company's
Twilio account is cached for the same time, so a change saved through one
server process reaches the others within that window.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from twilio.rest import Client as TwilioClient

from audiocall.core import config, secrets_box
from audiocall.db.models import AppSetting
from audiocall.db.session import get_session_factory

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 30
PLATFORM = "platform"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    secret: bool = False


_TWILIO_SPECS = (
    SettingSpec("twilio_account_sid", "Twilio Account SID"),
    SettingSpec("twilio_auth_token", "Twilio Auth Token", secret=True),
    SettingSpec("twilio_phone_number", "Default caller number"),
)
PLATFORM_SPECS: dict[str, SettingSpec] = {
    s.key: s
    for s in (
        *_TWILIO_SPECS,
        SettingSpec("google_api_key", "Gemini API key", secret=True),
        SettingSpec("public_url", "Public URL"),
    )
}
ORG_SPECS: dict[str, SettingSpec] = {s.key: s for s in _TWILIO_SPECS}
# Keys allowed as per-organization flags (setup progress).
ORG_FLAGS = ("setup_profile", "setup_completed")

# What was last applied for the platform, so a refresh only rebuilds clients
# when something actually changed.
_applied: dict[str, str] = {}
# Platform keys whose current value came from the dashboard, not the environment.
_from_dashboard: set[str] = set()


def _scope(org_id: uuid.UUID | None) -> str:
    return PLATFORM if org_id is None else str(org_id)


# ── Reading and writing ──────────────────────────────────────────────────────
async def _read(scope: str, specs: dict[str, SettingSpec]) -> dict[str, str]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(AppSetting).where(AppSetting.scope == scope, AppSetting.key.in_(list(specs)))
            )
        ).scalars().all()
    saved: dict[str, str] = {}
    for row in rows:
        if row.is_secret:
            try:
                saved[row.key] = secrets_box.decrypt(row.value)
            except secrets_box.SecretUnreadable:
                logger.warning(
                    "Setting %s (%s) can't be decrypted (SESSION_SECRET / "
                    "SETTINGS_ENCRYPTION_KEY changed?) — ignoring it; re-enter it in Settings.",
                    row.key,
                    scope,
                )
                continue
        else:
            saved[row.key] = row.value
    return saved


async def _write(scope: str, specs: dict[str, SettingSpec], updates: dict[str, str | None]) -> None:
    async with get_session_factory()() as session:
        for key, value in updates.items():
            spec = specs[key]
            value = (value or "").strip()
            if not value:
                await session.execute(
                    delete(AppSetting).where(AppSetting.scope == scope, AppSetting.key == key)
                )
                continue
            stored = secrets_box.encrypt(value) if spec.secret else value
            await session.execute(
                insert(AppSetting)
                .values(scope=scope, key=key, value=stored, is_secret=spec.secret)
                .on_conflict_do_update(
                    index_elements=[AppSetting.scope, AppSetting.key],
                    set_={"value": stored, "is_secret": spec.secret},
                )
            )
        await session.commit()


def mask(value: str) -> str:
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 8 else "•" * len(value)


def _view_item(spec: SettingSpec, value: str, source: str) -> dict:
    return {
        "label": spec.label,
        "secret": spec.secret,
        "value": mask(value) if spec.secret else value,
        "is_set": bool(value),
        "source": source if value else "unset",
    }


# ── Platform ─────────────────────────────────────────────────────────────────
def _effective(saved: dict[str, str]) -> dict[str, str]:
    return {key: saved.get(key) or config.ENV_DEFAULTS.get(key, "") for key in PLATFORM_SPECS}


def apply(values: dict[str, str]) -> None:
    """Put effective platform setting values into the running process."""
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
        _org_cache.clear()  # companies on the fallback account follow it

    if values["public_url"]:
        config.set_public_url(values["public_url"])

    if old.get("google_api_key") != values["google_api_key"]:
        if values["google_api_key"]:
            os.environ["GOOGLE_API_KEY"] = values["google_api_key"]
        else:
            os.environ.pop("GOOGLE_API_KEY", None)
        from audiocall.agent import reset_model_clients

        reset_model_clients()


async def load() -> None:
    """Read saved platform settings from the database and apply them."""
    global _from_dashboard
    saved = await _read(PLATFORM, PLATFORM_SPECS)
    _from_dashboard = {k for k, v in saved.items() if v}
    apply(_effective(saved))


async def save(updates: dict[str, str | None]) -> None:
    """Save platform settings. An empty value or None removes the saved value,
    so the environment's applies again."""
    await _write(PLATFORM, PLATFORM_SPECS, updates)
    await load()


def public_view() -> dict[str, dict]:
    """Current platform settings for the dashboard. Secrets are masked."""
    view = {}
    for key, spec in PLATFORM_SPECS.items():
        value = _applied.get(key, config.ENV_DEFAULTS.get(key, ""))
        view[key] = _view_item(spec, value, "dashboard" if key in _from_dashboard else "environment")
    return view


def platform_status() -> dict[str, bool]:
    """What every company depends on, for the setup checklist."""
    return {
        "gemini": bool(os.environ.get("GOOGLE_API_KEY"))
        or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"),
        "public_url": not config.is_local_host(),
    }


# ── Per-organization Twilio account ─────────────────────────────────────────
@dataclass(frozen=True)
class TwilioAccount:
    """The Twilio account a company's calls go through."""

    account_sid: str
    auth_token: str
    phone_number: str
    client: TwilioClient
    own: bool  # the company's own account, not the platform's fallback

    @property
    def configured(self) -> bool:
        return bool(self.account_sid and self.auth_token)


_org_cache: dict[str, tuple[float, TwilioAccount]] = {}


def _platform_account() -> TwilioAccount:
    return TwilioAccount(
        config.TWILIO_ACCOUNT_SID,
        config.TWILIO_AUTH_TOKEN,
        config.TWILIO_PHONE_NUMBER,
        config.twilio_client,
        own=False,
    )


async def twilio_for(org_id: uuid.UUID | None) -> TwilioAccount:
    """The company's own Twilio account if it saved one, else the platform's."""
    if org_id is None:
        return _platform_account()
    scope = _scope(org_id)
    cached = _org_cache.get(scope)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    saved = await _read(scope, ORG_SPECS)
    if saved.get("twilio_account_sid") and saved.get("twilio_auth_token"):
        account = TwilioAccount(
            saved["twilio_account_sid"],
            saved["twilio_auth_token"],
            saved.get("twilio_phone_number", ""),
            TwilioClient(saved["twilio_account_sid"], saved["twilio_auth_token"]),
            own=True,
        )
    else:
        platform = _platform_account()
        # A company on the shared account may still pick its own caller number.
        account = TwilioAccount(
            platform.account_sid,
            platform.auth_token,
            saved.get("twilio_phone_number") or platform.phone_number,
            platform.client,
            own=False,
        )
    _org_cache[scope] = (time.monotonic() + REFRESH_SECONDS, account)
    return account


async def save_org(org_id: uuid.UUID, updates: dict[str, str | None]) -> None:
    await _write(_scope(org_id), ORG_SPECS, updates)
    _org_cache.pop(_scope(org_id), None)


async def org_view(org_id: uuid.UUID) -> dict:
    """The company's Twilio settings for the dashboard. Secrets are masked."""
    saved = await _read(_scope(org_id), ORG_SPECS)
    account = await twilio_for(org_id)
    view = {
        key: _view_item(spec, saved.get(key, ""), "organization")
        for key, spec in ORG_SPECS.items()
    }
    return {
        "settings": view,
        "uses_platform_twilio": not account.own,
        "platform_twilio_available": _platform_account().configured,
    }


# ── Flags (setup progress) ───────────────────────────────────────────────────
async def get_flags(org_id: uuid.UUID) -> dict[str, str]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(AppSetting).where(
                    AppSetting.scope == _scope(org_id), AppSetting.key.in_(ORG_FLAGS)
                )
            )
        ).scalars()
        return {row.key: row.value for row in rows}


async def set_flag(org_id: uuid.UUID, key: str, value: str) -> None:
    if key not in ORG_FLAGS:
        raise ValueError(f"{key} is not a setup flag")
    async with get_session_factory()() as session:
        await session.execute(
            insert(AppSetting)
            .values(scope=_scope(org_id), key=key, value=value, is_secret=False)
            .on_conflict_do_update(
                index_elements=[AppSetting.scope, AppSetting.key], set_={"value": value}
            )
        )
        await session.commit()


# ── Background refresh ───────────────────────────────────────────────────────
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
