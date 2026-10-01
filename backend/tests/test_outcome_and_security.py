import time
import uuid

from twilio.base.exceptions import TwilioRestException

from audiocall.core import security
from audiocall.services.calls_service import describe_twilio_error
from audiocall.services.outcome import outcome_from_analysis, outcome_from_status


def test_outcome_from_status():
    assert outcome_from_status("no_answer", None) == "no_answer"
    assert outcome_from_status("failed", "ai_error") == "failed"
    assert outcome_from_status("completed", "customer_silent") == "no_conversation"
    assert outcome_from_status("completed", None) == "incomplete"
    assert outcome_from_status("in_progress", None) is None


def test_outcome_from_analysis():
    assert outcome_from_analysis("interested") == "qualified"
    assert outcome_from_analysis("not_interested") == "not_interested"
    assert outcome_from_analysis("uncertain") == "callback"
    assert outcome_from_analysis(None) == "incomplete"


def test_twilio_trial_errors_are_explained():
    exc = TwilioRestException(400, "uri", msg="The number is unverified", code=21219)
    event_type, reason = describe_twilio_error(exc)
    assert event_type == "provider_error"
    assert "Verified Caller IDs" in reason
    event_type, reason = describe_twilio_error(TwilioRestException(400, "uri", msg="bad", code=21211))
    assert event_type == "invalid_number"


def test_stream_token_bound_to_call_and_expiry(monkeypatch):
    call_id, other = uuid.uuid4(), uuid.uuid4()
    token = security.create_stream_token(call_id)
    assert security.verify_stream_token(token, call_id)
    assert not security.verify_stream_token(token, other)
    assert not security.verify_stream_token("garbage", call_id)
    # A session token can't be used as a stream token.
    assert not security.verify_stream_token(security.create_session_token("admin"), call_id)
    monkeypatch.setattr(time, "time", lambda: 10**12)
    assert not security.verify_stream_token(token, call_id)
