from audiocall import conversation
from audiocall.profiles import DEFAULT_RO_FIELDS

FIELDS = DEFAULT_RO_FIELDS


def test_next_field_is_first_missing_required():
    assert conversation.next_field(FIELDS, {})["key"] == "customer_name"
    collected = {"customer_name": "Rahul", "requirement": "hotel", "ro_capacity": "500 LPH"}
    # company_name is optional, so it's skipped in favour of required fields
    assert conversation.next_field(FIELDS, collected)["key"] == "location"


def test_never_asks_again_for_collected_fields():
    collected = {"ro_capacity": "500 LPH", "location": "Bangalore"}
    progress = conversation.progress(FIELDS, collected)
    assert "RO Capacity" not in progress["still_missing"]
    assert "Location" not in progress["still_missing"]
    assert progress["collected"] == {"RO Capacity": "500 LPH", "Location": "Bangalore"}


def test_optional_fields_asked_after_required():
    collected = {f["key"]: "x" for f in FIELDS if f["required"]}
    progress = conversation.progress(FIELDS, collected)
    assert progress["all_required_collected"] is True
    assert progress["next_field_to_ask"]["key"] == "company_name"


def test_all_collected():
    progress = conversation.progress(FIELDS, {f["key"]: "x" for f in FIELDS})
    assert progress["next_field_to_ask"] is None
    assert progress["still_missing"] == []


def test_blank_values_count_as_missing():
    assert conversation.next_field(FIELDS, {"customer_name": "  "})["key"] == "customer_name"


def test_match_field_accepts_key_or_label():
    assert conversation.match_field(FIELDS, "ro_capacity")["key"] == "ro_capacity"
    assert conversation.match_field(FIELDS, "RO Capacity")["key"] == "ro_capacity"
    assert conversation.match_field(FIELDS, "ro-capacity")["key"] == "ro_capacity"
    assert conversation.match_field(FIELDS, "favourite colour") is None
