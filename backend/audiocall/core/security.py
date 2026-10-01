"""Password hashing, signed session-cookie tokens, and Twilio request
signature verification.

Session tokens are a deliberately simple stateless design: `username:expiry`
signed with HMAC-SHA256 over `SESSION_SECRET`, base64url-encoded. No session
table needed — verifying a token is just recomputing and comparing the
signature, so any process holding `SESSION_SECRET` can validate it without a
DB round-trip. `admin_users` (bcrypt password hashes) is the actual durable
state; sessions are not persisted anywhere.

Uses `bcrypt` directly rather than `passlib` —
passlib's bcrypt backend has had ongoing compatibility breaks against modern
bcrypt releases (it inspects an internal version string that changed), so the
current common recommendation is to call the actively-maintained `bcrypt`
package directly instead.
"""

from __future__ import annotations

import base64
import hmac
import time
from hashlib import sha256

import bcrypt
from twilio.request_validator import RequestValidator

from audiocall.core import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. empty string) — never a valid match.
        return False


def _require_session_secret() -> str:
    if not config.SESSION_SECRET:
        raise RuntimeError(
            "SESSION_SECRET is not set. Set it to a long random value before "
            "issuing or verifying admin sessions."
        )
    return config.SESSION_SECRET


def _sign(payload: str) -> str:
    secret = _require_session_secret()
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()


def create_session_token(username: str) -> str:
    expiry = int(time.time()) + config.SESSION_TTL_SECONDS
    payload = f"{username}:{expiry}"
    token = f"{payload}:{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def verify_session_token(token: str) -> str | None:
    """Returns the username if the token is validly signed and unexpired."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, expiry_str, signature = decoded.split(":", 2)
        expiry = int(expiry_str)
    except (ValueError, UnicodeDecodeError):
        return None

    expected_signature = _sign(f"{username}:{expiry}")
    if not hmac.compare_digest(signature, expected_signature):
        return None
    if time.time() > expiry:
        return None
    return username


def verify_twilio_signature(url: str, params: dict[str, str], signature: str) -> bool:
    """Validates Twilio's `X-Twilio-Signature` header for a webhook request.

    `url` must be the exact public URL Twilio requested (scheme + host from
    our own config, not necessarily what the app server sees behind a proxy)
    including its query string; `params` is the POST form body.
    """
    validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
    return validator.validate(url, params, signature)


# ── Browser call stream tokens ──────────────────────────────────────────────
# The browser demo channel's WebSocket can't rely on the session cookie (the
# dashboard and API are usually on different sites in production), so
# `POST /api/calls/browser` — itself admin-only — hands out a short-lived
# token bound to one call_id.
STREAM_TOKEN_TTL_SECONDS = 120


def create_stream_token(call_id: object) -> str:
    expiry = int(time.time()) + STREAM_TOKEN_TTL_SECONDS
    payload = f"stream:{call_id}:{expiry}"
    return base64.urlsafe_b64encode(f"{payload}:{_sign(payload)}".encode()).decode()


def verify_stream_token(token: str, call_id: object) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        prefix, token_call_id, expiry_str, signature = decoded.split(":", 3)
        expiry = int(expiry_str)
    except (ValueError, UnicodeDecodeError):
        return False
    payload = f"{prefix}:{token_call_id}:{expiry}"
    return (
        prefix == "stream"
        and token_call_id == str(call_id)
        and hmac.compare_digest(signature, _sign(payload))
        and time.time() <= expiry
    )
