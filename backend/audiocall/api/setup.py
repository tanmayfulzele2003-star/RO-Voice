"""First-run setup, mounted under /api/setup.

* `GET /status` (public): whether the first admin still has to be created.
* `POST /admin` (public, one time): create the first admin with the setup
  token printed in the server log — replaces running scripts/create_admin.py.
* `GET /checklist` (admin): what's left before the first real call.
* `POST /complete` (admin): hide the setup banner.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from audiocall.api.auth import require_admin, set_session_cookie
from audiocall.core import config
from audiocall.core.security import hash_password, setup_token
from audiocall.db.models import AdminUser, BusinessProfile, Call, PhoneNumber
from audiocall.db.session import get_session_factory
from audiocall.services import settings_service

router = APIRouter(prefix="/api/setup", tags=["setup"])

SETUP_DONE_FLAG = "setup_completed"


class SetupStatus(BaseModel):
    needs_admin: bool


class FirstAdminRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)


class ChecklistItem(BaseModel):
    key: str
    label: str
    done: bool
    hint: str


class Checklist(BaseModel):
    items: list[ChecklistItem]
    complete: bool
    dismissed: bool


async def admin_count() -> int:
    async with get_session_factory()() as session:
        return await session.scalar(select(func.count()).select_from(AdminUser)) or 0


@router.get("/status", response_model=SetupStatus)
async def setup_status() -> SetupStatus:
    return SetupStatus(needs_admin=await admin_count() == 0)


@router.post("/admin", response_model=SetupStatus, status_code=201)
async def create_first_admin(payload: FirstAdminRequest, response: Response) -> SetupStatus:
    if not hmac.compare_digest(payload.token.strip(), setup_token()):
        raise HTTPException(status_code=403, detail="Setup link is invalid — copy it from the server log.")
    async with get_session_factory()() as session:
        # Serialise concurrent attempts: only the first one can see zero admins.
        await session.execute(text("LOCK TABLE admin_users IN SHARE ROW EXCLUSIVE MODE"))
        if await session.scalar(select(func.count()).select_from(AdminUser)):
            raise HTTPException(status_code=409, detail="An admin already exists — sign in instead.")
        session.add(AdminUser(username=payload.username, password_hash=hash_password(payload.password)))
        await session.commit()
    set_session_cookie(response, payload.username)
    return SetupStatus(needs_admin=False)


@router.get("/checklist", response_model=Checklist, dependencies=[Depends(require_admin)])
async def checklist() -> Checklist:
    view = settings_service.public_view()
    async with get_session_factory()() as session:
        numbers = await session.scalar(
            select(func.count())
            .select_from(PhoneNumber)
            .where(PhoneNumber.is_active.is_(True), PhoneNumber.outbound_enabled.is_(True))
        )
        profiles = await session.scalar(select(func.count()).select_from(BusinessProfile))
        talked = await session.scalar(
            select(func.count()).select_from(Call).where(Call.start_time.is_not(None))
        )
    flags = await settings_service.get_flags()
    items = [
        ChecklistItem(
            key="twilio",
            label="Connect Twilio",
            done=view["twilio_account_sid"]["is_set"] and view["twilio_auth_token"]["is_set"],
            hint="Account SID and Auth Token from console.twilio.com",
        ),
        ChecklistItem(
            key="number",
            label="Add a phone number",
            done=bool(numbers) or view["twilio_phone_number"]["is_set"],
            hint="A Twilio number the agent calls from and answers on",
        ),
        ChecklistItem(
            key="gemini",
            label="Connect Gemini",
            done=view["google_api_key"]["is_set"],
            hint="An API key from aistudio.google.com",
        ),
        ChecklistItem(
            key="public_url",
            label="Set the public URL",
            done=not config.is_local_host(),
            hint="Where Twilio reaches this server, e.g. https://calls.example.com",
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
    return Checklist(
        items=items,
        complete=all(i.done for i in items),
        dismissed=flags.get(SETUP_DONE_FLAG) == "true",
    )


class FlagUpdate(BaseModel):
    key: str = Field(pattern=r"^(setup_profile|setup_completed)$")
    value: bool


@router.post("/flags", status_code=204, dependencies=[Depends(require_admin)])
async def set_flag(payload: FlagUpdate) -> Response:
    await settings_service.set_flag(payload.key, "true" if payload.value else "false")
    return Response(status_code=204)
