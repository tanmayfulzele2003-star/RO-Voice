"""First-run setup, mounted under /api/setup.

* `GET /status` (public): whether the first admin still has to be created.
* `POST /admin` (public, one time): create the installer's account and first
  company with the setup token printed in the server log.
* `GET /checklist`: what's left before the company's first real call.
* `POST /flags` (admin): record setup progress / hide the setup banner.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from audiocall.api.auth import require_role, require_user, set_session_cookie
from audiocall.core.security import setup_token
from audiocall.db.models import BusinessProfile, Call, PhoneNumber
from audiocall.db.session import get_session_factory
from audiocall.services import settings_service, team_service
from audiocall.services.team_service import UserContext

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatus(BaseModel):
    needs_admin: bool


class FirstAdminRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    company_name: str = Field(default="My company", min_length=1, max_length=200)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool
    hint: str
    # Platform-wide steps (Gemini, public URL) only the platform admin can do.
    platform: bool = False


class Checklist(BaseModel):
    items: list[ChecklistItem]
    complete: bool
    dismissed: bool


async def admin_count() -> int:
    return await team_service.user_count()


@router.get("/status", response_model=SetupStatus)
async def setup_status() -> SetupStatus:
    return SetupStatus(needs_admin=await admin_count() == 0)


@router.post("/admin", response_model=SetupStatus, status_code=201)
async def create_first_admin(payload: FirstAdminRequest, response: Response) -> SetupStatus:
    if not hmac.compare_digest(payload.token.strip(), setup_token()):
        raise HTTPException(status_code=403, detail="Setup link is invalid — copy it from the server log.")
    try:
        await team_service.create_first_admin(
            payload.username, payload.password, payload.company_name.strip()
        )
    except team_service.TeamError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    set_session_cookie(response, payload.username)
    return SetupStatus(needs_admin=False)


@router.get("/checklist", response_model=Checklist)
async def checklist(user: UserContext = Depends(require_user)) -> Checklist:
    account = await settings_service.twilio_for(user.org_id)
    platform = settings_service.platform_status()
    async with get_session_factory()() as session:
        numbers = await session.scalar(
            select(func.count())
            .select_from(PhoneNumber)
            .where(
                PhoneNumber.org_id == user.org_id,
                PhoneNumber.is_active.is_(True),
                PhoneNumber.outbound_enabled.is_(True),
            )
        )
        profiles = await session.scalar(
            select(func.count()).select_from(BusinessProfile).where(BusinessProfile.org_id == user.org_id)
        )
        talked = await session.scalar(
            select(func.count())
            .select_from(Call)
            .where(Call.org_id == user.org_id, Call.start_time.is_not(None))
        )
    flags = await settings_service.get_flags(user.org_id)
    items = [
        ChecklistItem(
            key="twilio",
            label="Connect Twilio",
            done=account.configured,
            hint="Account SID and Auth Token from console.twilio.com",
        ),
        ChecklistItem(
            key="number",
            label="Add a phone number",
            done=bool(numbers) or bool(account.phone_number),
            hint="A Twilio number the agent calls from and answers on",
        ),
        ChecklistItem(
            key="gemini",
            label="Connect Gemini",
            done=platform["gemini"],
            hint="An API key from aistudio.google.com",
            platform=True,
        ),
        ChecklistItem(
            key="public_url",
            label="Set the public URL",
            done=platform["public_url"],
            hint="Where Twilio reaches this server, e.g. https://calls.example.com",
            platform=True,
        ),
        ChecklistItem(
            key="profile",
            label="Set up your business",
            done=flags.get("setup_profile") == "true" or (profiles or 0) > 1,
            hint="Who the agent represents and what it asks",
        ),
        ChecklistItem(
            key="test_call",
            label="Make a test call",
            done=bool(talked),
            hint="Call your own phone, or try it in the browser",
        ),
    ]
    if not user.is_platform_admin:
        # A customer company can't change platform settings; once the
        # platform admin has done them they're simply not its concern.
        items = [i for i in items if not i.platform]
    return Checklist(
        items=items,
        complete=all(i.done for i in items),
        dismissed=flags.get("setup_completed") == "true",
    )


class FlagUpdate(BaseModel):
    key: str = Field(pattern=r"^(setup_profile|setup_completed)$")
    value: bool


@router.post("/flags", status_code=204)
async def set_flag(payload: FlagUpdate, user: UserContext = Depends(require_role("admin"))) -> Response:
    await settings_service.set_flag(user.org_id, payload.key, "true" if payload.value else "false")
    return Response(status_code=204)
