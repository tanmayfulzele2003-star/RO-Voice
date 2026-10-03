"""Encryption for secrets stored in the database (Twilio auth token, Gemini
key). Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from
SETTINGS_ENCRYPTION_KEY, or SESSION_SECRET when that isn't set.

Rotating that secret makes stored values unreadable: they then count as
unset (logged), and are re-entered in the dashboard.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from audiocall.core import config


class SecretUnreadable(Exception):
    pass


def _fernet() -> Fernet:
    secret = os.environ.get("SETTINGS_ENCRYPTION_KEY") or config.SESSION_SECRET
    if not secret:
        raise RuntimeError("Set SESSION_SECRET (or SETTINGS_ENCRYPTION_KEY) to store secrets.")
    digest = hashlib.sha256(f"audiocall-settings:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretUnreadable("stored secret can't be decrypted with the current key") from exc
