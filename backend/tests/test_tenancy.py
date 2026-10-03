"""Multi-company isolation, roles, invites and platform administration,
through the real HTTP API against Postgres (RUN_DB_TESTS=1).

The core promise: a signed-in user only ever sees and changes their own
company's data. Every route is tried against another company's rows.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import update

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="needs RUN_DB_TESTS=1 and a migrated Postgres"
)

from audiocall.core.security import hash_password  # noqa: E402
from audiocall.db import session as db_session  # noqa: E402
from audiocall.db.models import AdminUser, Invite, Organization  # noqa: E402
from audiocall.profiles import DEFAULT_RO_PROFILE  # noqa: E402
from audiocall.services import (  # noqa: E402
    calls_service,
    campaigns_service,
    customers_service,
    numbers_service,
    profiles_service,
)
from tests.dbhelpers import delete_orgs, make_org  # noqa: E402

PASSWORD = "correct-horse-1"


@pytest.fixture
async def orgs():
    db_session.get_engine.cache_clear()
    a, b = await make_org("Company A"), await make_org("Company B")
    created = [a.id, b.id]
    yield a, b, created
    await delete_orgs(created)
    await db_session.get_engine().dispose()


async def add_user(org_id, role="owner", platform=False, active=True) -> str:
    username = f"t-{role}-{uuid.uuid4().hex[:8]}"
    async with db_session.get_session_factory()() as session:
        session.add(
            AdminUser(
                username=username,
                password_hash=hash_password(PASSWORD),
                org_id=org_id,
                role=role,
                is_platform_admin=platform,
                is_active=active,
            )
        )
        await session.commit()
    return username


async def signed_in(username: str) -> httpx.AsyncClient:
    from audiocall.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as login:
        res = await login.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert res.status_code == 200, res.text
    # A fresh client carrying the session cookie, for the caller to `async with`.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://t", cookies=login.cookies
    )


def _phone() -> str:
    return "+1555" + str(uuid.uuid4().int)[:7]


async def seed(org_id):
    """One of everything, in one company."""
    profile = await profiles_service.create_profile(org_id, {**DEFAULT_RO_PROFILE, "name": "Seeded"})
    customer = await customers_service.create_customer(
        org_id, {"name": "Seeded Customer", "phone": _phone(), "profile_id": profile.id}
    )
    number = await numbers_service.create_number(org_id, {"number": _phone()})
    call = await calls_service.create_call(customer.id, "outbound", org_id=org_id)
    campaign = await campaigns_service.create_campaign(
        org_id, {"name": "Seeded", "max_concurrent": 1, "max_attempts": 1, "retry_delay_minutes": 5}, [customer.id]
    )
    return profile, customer, number, call, campaign


# ── Isolation ────────────────────────────────────────────────────────────────
async def test_a_company_never_sees_or_changes_another_companys_data(orgs):
    a, b, _ = orgs
    profile, customer, number, call, campaign = await seed(b.id)
    client = await signed_in(await add_user(a.id, "owner"))

    async with client:
        # Lists contain nothing of B's.
        for path in ("/api/customers", "/api/calls"):
            assert (await client.get(path)).json()["total"] == 0, path
        assert (await client.get("/api/numbers")).json() == []
        assert (await client.get("/api/campaigns")).json() == []
        assert all(p["id"] != str(profile.id) for p in (await client.get("/api/profiles")).json())
        assert (await client.get("/api/stats/overview")).json()["total_calls"] == 0

        # Direct access by id is 404 — B's rows don't exist for A.
        not_found = [
            ("GET", f"/api/customers/{customer.id}", None),
            ("PATCH", f"/api/customers/{customer.id}", {"name": "Hijacked"}),
            ("GET", f"/api/calls/{call.id}", None),
            ("POST", "/api/calls", {"customer_id": str(customer.id)}),
            ("POST", "/api/calls/browser", {"customer_id": str(customer.id)}),
            ("GET", f"/api/profiles/{profile.id}", None),
            ("PATCH", f"/api/profiles/{profile.id}", {"name": "Hijacked"}),
            ("DELETE", f"/api/profiles/{profile.id}", None),
            ("PATCH", f"/api/numbers/{number.id}", {"label": "Hijacked"}),
            ("DELETE", f"/api/numbers/{number.id}", None),
            ("GET", f"/api/campaigns/{campaign.id}", None),
            ("POST", f"/api/campaigns/{campaign.id}/start", None),
            ("DELETE", f"/api/campaigns/{campaign.id}", None),
        ]
        for method, path, body in not_found:
            res = await client.request(method, path, json=body)
            assert res.status_code == 404, (method, path, res.status_code, res.text)
        res = await client.post(f"/api/numbers/{number.id}/sync-twilio")
        assert res.status_code == 502 and "not found" in res.json()["detail"].lower()

        # B's ids can't be smuggled into A's writes either.
        res = await client.post("/api/customers", json={"name": "X", "phone": _phone(), "profile_id": str(profile.id)})
        assert res.status_code == 422
        res = await client.post(
            "/api/campaigns", json={"name": "X", "customer_ids": [str(customer.id)]}
        )
        assert res.status_code == 422

    # Nothing of B's changed.
    assert (await customers_service.get_customer(customer.id, b.id)).name == "Seeded Customer"
    assert (await profiles_service.get_profile(profile.id, b.id)).name == "Seeded"
    found, _, _ = await campaigns_service.get_campaign_detail(campaign.id, b.id)
    assert found.status == "draft"


async def test_each_company_has_its_own_default_profile(orgs):
    a, b, _ = orgs
    pa = await profiles_service.get_default_profile(a.id)
    pb = await profiles_service.get_default_profile(b.id)
    assert pa.id != pb.id and pa.is_default and pb.is_default


async def test_inbound_call_lands_in_the_company_that_owns_the_number(orgs):
    from xml.etree import ElementTree

    a, b, _ = orgs
    number = await numbers_service.create_number(b.id, {"number": _phone()})
    from audiocall.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as client:
        res = await client.post("/voice", data={"CallSid": f"CA{uuid.uuid4().hex}", "From": _phone(), "To": number.number})
    call_id = uuid.UUID(ElementTree.fromstring(res.text).find("./Connect/Stream/Parameter").get("value"))
    call = await calls_service.get_call(call_id)
    assert call.org_id == b.id
    customer = await customers_service.get_customer(call.customer_id, b.id)
    assert customer is not None and customer.org_id == b.id


# ── Roles ────────────────────────────────────────────────────────────────────
async def test_roles_limit_what_each_user_can_do(orgs):
    a, _, _ = orgs
    viewer = await signed_in(await add_user(a.id, "viewer"))
    member = await signed_in(await add_user(a.id, "member"))
    admin = await signed_in(await add_user(a.id, "admin"))
    new_customer = {"name": "Role test", "phone": _phone()}
    profile_body = {**DEFAULT_RO_PROFILE, "name": "Role test profile"}

    async with viewer, member, admin:
        assert (await viewer.get("/api/customers")).status_code == 200
        assert (await viewer.post("/api/customers", json=new_customer)).status_code == 403
        assert (await viewer.get("/api/settings")).status_code == 403

        assert (await member.post("/api/customers", json=new_customer)).status_code == 201
        assert (await member.post("/api/profiles", json=profile_body)).status_code == 403
        assert (await member.post("/api/numbers", json={"number": _phone()})).status_code == 403
        assert (await member.get("/api/users")).status_code == 403

        assert (await admin.post("/api/profiles", json=profile_body)).status_code == 201
        assert (await admin.get("/api/users")).status_code == 200
        assert (await admin.patch("/api/organization", json={"name": "Renamed"})).status_code == 403
        # Admins can't create or touch owners.
        assert (await admin.post("/api/invites", json={"role": "owner"})).status_code == 403
        for path in ("/api/platform/organizations", "/api/platform/settings"):
            assert (await admin.get(path)).status_code == 403


async def test_a_company_always_keeps_an_owner(orgs):
    a, _, _ = orgs
    owner_name = await add_user(a.id, "owner")
    other_owner = await add_user(a.id, "owner")
    async with await signed_in(owner_name) as owner:
        users = {u["username"]: u for u in (await owner.get("/api/users")).json()}
        # Demoting the other owner is fine while I'm still an owner …
        res = await owner.patch(f"/api/users/{users[other_owner]['id']}", json={"role": "admin"})
        assert res.status_code == 200 and res.json()["role"] == "admin"
        # … but nobody can change their own role, or remove themselves.
        assert (await owner.patch(f"/api/users/{users[owner_name]['id']}", json={"role": "admin"})).status_code == 409
        assert (await owner.delete(f"/api/users/{users[owner_name]['id']}")).status_code == 409


async def test_deactivated_user_and_company_are_locked_out(orgs):
    a, _, _ = orgs
    username = await add_user(a.id, "member")
    client = await signed_in(username)
    async with client:
        assert (await client.get("/api/customers")).status_code == 200
        async with db_session.get_session_factory()() as session:
            await session.execute(update(AdminUser).where(AdminUser.username == username).values(is_active=False))
            await session.commit()
        assert (await client.get("/api/customers")).status_code == 401  # existing session stops working

    username = await add_user(a.id, "owner")
    client = await signed_in(username)
    async with client:
        async with db_session.get_session_factory()() as session:
            await session.execute(update(Organization).where(Organization.id == a.id).values(is_active=False))
            await session.commit()
        assert (await client.get("/api/customers")).status_code == 401


# ── Invites ──────────────────────────────────────────────────────────────────
async def test_invite_link_works_once_and_expires(orgs):
    a, _, _ = orgs
    from audiocall.main import app

    async with await signed_in(await add_user(a.id, "admin")) as admin:
        created = (await admin.post("/api/invites", json={"role": "member", "note": "ravi@acme.test"})).json()
        token = created["token"]
        assert [i["note"] for i in (await admin.get("/api/invites")).json()] == ["ravi@acme.test"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as guest:
        info = (await guest.get(f"/api/join/{token}")).json()
        assert info["organization"] == "Company A" and info["role"] == "member"
        username = f"t-joined-{uuid.uuid4().hex[:6]}"
        res = await guest.post(f"/api/join/{token}", json={"username": username, "password": PASSWORD})
        assert res.status_code == 201 and res.json()["organization"]["id"] == str(a.id)
        me = (await guest.get("/api/auth/me")).json()  # signed in right away
        assert me["role"] == "member"

        again = await guest.post(f"/api/join/{token}", json={"username": username + "x", "password": PASSWORD})
        assert again.status_code == 409  # single use
        assert (await guest.get(f"/api/join/{token}")).status_code == 404

    async with await signed_in(await add_user(a.id, "admin")) as admin:
        token = (await admin.post("/api/invites", json={"role": "viewer"})).json()["token"]
    async with db_session.get_session_factory()() as session:
        await session.execute(
            update(Invite).where(Invite.org_id == a.id, Invite.role == "viewer")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as guest:
        res = await guest.post(f"/api/join/{token}", json={"username": f"t-late-{uuid.uuid4().hex[:6]}", "password": PASSWORD})
        assert res.status_code == 409


# ── Platform administration ──────────────────────────────────────────────────
async def test_platform_admin_onboards_a_new_company(orgs):
    a, _, created = orgs
    from audiocall.main import app

    async with await signed_in(await add_user(a.id, "owner", platform=True)) as platform:
        res = await platform.post("/api/platform/organizations", json={"name": "Newco Solar", "max_concurrent_calls": 3})
        assert res.status_code == 201
        org = res.json()["organization"]
        created.append(uuid.UUID(org["id"]))
        token = res.json()["owner_invite"]["token"]
        listed = {o["name"]: o for o in (await platform.get("/api/platform/organizations")).json()}
        assert listed["Newco Solar"]["max_concurrent_calls"] == 3

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t") as owner:
        res = await owner.post(f"/api/join/{token}", json={"username": f"t-newco-{uuid.uuid4().hex[:6]}", "password": PASSWORD})
        me = res.json()
        assert me["organization"]["name"] == "Newco Solar" and me["role"] == "owner"
        assert me["is_platform_admin"] is False
        assert (await owner.get("/api/customers")).json()["total"] == 0  # a clean slate
        assert (await owner.get("/api/platform/organizations")).status_code == 403
        # The customer company's checklist leaves out the platform-only steps.
        keys = [i["key"] for i in (await owner.get("/api/setup/checklist")).json()["items"]]
        assert "gemini" not in keys and "twilio" in keys


async def test_company_call_limit_caps_free_lines(orgs, monkeypatch):
    from audiocall.core import config

    a, _, _ = orgs
    monkeypatch.setattr(config, "MAX_CONCURRENT_CALLS", 100)
    async with db_session.get_session_factory()() as session:
        await session.execute(update(Organization).where(Organization.id == a.id).values(max_concurrent_calls=1))
        await session.commit()
    assert await calls_service.free_lines(a.id) == 1
    customer = await customers_service.create_customer(a.id, {"name": "Busy", "phone": _phone()})
    await calls_service.create_call(customer.id, "outbound", org_id=a.id)  # queued = holding a line
    assert await calls_service.free_lines(a.id) == 0
