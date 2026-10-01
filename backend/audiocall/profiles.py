"""Business-profile defaults and helpers.

A business profile is everything the agent needs to run a qualification call
for one business. The RO profile below is the out-of-the-box default (seeded
by the migration that introduced profiles); admins can add more from the
dashboard for any other business.
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_RO_FIELDS: list[dict[str, Any]] = [
    {
        "key": "customer_name",
        "label": "Customer Name",
        "description": "The customer's full name",
        "required": True,
    },
    {
        "key": "company_name",
        "label": "Company Name",
        "description": "The business or organisation they represent, if any",
        "required": False,
    },
    {
        "key": "requirement",
        "label": "Requirement",
        "description": (
            "What they need the RO system for and where it will be used, e.g. drinking "
            "water for a hotel, industrial process water, a residential complex"
        ),
        "required": True,
    },
    {
        "key": "ro_capacity",
        "label": "RO Capacity",
        "description": "Required capacity, e.g. in LPH (litres per hour)",
        "required": True,
    },
    {
        "key": "location",
        "label": "Location",
        "description": "Installation city/area",
        "required": True,
    },
    {
        "key": "budget",
        "label": "Budget",
        "description": "Approximate budget range",
        "required": True,
    },
    {
        "key": "timeline",
        "label": "Timeline",
        "description": "When they want the system installed",
        "required": True,
    },
    {
        "key": "additional_requirements",
        "label": "Additional Requirements",
        "description": "Anything else relevant (water source, TDS, maintenance, etc.)",
        "required": False,
    },
]

DEFAULT_RO_PROFILE: dict[str, Any] = {
    "name": "AquaPure RO Systems",
    "agent_name": "Priya",
    "industry": "Water treatment",
    "description": (
        "Sells and installs reverse-osmosis (RO) water purification systems for "
        "homes, offices, hotels and industry."
    ),
    "products": (
        "Domestic RO (10-25 LPH), Commercial RO (50-1000 LPH), Industrial RO plants "
        "(1000+ LPH), water softeners, annual maintenance contracts."
    ),
    "call_objective": (
        "Qualify the lead: understand what RO system the customer needs and collect "
        "their requirements so the sales team can send a quotation."
    ),
    "greeting": None,
    "language": None,
    "fields": DEFAULT_RO_FIELDS,
}

# The fixed `requirements` columns; a collected field with one of these keys is
# mirrored into its column (handy for the default RO profile and SQL reporting).
FIXED_REQUIREMENT_COLUMNS = (
    "customer_name",
    "company_name",
    "requirement",
    "ro_capacity",
    "location",
    "budget",
    "timeline",
    "additional_requirements",
)

_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def slugify_field_key(text: str) -> str:
    """Turn a label like "Number of Rooms" into a field key `number_of_rooms`."""
    key = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    if not key or not key[0].isalpha():
        key = f"field_{key}" if key else "field"
    return key[:50]


def is_valid_field_key(key: str) -> bool:
    return bool(_FIELD_KEY_RE.match(key))
