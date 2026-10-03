"""Settings saved from the dashboard, mounted under /api/settings.

Twilio credentials, the default caller number, the Gemini key and the public
URL. Saved values override the environment and apply without a restart; the
test endpoints check each one against the real service.
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from twilio.base.exceptions import TwilioRestException

from audiocall.api.auth import require_admin
from audiocall.core import config
from audiocall.core.security import deployment_id
from audiocall.phone import is_valid_e164, normalize_phone
from audiocall.services import numbers_service, settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])

_GEMINI_TEST_MODEL = "gemini-2.5-flash"


class SettingsUpdate(BaseModel):
    """Only the keys sent are changed. An empty string removes the saved value
    (the environment's applies again)."""

    twilio_account_sid: str | None = Field(default=None, max_length=64)
    twilio_auth_token: str | None = Field(default=None, max_length=128)
    twilio_phone_number: str | None = Field(default=None, max_length=32)
    google_api_key: str | None = Field(default=None, max_length=256)
    public_url: str | None = Field(default=None, max_length=300)

    @field_validator("twilio_account_sid")
    @classmethod
    def _sid(cls, v: str | None) -> str | None:
        if v and not re.fullmatch(r"AC[0-9a-fA-F]{32}", v.strip()):
            raise ValueError("Account SID starts with AC followed by 32 characters")
        return v

    @field_validator("twilio_phone_number")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return v
        phone = normalize_phone(v)
        if not is_valid_e164(phone):
            raise ValueError("Use international format, e.g. +14155550100")
        return phone

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


@router.get("")
async def get_settings() -> dict:
    return settings_service.public_view()


@router.patch("")
async def update_settings(payload: SettingsUpdate) -> dict:
    await settings_service.save(payload.model_dump(exclude_unset=True))
    return settings_service.public_view()


@router.post("/test-twilio", response_model=TestResult)
async def test_twilio() -> TestResult:
    """Check the credentials and list the account's numbers, so the wizard
    can offer to import them."""
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        return TestResult(ok=False, message="Enter the Account SID and Auth Token first.")
    client = config.twilio_client

    def _check() -> tuple:
        account = client.api.accounts(config.TWILIO_ACCOUNT_SID).fetch()
        numbers = client.incoming_phone_numbers.list(limit=100)
        return account, numbers

    try:
        account, numbers = await asyncio.to_thread(_check)
    except TwilioRestException as exc:
        return TestResult(ok=False, message=f"Twilio rejected these credentials: {exc.msg}")
    except Exception as exc:  # network, proxy, DNS
        return TestResult(ok=False, message=f"Couldn't reach Twilio from this server: {exc}")
    registered = {n.number for n in await numbers_service.list_numbers()}
    return TestResult(
        ok=True,
        message=f"Connected to {account.friendly_name} ({account.type} account).",
        details={
            "account_type": account.type,
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


@router.post("/test-gemini", response_model=TestResult)
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


@router.post("/test-public-url", response_model=TestResult)
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
