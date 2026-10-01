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
    }
