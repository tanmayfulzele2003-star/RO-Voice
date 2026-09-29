"""Environment-derived configuration and shared clients.

Split out from main.py so service modules and API routes can reuse the same
Twilio client / server-host config without importing main.py itself (which
would be a circular import, since main.py mounts the API routers that live in
those same service/api modules).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

# Safe to call even if the process entry point already loaded .env — this
# just makes the module self-contained for any other entry point (scripts,
# Alembic, tests) that imports it directly.
load_dotenv()

TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = os.environ.get("TWILIO_PHONE_NUMBER", "")

# SERVER_HOST should be your public hostname (e.g. abc123.ngrok.io). Twilio
# needs to reach this address for both the HTTP webhook and the WebSocket
# media stream. Strip any accidental scheme prefix.
_raw_host = os.environ.get("SERVER_HOST", "localhost:8000")
SERVER_HOST: str = _raw_host.removeprefix("https://").removeprefix("http://").rstrip("/")
USE_TLS: bool = os.environ.get("USE_TLS", "true").lower() == "true"

WS_SCHEME = "wss" if USE_TLS else "ws"
HTTP_SCHEME = "https" if USE_TLS else "http"

# The Next.js dashboard's origin, for CORS.
FRONTEND_ORIGIN: str = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

# How long (seconds) with no customer speech before we log a silence warning.
SILENCE_WARNING_SECONDS = 15
# How many barge-in interruptions in one call before we flag it as an
# "excessive interruption loop" error reason.
INTERRUPTION_THRESHOLD = 8

# ── Admin auth ───────────────────────────────────────────────────────────────
# Signs/verifies the session cookie issued by POST /api/auth/login. Must be a
# long random secret in any real deployment — there is no safe default here on
# purpose, so a missing SESSION_SECRET fails loudly rather than "working" with
# a guessable one.
SESSION_SECRET: str = os.environ.get("SESSION_SECRET", "")
SESSION_COOKIE_NAME = "audiocall_session"
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12 hours

# ── Twilio webhook signature validation ─────────────────────────────────────
# Disable only for local development without a real Twilio account/ngrok
# tunnel — never disable this in a real deployment.
TWILIO_VALIDATE_SIGNATURE: bool = (
    os.environ.get("TWILIO_VALIDATE_SIGNATURE", "true").lower() == "true"
)

# ── Rate limiting ────────────────────────────────────────────────────────────
# Outbound calling is billable — cap how many calls one admin session can
# start in a rolling window.
CALL_RATE_LIMIT_MAX = 5
CALL_RATE_LIMIT_WINDOW_SECONDS = 60

twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
