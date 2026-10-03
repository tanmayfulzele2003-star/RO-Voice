"""TwiML builders for the phone channel.

Pure functions (no I/O) so the exact XML Twilio receives is unit-tested. All
dynamic text goes through `escape`/`quoteattr`: customer names and agent
summaries end up inside these documents.
"""

from __future__ import annotations

import uuid
from xml.sax.saxutils import escape, quoteattr

_XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>'

BUSY_MESSAGE = (
    "Thank you for calling. All our lines are busy right now. "
    "Please try again in a few minutes. Goodbye."
)
NUMBER_DISABLED_MESSAGE = "Sorry, this number is not accepting calls right now. Goodbye."
TRANSFER_FAILED_MESSAGE = (
    "Sorry, no one from our team could take your call right now. "
    "We have your details and will call you back shortly. Goodbye."
)


def stream_twiml(stream_url: str, call_id: uuid.UUID) -> str:
    """Connect the call's audio to our /stream WebSocket.

    Twilio's Media Stream client doesn't reliably keep the query string on
    the WSS URL, so call_id is also sent as a <Parameter>, which comes back in
    the "start" event's customParameters.
    """
    return (
        f"{_XML_HEAD}<Response><Connect>"
        f"<Stream url={quoteattr(stream_url)}>"
        f'<Parameter name="call_id" value="{call_id}"/>'
        "</Stream></Connect></Response>"
    )


def say_and_hangup(message: str) -> str:
    return f"{_XML_HEAD}<Response><Say>{escape(message)}</Say><Hangup/></Response>"


def hangup() -> str:
    return f"{_XML_HEAD}<Response><Hangup/></Response>"


def dial_twiml(
    transfer_number: str,
    caller_id: str | None,
    timeout_seconds: int,
    action_url: str | None = None,
    whisper_url: str | None = None,
    announcement: str | None = None,
) -> str:
    """Connect the caller to a person.

    `whisper_url` is fetched when the person picks up and played to them
    only, before the two sides are bridged. `action_url` receives
    DialCallStatus once the <Dial> ends, so an unanswered transfer can fall
    back instead of dropping the caller.
    """
    attrs = f' timeout="{int(timeout_seconds)}"'
    if caller_id:
        attrs += f" callerId={quoteattr(caller_id)}"
    if action_url:
        attrs += f' action={quoteattr(action_url)} method="POST"'
    number_attrs = f" url={quoteattr(whisper_url)}" if whisper_url else ""
    say = f"<Say>{escape(announcement)}</Say>" if announcement else ""
    return (
        f"{_XML_HEAD}<Response>{say}"
        f"<Dial{attrs}><Number{number_attrs}>{escape(transfer_number)}</Number></Dial>"
        "</Response>"
    )


def whisper_twiml(customer_name: str | None, summary: str | None) -> str:
    """What the human hears before being connected."""
    who = customer_name or "a customer"
    text = f"Transferred call from {who}."
    if summary:
        text += f" {summary}"
    return f"{_XML_HEAD}<Response><Say>{escape(text)}</Say></Response>"


def business_number(direction: str | None, from_number: str | None, to_number: str | None) -> str | None:
    """Our side of the call: the caller ID on outbound calls, the dialled
    number on inbound ones. Twilio only accepts caller IDs the account owns."""
    return to_number if direction == "inbound" else from_number
