from types import SimpleNamespace

from audiocall import agent
from audiocall.profiles import DEFAULT_RO_PROFILE


def _ctx(**state):
    return SimpleNamespace(state={"call_id": "", "profile": DEFAULT_RO_PROFILE, **state})


async def test_save_customer_info_tracks_progress_without_db():
    ctx = _ctx()
    result = await agent.save_customer_info("RO Capacity", "500 LPH", ctx)
    assert result["saved"] == {"key": "ro_capacity", "label": "RO Capacity", "value": "500 LPH"}
    assert ctx.state["collected"] == {"ro_capacity": "500 LPH"}
    assert "RO Capacity" not in result["still_missing"]
    assert result["next_field_to_ask"]["key"] == "customer_name"

    result = await agent.save_customer_info("location", "Bangalore", ctx)
    assert result["collected"] == {"RO Capacity": "500 LPH", "Location": "Bangalore"}


async def test_save_customer_info_unknown_field_returns_valid_keys():
    result = await agent.save_customer_info("shoe_size", "9", _ctx())
    assert "error" in result and "ro_capacity" in result["error"]


async def test_end_call_records_assessment():
    ctx = _ctx()
    await agent.end_call("interested", True, "requirements collected", ctx)
    assert ctx.state["end_call"]["lead_status"] == "interested"


def test_instruction_uses_business_profile_and_customer():
    hotel = {
        "name": "Sunrise Hotels",
        "agent_name": "Arjun",
        "call_objective": "Book a room",
        "language": "Hindi",
        "fields": [{"key": "check_in", "label": "Check-in date", "description": "", "required": True}],
    }
    text = agent.render_instruction(hotel, {"name": "Rahul Kumar", "purpose": "Booking enquiry"})
    assert "Arjun" in text and "Sunrise Hotels" in text and "Book a room" in text
    assert "check_in (Check-in date)" in text
    assert "Rahul Kumar" in text and "Booking enquiry" in text
    assert "Speak Hindi" in text
    assert "RO" not in text.replace("PHONE", "")  # nothing RO-specific leaks in


def test_agent_exposes_tools():
    assert {t.__name__ for t in agent.root_agent.tools} == {
        "save_customer_info",
        "get_call_progress",
        "end_call",
        "transfer_to_human",
    }


async def test_transfer_unavailable_on_browser_or_without_number():
    browser = _ctx(channel="browser", profile={**DEFAULT_RO_PROFILE, "transfer_number": "+919800000001"})
    assert (await agent.transfer_to_human("asked", "summary", browser))["status"] == "unavailable"
    no_number = _ctx(channel="phone")
    assert (await agent.transfer_to_human("asked", "summary", no_number))["status"] == "unavailable"
    assert "transfer" not in no_number.state


async def test_transfer_available_on_phone_with_number():
    ctx = _ctx(channel="phone", profile={**DEFAULT_RO_PROFILE, "transfer_number": "+919800000001"})
    result = await agent.transfer_to_human("hot lead", "Rahul wants 500 LPH", ctx)
    assert result["status"] == "transferring"
    assert ctx.state["transfer"] == {"reason": "hot lead", "summary": "Rahul wants 500 LPH"}


def test_instruction_adapts_to_inbound_calls_and_transfer():
    outbound = agent.render_instruction(DEFAULT_RO_PROFILE, {})
    inbound = agent.render_instruction(DEFAULT_RO_PROFILE, {}, direction="inbound")
    assert "outbound PHONE CALL" in outbound and "called YOU" not in outbound
    assert "inbound PHONE CALL" in inbound and "called YOU" in inbound

    with_transfer = agent.render_instruction(DEFAULT_RO_PROFILE, {}, transfer_available=True)
    assert "transfer_to_human" in with_transfer
    assert "transfer_to_human" not in outbound  # never offered a tool it can't use
