"""Settings saved from the dashboard, first-run setup and industry templates.

The pure parts run everywhere; the database parts need RUN_DB_TESTS=1 (see
test_db_telephony.py) and clean up after themselves.
"""

import os
import uuid

import httpx
import pytest
from sqlalchemy import select, text

from audiocall.api.schemas import ProfileCreate
from audiocall.core import config, secrets_box
from audiocall.core.security import setup_token
from audiocall.services import settings_service
from audiocall.templates import TEMPLATES

needs_db = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="needs RUN_DB_TESTS=1 and a migrated Postgres"
)


@pytest.fixture
def restore_config(monkeypatch):
    """apply() mutates config and os.environ; put everything back."""
    for name in (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "SERVER_HOST",
        "USE_TLS",
        "WS_SCHEME",
        "HTTP_SCHEME",
        "twilio_client",
    ):
        monkeypatch.setattr(config, name, getattr(config, name))
    monkeypatch.setattr(settings_service, "_applied", {})
    monkeypatch.setattr(settings_service, "_from_dashboard", set())
    monkeypatch.setenv("GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", "test-key"))


# ── Pure ─────────────────────────────────────────────────────────────────────
def test_secrets_round_trip_and_are_not_plaintext():
    token = secrets_box.encrypt("my-auth-token")
    assert "my-auth-token" not in token
    assert secrets_box.decrypt(token) == "my-auth-token"
    with pytest.raises(secrets_box.SecretUnreadable):
        secrets_box.decrypt("not-a-valid-token")


def test_public_url_sets_host_and_schemes(restore_config):
    config.set_public_url("https://calls.example.com/")
    assert (config.SERVER_HOST, config.HTTP_SCHEME, config.WS_SCHEME) == ("calls.example.com", "https", "wss")
    assert config.public_url() == "https://calls.example.com" and not config.is_local_host()
    config.set_public_url("http://localhost:8000")
    assert config.WS_SCHEME == "ws" and config.is_local_host()


def test_apply_updates_running_config_and_gemini_key(restore_config):
    from audiocall import agent

    values = {
        "twilio_account_sid": "AC" + "1" * 32,
        "twilio_auth_token": "secret-token",
        "twilio_phone_number": "+14155550100",
        "google_api_key": "dashboard-key",
        "public_url": "https://calls.example.com",
    }
    agent._llm.api_client  # build the cached client with the old key
    settings_service.apply(values)
    assert config.TWILIO_ACCOUNT_SID == values["twilio_account_sid"]
    assert config.twilio_client.username == values["twilio_account_sid"]
    assert config.TWILIO_PHONE_NUMBER == "+14155550100"
    assert config.public_url() == "https://calls.example.com"
    assert os.environ["GOOGLE_API_KEY"] == "dashboard-key"
    assert agent._llm.api_client._api_client.api_key == "dashboard-key"


def test_secrets_are_masked_in_the_dashboard_view(restore_config):
    settings_service.apply(
        {
            "twilio_account_sid": "AC" + "2" * 32,
            "twilio_auth_token": "abcdefgh12345678",
            "twilio_phone_number": "",
            "google_api_key": "AIzaSyExampleKey9876",
            "public_url": "http://localhost:8000",
        }
    )
    view = settings_service.public_view()
    assert view["twilio_auth_token"]["value"] == "••••••••5678"
    assert view["google_api_key"]["value"].endswith("9876") and "AIza" not in view["google_api_key"]["value"]
    assert view["twilio_account_sid"]["value"] == "AC" + "2" * 32  # not a secret
    assert view["twilio_phone_number"] == {**view["twilio_phone_number"], "is_set": False, "source": "unset"}


def test_every_industry_template_is_a_valid_profile():
    ids = [t["id"] for t in TEMPLATES]
    assert len(ids) == len(set(ids))
    for template in TEMPLATES:
        ProfileCreate(**template["profile"])  # raises if a template is malformed


def test_setup_token_is_stable_and_overridable(monkeypatch):
    assert setup_token() == setup_token() and len(setup_token()) == 24
    monkeypatch.setenv("SETUP_TOKEN", "chosen-token")
    assert setup_token() == "chosen-token"


# ── Database ─────────────────────────────────────────────────────────────────
@pytest.fixture
async def db(restore_config):
    from audiocall.db import session as db_session

    db_session.get_engine.cache_clear()
    async with db_session.get_engine().begin() as conn:
        admins = (await conn.execute(text("SELECT count(*) FROM admin_users"))).scalar()
        saved = (await conn.execute(text("SELECT key, value, is_secret FROM app_settings"))).all()
    yield admins
    async with db_session.get_engine().begin() as conn:
        await conn.execute(text("DELETE FROM app_settings"))
        for row in saved:
            await conn.execute(
                text("INSERT INTO app_settings (key, value, is_secret) VALUES (:k, :v, :s)"),
                {"k": row.key, "v": row.value, "s": row.is_secret},
            )
        await conn.execute(text("DELETE FROM admin_users WHERE username LIKE 'setup-test-%'"))
    await db_session.get_engine().dispose()


async def _client():
    from audiocall.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")


@needs_db
async def test_saved_secret_is_encrypted_at_rest_and_clearing_falls_back(db, monkeypatch):
    from audiocall.db.models import AppSetting
    from audiocall.db.session import get_session_factory

    monkeypatch.setitem(config.ENV_DEFAULTS, "twilio_auth_token", "env-token")
    await settings_service.save({"twilio_auth_token": "dashboard-token", "twilio_phone_number": "+14155550123"})
    assert config.TWILIO_AUTH_TOKEN == "dashboard-token"
    assert settings_service.public_view()["twilio_auth_token"]["source"] == "dashboard"
    async with get_session_factory()() as session:
        row = await session.get(AppSetting, "twilio_auth_token")
        assert row.is_secret and "dashboard-token" not in row.value

    await settings_service.save({"twilio_auth_token": ""})
    assert config.TWILIO_AUTH_TOKEN == "env-token"
    assert settings_service.public_view()["twilio_auth_token"]["source"] == "environment"
    async with get_session_factory()() as session:
        assert await session.get(AppSetting, "twilio_auth_token") is None


@needs_db
async def test_unreadable_secret_is_ignored_not_fatal(db, monkeypatch):
    from audiocall.db.session import get_session_factory

    monkeypatch.setitem(config.ENV_DEFAULTS, "google_api_key", "env-key")
    async with get_session_factory()() as session:
        await session.execute(
            text("INSERT INTO app_settings (key, value, is_secret) VALUES ('google_api_key', 'garbage', true)")
        )
        await session.commit()
    await settings_service.load()  # e.g. SESSION_SECRET was rotated
    assert os.environ["GOOGLE_API_KEY"] == "env-key"


@needs_db
async def test_first_admin_needs_the_token_and_works_once(db):
    if db:
        pytest.skip("database already has admins")
    async with await _client() as client:
        assert (await client.get("/api/setup/status")).json() == {"needs_admin": True}
        body = {"username": "setup-test-a", "password": "long-enough-pw"}
        assert (await client.post("/api/setup/admin", json={**body, "token": "wrong"})).status_code == 403

        res = await client.post("/api/setup/admin", json={**body, "token": setup_token()})
        assert res.status_code == 201 and "audiocall_session" in res.cookies
        assert (await client.get("/api/auth/me")).json() == {"username": "setup-test-a"}  # logged in

        again = await client.post(
            "/api/setup/admin", json={"username": "setup-test-b", "password": "long-enough-pw", "token": setup_token()}
        )
        assert again.status_code == 409
        assert (await client.get("/api/setup/status")).json() == {"needs_admin": False}

        checklist = (await client.get("/api/setup/checklist")).json()
        assert [i["key"] for i in checklist["items"]] == [
            "twilio", "number", "gemini", "public_url", "profile", "test_call",
        ]
        assert (await client.post("/api/setup/flags", json={"key": "setup_completed", "value": True})).status_code == 204
        assert (await client.get("/api/setup/checklist")).json()["dismissed"] is True

        templates = (await client.get("/api/profiles/templates")).json()
        assert {t["id"] for t in templates} >= {"water_treatment", "real_estate", "clinic"}

        res = await client.patch("/api/settings", json={"public_url": "calls.example.com"})
        assert res.status_code == 422  # scheme required
        res = await client.patch("/api/settings", json={"public_url": "https://calls.example.com"})
        assert res.json()["public_url"]["value"] == "https://calls.example.com"
        # No Twilio credentials in the test environment: a clear "enter them" answer, not a crash.
        twilio = (await client.post("/api/settings/test-twilio")).json()
        assert twilio["ok"] is False and "Account SID" in twilio["message"]


@needs_db
async def test_settings_routes_require_login(db):
    async with await _client() as client:
        assert (await client.get("/api/settings")).status_code == 401
        assert (await client.get("/api/setup/checklist")).status_code == 401
        assert (await client.get("/api/setup/status")).status_code == 200  # public


def test_flag_keys_cannot_overwrite_settings():
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(settings_service.set_flag("twilio_auth_token", "x"))
