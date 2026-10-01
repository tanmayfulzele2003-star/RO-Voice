"""Pydantic models shared across services (not tied to the DB layer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    key: str = Field(description="The field key from the checklist, e.g. ro_capacity")
    value: str | None = Field(
        default=None, description="What the customer said, normalised; null if never provided"
    )


class CallAnalysis(BaseModel):
    """Structured extraction + summary produced from a call transcript.

    `fields` holds one entry per checklist field of the call's business
    profile, so the same contract works for any business.
    """

    fields: list[ExtractedField] = Field(default_factory=list)

    summary: str
    customer_intent: str
    key_requirements: list[str] = Field(default_factory=list)
    important_points: list[str] = Field(default_factory=list)
    lead_status: Literal["interested", "not_interested", "uncertain"]
    follow_up_required: bool
    follow_up_notes: str | None = Field(
        default=None, description="What the follow-up should cover, if one is required"
    )
    call_outcome: str = Field(
        default="",
        description="One sentence: how the call ended and what was agreed",
    )

    def field_values(self) -> dict[str, str | None]:
        return {f.key: f.value for f in self.fields}
