import pytest
from pydantic import ValidationError

from audiocall.api.schemas import CustomerCreate, CustomerUpdate, ProfileCreate, ProfileField
from audiocall.phone import is_valid_e164, normalize_phone


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+91 98765 43210", "+919876543210"),
        ("+1 (555) 123-4567", "+15551234567"),
        ("0091 98765 43210", "+919876543210"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected
    assert is_valid_e164(expected)


@pytest.mark.parametrize("bad", ["9876543210", "+0123456789", "+91", "abc", "+91987654321012345"])
def test_rejects_invalid_numbers(bad):
    with pytest.raises(ValidationError):
        CustomerCreate(name="Rahul", phone=bad)


def test_customer_update_phone_optional_but_validated():
    assert CustomerUpdate(name="x").phone is None
    with pytest.raises(ValidationError):
        CustomerUpdate(phone="12345")


def test_profile_field_key_generated_from_label():
    assert ProfileField(label="Number of Rooms").key == "number_of_rooms"
    assert ProfileField(label="2nd contact").key == "field_2nd_contact"


def test_profile_rejects_duplicate_keys_and_empty_fields():
    base = {"name": "Biz", "agent_name": "A", "call_objective": "Qualify"}
    with pytest.raises(ValidationError):
        ProfileCreate(**base, fields=[{"label": "Budget"}, {"label": "budget"}])
    with pytest.raises(ValidationError):
        ProfileCreate(**base, fields=[])
    with pytest.raises(ValidationError):
        ProfileCreate(**base, fields=[{"label": "x", "key": "Bad Key"}])
