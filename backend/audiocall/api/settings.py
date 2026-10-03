"""Settings saved from the dashboard.

* `/api/settings` — the signed-in company's own Twilio account and default
  caller number (admins and owners). Without its own account a company uses
  the platform's.
* `/api/platform/settings` — platform-wide: Gemini key, public URL and the
  fallback Twilio account (platform admin only).

Saved values override the environment and apply without a restart; the test
endpoints check each one against the real service.
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from twilio.base.exceptions import TwilioRestException

from audiocall.api.auth import require_platform_admin, require_role
from audiocall.core import config
from audiocall.core.security import deployment_id
from audiocall.phone import is_valid_e164, normalize_phone
from audiocall.services import numbers_service, settings_service
from audiocall.services.settings_service import TwilioAccount
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/settings", tags=["settings"])
platform_router = APIRouter(prefix="/api/platform/settings", tags=["platform"])

_GEMINI_TEST_MODEL = "gemini-2.5-flash"


def _check_sid(v: str | None) -> str | None:
    if v and not re.fullmatch(r"AC[0-9a-fA-F]{32}", v.strip()):
        raise ValueError("Account SID starts with AC followed by 32 characters")
    return v


def _check_phone(v: str | None) -> str | None:
    if not v or not v.strip():
        return v
    phone = normalize_phone(v)
    if not is_valid_e164(phone):
        raise ValueError("Use international format, e.g. +14155550100")
    return phone


class OrgSettingsUpdate(BaseModel):
    """Only the keys sent are changed. An empty string removes the saved value."""

    twilio_account_sid: str | None = Field(default=None, max_length=64)
    twilio_auth_token: str | None = Field(default=None, max_length=128)
    twilio_phone_number: str | None = Field(default=None, max_length=32)

    _sid = field_validator("twilio_account_sid")(_check_sid)
    _phone = field_validator("twilio_phone_number")(_check_phone)


class PlatformSettingsUpdate(OrgSettingsUpdate):
    google_api_key: str | None = Field(default=None, max_length=256)
    public_url: str | None = Field(default=None, max_length=300)

    @field_validator("public_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return v
        v = v.strip().rstrip("/")
        if not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", v):
            raise ValueError("Use the scheme and host only, e.g. https://calls.example.com")
        return v


class TestResult(BaseModel):
    ok: bool
    message: str
    details: dict | None = None


async def _test_twilio(account: TwilioAccount, org_id) -> TestResult:  # noqa: ANN001
    """Check the credentials and list the account's numbers, so the wizard
    can offer to import them."""
    if not account.configured:
        return TestResult(ok=False, message="Enter the Account SID and Auth Token first.")

    def _check() -> tuple:
        twilio_account = account.client.api.accounts(account.account_sid).fetch()
        numbers = account.client.incoming_phone_numbers.list(limit=100)
        return twilio_account, numbers

    try:
        twilio_account, numbers = await asyncio.to_thread(_check)
    except TwilioRestException as exc:
        return TestResult(ok=False, message=f"Twilio rejected these credentials: {exc.msg}")
    except Exception as exc:  # network, proxy, DNS
        return TestResult(ok=False, message=f"Couldn't reach Twilio from this server: {exc}")
    registered = {n.number for n in await numbers_service.list_numbers(org_id)} if org_id else set()
    return TestResult(
        ok=True,
        message=f"Connected to {twilio_account.friendly_name} ({twilio_account.type} account).",
        details={
            "account_type": twilio_account.type,
            "numbers": [
                {
                    "number": n.phone_number,
                    "friendly_name": n.friendly_name,
                    "registered": n.phone_number in registered,
                }
                for n in numbers
            ],
        },
    )


# ── The company's own settings ───────────────────────────────────────────────
@router.get("")
async def get_org_settings(user: UserContext = Depends(require_role("admin"))) -> dict:
    return await settings_service.org_view(user.org_id)


@router.patch("")
async def update_org_settings(
    payload: OrgSettingsUpdate, user: UserContext = Depends(require_role("admin"))
) -> dict:
    await settings_service.save_org(user.org_id, payload.model_dump(exclude_unset=True))
    return await settings_service.org_view(user.org_id)


@router.post("/test-twilio", response_model=TestResult)
async def test_org_twilio(user: UserContext = Depends(require_role("admin"))) -> TestResult:
    return await _test_twilio(await settings_service.twilio_for(user.org_id), user.org_id)


# ── Platform-wide settings ───────────────────────────────────────────────────
@platform_router.get("", dependencies=[Depends(require_platform_admin)])
async def get_platform_settings() -> dict:
    return settings_service.public_view()


@platform_router.patch("", dependencies=[Depends(require_platform_admin)])
async def update_platform_settings(payload: PlatformSettingsUpdate) -> dict:
    await settings_service.save(payload.model_dump(exclude_unset=True))
    return settings_service.public_view()


@platform_router.post("/test-twilio", response_model=TestResult)
async def test_platform_twilio(user: UserContext = Depends(require_platform_admin)) -> TestResult:
    return await _test_twilio(await settings_service.twilio_for(None), user.org_id)


@platform_router.post(
    "/test-gemini", response_model=TestResult, dependencies=[Depends(require_platform_admin)]
)
async def test_gemini() -> TestResult:
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
    if not (os.environ.get("GOOGLE_API_KEY") or vertex):
        return TestResult(ok=False, message="Enter a Gemini API key first.")
    from google import genai

    try:
        await genai.Client().aio.models.get(model=_GEMINI_TEST_MODEL)
    except Exception as exc:
        return TestResult(ok=False, message=f"Gemini rejected the key: {exc}")
    return TestResult(ok=True, message="Gemini API key works.")


@platform_router.post(
    "/test-public-url", response_model=TestResult, dependencies=[Depends(require_platform_admin)]
)
async def test_public_url() -> TestResult:
    """Fetch {public_url}/health the way Twilio would, and check it reached
    this deployment."""
    if config.is_local_host():
        return TestResult(
            ok=False,
            message=f"{config.public_url()} is only reachable from this machine. Use your "
            "domain, or a tunnel such as ngrok, so Twilio can reach the server.",
        )
    url = f"{config.public_url()}/health"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(url)
        data = response.json() if response.status_code == 200 else {}
    except Exception as exc:
        return TestResult(ok=False, message=f"Couldn't reach {url}: {exc}")
    if data.get("deployment") != deployment_id():
        return TestResult(
            ok=False,
            message=f"{url} answered, but it isn't this server (HTTP {response.status_code}).",
        )
    return TestResult(ok=True, message=f"Twilio will be able to reach {config.public_url()}.")
