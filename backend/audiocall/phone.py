"""Phone-number normalisation and validation (E.164).

Twilio only dials E.164 numbers (`+` country code + subscriber number, max 15
digits). A local number without its country code is the most common reason an
outbound call is rejected, so numbers are validated when a customer is saved
rather than discovered when the call is placed.
"""

from __future__ import annotations

import re

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_SEPARATORS_RE = re.compile(r"[\s\-().]")


def normalize_phone(raw: str) -> str:
    """Strip spaces, dashes, dots and brackets; turn a leading `00` into `+`."""
    phone = _SEPARATORS_RE.sub("", raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    return phone


def is_valid_e164(phone: str) -> bool:
    return bool(_E164_RE.match(phone))
