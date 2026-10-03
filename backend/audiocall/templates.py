"""Industry templates for business profiles.

A new customer of the product picks the template closest to their business in
the setup wizard and edits the name, products and questions from there,
instead of writing a profile from a blank page.
"""

from __future__ import annotations

from typing import Any

from audiocall.profiles import DEFAULT_RO_PROFILE


def _field(key: str, label: str, description: str, required: bool = True) -> dict[str, Any]:
    return {"key": key, "label": label, "description": description, "required": required}


_NAME = _field("customer_name", "Customer Name", "The customer's full name")
_LOCATION = _field("location", "Location", "City or area")
_TIMELINE = _field("timeline", "Timeline", "When they want to go ahead")
_BUDGET = _field("budget", "Budget", "Approximate budget range")
_NOTES = _field("additional_requirements", "Anything else", "Other details worth passing on", False)


TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "water_treatment",
        "title": "Water treatment / RO",
        "summary": "Qualify RO and water-purifier leads for a quotation.",
        "profile": DEFAULT_RO_PROFILE,
    },
    {
        "id": "real_estate",
        "title": "Real estate",
        "summary": "Qualify buyers and book site visits.",
        "profile": {
            "name": "Your Realty",
            "agent_name": "Ananya",
            "industry": "Real estate",
            "description": "Sells residential apartments and villas.",
            "products": "2 and 3 BHK apartments, villas, plots. Site visits on weekends.",
            "call_objective": (
                "Understand what the buyer is looking for and offer a site visit, so a "
                "sales manager can follow up with matching properties."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _NAME,
                _field("property_type", "Property type", "Apartment, villa or plot; number of bedrooms"),
                _LOCATION,
                _BUDGET,
                _field("purpose", "Purpose", "To live in, or as an investment"),
                _TIMELINE,
                _field("site_visit", "Site visit", "Whether and when they'd like to visit", False),
            ],
        },
    },
    {
        "id": "clinic",
        "title": "Clinic / healthcare",
        "summary": "Take appointment requests and triage the reason for the visit.",
        "profile": {
            "name": "Your Clinic",
            "agent_name": "Meera",
            "industry": "Healthcare",
            "description": "A multi-speciality outpatient clinic.",
            "products": "General physician, dental, dermatology and physiotherapy consultations.",
            "call_objective": (
                "Collect an appointment request: who the patient is, the reason for the "
                "visit and a preferred time. Never give medical advice; for an emergency, "
                "tell them to call emergency services."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _field("customer_name", "Patient name", "The patient's full name"),
                _field("reason", "Reason for visit", "Symptoms or the service they need"),
                _field("department", "Department", "Which speciality, if they know"),
                _field("preferred_time", "Preferred time", "Day and time that suits them"),
                _field("new_patient", "New patient", "Whether they've visited before", False),
            ],
        },
    },
    {
        "id": "solar",
        "title": "Solar installation",
        "summary": "Qualify rooftop solar leads for a site survey.",
        "profile": {
            "name": "Your Solar",
            "agent_name": "Rohan",
            "industry": "Solar energy",
            "description": "Designs and installs rooftop solar for homes and businesses.",
            "products": "On-grid and hybrid rooftop systems, 3 kW to 100 kW, subsidy assistance.",
            "call_objective": (
                "Understand the customer's electricity use and roof, and book a free site "
                "survey so an engineer can prepare a quote."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _NAME,
                _field("property_type", "Property type", "Home, office, factory, etc."),
                _field("monthly_bill", "Monthly electricity bill", "Approximate amount per month"),
                _field("roof", "Roof", "Roof type and roughly how much space is free"),
                _LOCATION,
                _TIMELINE,
            ],
        },
    },
    {
        "id": "insurance",
        "title": "Insurance",
        "summary": "Qualify interest in a policy for an advisor call-back.",
        "profile": {
            "name": "Your Insurance",
            "agent_name": "Kabir",
            "industry": "Insurance",
            "description": "An insurance advisory firm.",
            "products": "Health, term life, motor and home insurance.",
            "call_objective": (
                "Find out which cover the customer is interested in and their basic "
                "details so a licensed advisor can call back with quotes. Don't quote "
                "premiums yourself."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _NAME,
                _field("insurance_type", "Insurance type", "Health, life, motor or home"),
                _field("cover_for", "Cover for", "Who the policy is for (self, family, vehicle…)"),
                _field("existing_policy", "Existing policy", "Whether they already have one", False),
                _field("callback_time", "Best time to call", "When the advisor should call"),
            ],
        },
    },
    {
        "id": "education",
        "title": "Education / coaching",
        "summary": "Qualify course enquiries and book a counselling session.",
        "profile": {
            "name": "Your Academy",
            "agent_name": "Isha",
            "industry": "Education",
            "description": "Runs coaching and skill-development courses, online and in person.",
            "products": "Exam preparation, coding bootcamps, language courses.",
            "call_objective": (
                "Understand what the student wants to learn and offer a free counselling "
                "session with an academic advisor."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _field("customer_name", "Student name", "The student's full name"),
                _field("course", "Course of interest", "What they want to study"),
                _field("current_level", "Current level", "Class, degree or experience"),
                _field("mode", "Mode", "Online or in person", False),
                _field("counselling_time", "Counselling slot", "When they're free for a session"),
            ],
        },
    },
    {
        "id": "hospitality",
        "title": "Hotel / hospitality",
        "summary": "Take booking enquiries for rooms and events.",
        "profile": {
            "name": "Your Hotel",
            "agent_name": "Arjun",
            "industry": "Hospitality",
            "description": "A business hotel with rooms, a restaurant and banquet halls.",
            "products": "Deluxe and suite rooms, banquet halls for 50-500 guests, airport pickup.",
            "call_objective": (
                "Collect the booking enquiry so the reservations team can confirm "
                "availability and send a quote."
            ),
            "greeting": None,
            "language": None,
            "fields": [
                _field("customer_name", "Guest name", "The guest's full name"),
                _field("booking_type", "Booking type", "Room stay or event"),
                _field("dates", "Dates", "Check-in and check-out, or the event date"),
                _field("guests", "Guests", "Number of guests or rooms"),
                _BUDGET | {"required": False},
                _NOTES,
            ],
        },
    },
    {
        "id": "general",
        "title": "General lead qualification",
        "summary": "A starting point for any other business.",
        "profile": {
            "name": "Your Business",
            "agent_name": "Alex",
            "industry": None,
            "description": None,
            "products": None,
            "call_objective": (
                "Understand what the customer needs and collect their details so the team "
                "can follow up."
            ),
            "greeting": None,
            "language": None,
            "fields": [_NAME, _field("requirement", "Requirement", "What they need"), _BUDGET, _TIMELINE, _NOTES],
        },
    },
]


def get_template(template_id: str) -> dict[str, Any] | None:
    return next((t for t in TEMPLATES if t["id"] == template_id), None)
