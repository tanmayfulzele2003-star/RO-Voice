"""Call outcome — the business result of a call, as one filterable value.

Status says what happened to the *phone call* (ringing, completed, failed...).
Outcome says what it *achieved*:

    qualified        conversation finished and the lead is interested
    not_interested   customer declined
    callback         lead is uncertain / asked to be contacted later (or a
                     transfer to a person wasn't answered)
    transferred      the agent handed the call to a real person
    incomplete       conversation started but ended before analysis could judge it
    no_answer        never picked up / busy
    no_conversation  answered, but the customer never said anything
    failed           telephony, AI, or other system failure
"""

from __future__ import annotations

OUTCOMES = (
    "qualified",
    "not_interested",
    "callback",
    "transferred",
    "incomplete",
    "no_answer",
    "no_conversation",
    "failed",
)

_LEAD_TO_OUTCOME = {
    "interested": "qualified",
    "not_interested": "not_interested",
    "uncertain": "callback",
}


def outcome_from_status(status: str | None, error_reason: str | None) -> str | None:
    """Outcome knowable from the call lifecycle alone (before AI analysis)."""
    if status == "no_answer":
        return "no_answer"
    if status == "failed":
        return "failed"
    if error_reason == "customer_silent":
        return "no_conversation"
    if status in ("completed", "disconnected"):
        return "incomplete"
    return None


def outcome_from_analysis(lead_status: str | None) -> str:
    return _LEAD_TO_OUTCOME.get(lead_status or "", "incomplete")
