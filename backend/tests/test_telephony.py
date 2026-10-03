"""TwiML builders and the campaign retry rule — pure functions, no I/O."""

import uuid
from xml.etree import ElementTree

from audiocall.services import telephony
from audiocall.services.campaigns_service import next_contact_state


def test_stream_twiml_carries_call_id_twice():
    call_id = uuid.uuid4()
    xml = telephony.stream_twiml(f"wss://h/stream?call_id={call_id}&x=1", call_id)
    root = ElementTree.fromstring(xml)
    stream = root.find("./Connect/Stream")
    assert stream.get("url").endswith("&x=1")  # escaped in XML, intact once parsed
    assert stream.find("Parameter").get("value") == str(call_id)


def test_dial_twiml_with_whisper_and_fallback():
    xml = telephony.dial_twiml(
        "+919800000001",
        caller_id="+14155550100",
        timeout_seconds=25,
        action_url="https://h/transfer-status?call_id=1&a=b",
        whisper_url="https://h/transfer-whisper?call_id=1",
    )
    dial = ElementTree.fromstring(xml).find("Dial")
    assert dial.get("callerId") == "+14155550100"
    assert dial.get("timeout") == "25"
    assert dial.get("action") == "https://h/transfer-status?call_id=1&a=b"
    number = dial.find("Number")
    assert number.text == "+919800000001"
    assert number.get("url") == "https://h/transfer-whisper?call_id=1"


def test_dial_twiml_announcement_and_no_caller_id():
    root = ElementTree.fromstring(
        telephony.dial_twiml("+919800000001", None, 20, announcement="Please hold")
    )
    assert root.find("Say").text == "Please hold"
    assert root.find("Dial").get("callerId") is None


def test_whisper_escapes_customer_text():
    xml = telephony.whisper_twiml("Tom & <Jerry>", "Wants a quote </Say><Hangup/>")
    root = ElementTree.fromstring(xml)  # still well-formed
    assert root.find("Hangup") is None
    assert "Tom & <Jerry>" in root.find("Say").text


def test_say_and_hangup():
    root = ElementTree.fromstring(telephony.say_and_hangup(telephony.BUSY_MESSAGE))
    assert root.find("Say").text == telephony.BUSY_MESSAGE and root.find("Hangup") is not None


def test_business_number_is_our_side_of_the_call():
    assert telephony.business_number("outbound", "+1OURS", "+91CUST") == "+1OURS"
    assert telephony.business_number("inbound", "+91CUST", "+1OURS") == "+1OURS"


def test_contact_retried_only_when_unanswered_and_attempts_remain():
    assert next_contact_state("no_answer", "no_answer", attempts=1, max_attempts=2) == "pending"
    assert next_contact_state("failed", "failed", attempts=1, max_attempts=3) == "pending"
    assert next_contact_state("no_answer", "no_answer", attempts=2, max_attempts=2) == "failed"


def test_contact_done_once_the_call_got_through():
    assert next_contact_state("completed", "qualified", 1, 3) == "completed"
    assert next_contact_state("completed", "not_interested", 1, 3) == "completed"
    assert next_contact_state("disconnected", "no_conversation", 1, 3) == "completed"
    assert next_contact_state("in_progress", "transferred", 1, 3) == "completed"
