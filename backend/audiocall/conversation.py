"""Conversation state for the calling agent — pure functions, no I/O.

The agent's checklist is the business profile's `fields`. As the customer
answers, the agent calls its `save_customer_info` tool; these helpers work out
what is still missing and which question should come next, and the tool hands
that decision back to the model. That's what keeps the agent from re-asking
for something it already has, independently of how well the LLM tracks it.
"""

from __future__ import annotations

from typing import Any

FieldDef = dict[str, Any]  # {"key", "label", "description", "required"}

# Values that mean "the customer answered, but has no answer" — counted as
# collected so the agent moves on instead of asking again.
DECLINED_VALUES = {"not provided", "declined", "unknown", "none", "n/a", "na", "not sure"}


def field_by_key(fields: list[FieldDef], key: str) -> FieldDef | None:
    return next((f for f in fields if f["key"] == key), None)


def match_field(fields: list[FieldDef], name: str) -> FieldDef | None:
    """Resolve the model's field reference — tolerant of label-vs-key and
    case/spacing differences ("RO Capacity" -> `ro_capacity`)."""
    normalized = name.strip().lower().replace(" ", "_").replace("-", "_")
    for f in fields:
        if normalized in (f["key"], f["label"].strip().lower().replace(" ", "_")):
            return f
    return None


def missing_fields(fields: list[FieldDef], collected: dict[str, str]) -> list[FieldDef]:
    return [f for f in fields if not (collected.get(f["key"]) or "").strip()]


def next_field(fields: list[FieldDef], collected: dict[str, str]) -> FieldDef | None:
    """Next field to ask for: required ones first, in profile order."""
    missing = missing_fields(fields, collected)
    required = [f for f in missing if f.get("required", True)]
    return (required or missing or [None])[0]


def progress(fields: list[FieldDef], collected: dict[str, str]) -> dict[str, Any]:
    """Snapshot handed back to the model after every tool call."""
    missing = missing_fields(fields, collected)
    nxt = next_field(fields, collected)
    required_missing = [f for f in missing if f.get("required", True)]
    return {
        "collected": {
            f["label"]: collected[f["key"]] for f in fields if (collected.get(f["key"]) or "").strip()
        },
        "still_missing": [f["label"] for f in missing],
        "next_field_to_ask": (
            {"key": nxt["key"], "label": nxt["label"], "about": nxt.get("description", "")}
            if nxt
            else None
        ),
        "all_required_collected": not required_missing,
    }


def format_fields_for_prompt(fields: list[FieldDef]) -> str:
    lines = []
    for i, f in enumerate(fields, 1):
        optional = "" if f.get("required", True) else " (optional)"
        desc = f" — {f['description']}" if f.get("description") else ""
        lines.append(f"{i}. {f['key']} ({f['label']}){optional}{desc}")
    return "\n".join(lines)
