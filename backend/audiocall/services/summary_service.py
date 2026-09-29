"""Post-call AI analysis: transcript -> structured requirements + summary.

Runs one non-live text call (Gemini by default, or NVIDIA NIM if
SUMMARY_PROVIDER=nvidia — NOT the Live API used for the phone call itself)
after a call ends.
"""

from __future__ import annotations

import logging
import os
import uuid

from google import genai
from google.genai import types
from openai import AsyncOpenAI
from sqlalchemy import select

from audiocall.db.models import CallSummary, ConversationMessage, Requirement
from audiocall.db.session import get_session_factory
from audiocall.schemas import CallAnalysis

logger = logging.getLogger(__name__)

# Separate from AGENT_MODEL (the Live API model used for the phone call itself)
# — this is a plain text model, no audio/native-audio requirement.
_SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "gemini-2.5-flash")

# Which backend runs post-call analysis: "gemini" (default, google-genai
# structured output) or "nvidia" (NVIDIA NIM, OpenAI-compatible chat
# completions API). The live call itself always uses Gemini Live regardless
# of this setting — NIM has no equivalent real-time audio API.
_SUMMARY_PROVIDER = os.environ.get("SUMMARY_PROVIDER", "gemini").lower()
_NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
_NVIDIA_MODEL = os.environ.get("NVIDIA_SUMMARY_MODEL", "nvidia/nemotron-3-super-120b-a12b")

_EXTRACTION_INSTRUCTION = (
    "You are analyzing a transcript of a phone call between an RO (reverse-osmosis "
    "water system) sales agent (AI) and a customer. Extract the customer's stated "
    "requirements and produce a short summary and lead assessment.\n\n"
    "Only use information actually present in the transcript — leave a field null "
    "if the customer never provided it. Do not guess or invent values.\n\n"
    "lead_status must be one of: interested, not_interested, uncertain.\n"
    "follow_up_required is true if the sales team should follow up with this "
    "customer (e.g. they showed interest but the call ended before finishing, or "
    "they asked to be contacted later), false if there's clearly nothing further "
    "to do (e.g. they explicitly said not interested).\n"
    "summary must be a coherent 2-4 sentence human summary of the call, not a "
    "restatement of the JSON fields."
)


def _client() -> genai.Client:
    # No explicit args: reads GOOGLE_API_KEY / GOOGLE_GENAI_USE_VERTEXAI /
    # GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION from the environment, same
    # as the Live API client in agent.py.
    return genai.Client()


def _nvidia_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ["NVIDIA_API_KEY"], base_url=_NVIDIA_BASE_URL)


async def build_transcript_text(call_id: uuid.UUID) -> str:
    """Reconstruct a readable `Customer: ...` / `AI: ...` transcript."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.call_id == call_id)
            .order_by(ConversationMessage.timestamp)
        )
        messages = result.scalars().all()

    lines = [
        f"{'Customer' if m.speaker == 'customer' else 'AI'}: {m.message}"
        for m in messages
    ]
    return "\n".join(lines)


async def analyze_call(transcript_text: str) -> CallAnalysis:
    """One non-live text call, constrained to the CallAnalysis JSON shape.

    Backend selected by SUMMARY_PROVIDER — "gemini" (default) or "nvidia".
    """
    if _SUMMARY_PROVIDER == "nvidia":
        return await _analyze_call_nvidia(transcript_text)
    return await _analyze_call_gemini(transcript_text)


async def _analyze_call_gemini(transcript_text: str) -> CallAnalysis:
    response = await _client().aio.models.generate_content(
        model=_SUMMARY_MODEL,
        contents=f"Transcript:\n{transcript_text}",
        config=types.GenerateContentConfig(
            system_instruction=_EXTRACTION_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=CallAnalysis,
        ),
    )
    return CallAnalysis.model_validate_json(response.text)


async def _analyze_call_nvidia(transcript_text: str) -> CallAnalysis:
    # NIM models don't accept a Pydantic response_schema like google-genai
    # does — fall back to JSON-object mode plus the schema spelled out in the
    # prompt, generated from CallAnalysis itself so the two never drift apart.
    schema_hint = CallAnalysis.model_json_schema()
    response = await _nvidia_client().chat.completions.create(
        model=_NVIDIA_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{_EXTRACTION_INSTRUCTION}\n\n"
                    "Respond with ONLY a single JSON object matching this JSON "
                    f"Schema, no surrounding text or markdown fences:\n{schema_hint}"
                ),
            },
            {"role": "user", "content": f"Transcript:\n{transcript_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return CallAnalysis.model_validate_json(response.choices[0].message.content)


async def persist_analysis(call_id: uuid.UUID, analysis: CallAnalysis) -> None:
    """Upsert into `requirements` and `call_summaries` (both unique on call_id)."""
    async with get_session_factory()() as session:
        requirement = await session.scalar(
            select(Requirement).where(Requirement.call_id == call_id)
        )
        if requirement is None:
            requirement = Requirement(call_id=call_id)
            session.add(requirement)
        requirement.customer_name = analysis.customer_name
        requirement.company_name = analysis.company_name
        requirement.requirement = analysis.requirement
        requirement.ro_capacity = analysis.ro_capacity
        requirement.location = analysis.location
        requirement.budget = analysis.budget
        requirement.timeline = analysis.timeline
        requirement.additional_requirements = analysis.additional_requirements

        summary = await session.scalar(
            select(CallSummary).where(CallSummary.call_id == call_id)
        )
        if summary is None:
            summary = CallSummary(call_id=call_id)
            session.add(summary)
        summary.summary = analysis.summary
        summary.customer_intent = analysis.customer_intent
        summary.key_requirements = analysis.key_requirements
        summary.important_points = analysis.important_points
        summary.follow_up = analysis.follow_up_required
        summary.lead_status = analysis.lead_status

        await session.commit()


async def _persist_failure_summary(call_id: uuid.UUID, reason: str) -> None:
    async with get_session_factory()() as session:
        summary = await session.scalar(
            select(CallSummary).where(CallSummary.call_id == call_id)
        )
        if summary is None:
            summary = CallSummary(call_id=call_id)
            session.add(summary)
        summary.summary = f"Analysis failed: {reason}"
        await session.commit()


async def post_call_processing(call_id: uuid.UUID) -> None:
    """Entry point called (fire-and-forget) whenever a call reaches a terminal
    status. Loads the transcript, runs extraction, and persists the result.

    Never raises — this always runs in the background, disconnected from any
    request/websocket that could observe an exception.
    """
    try:
        transcript_text = await build_transcript_text(call_id)
    except Exception:
        logger.exception("Call %s: failed to load transcript for analysis", call_id)
        return

    if not transcript_text.strip():
        logger.info("Call %s has an empty transcript — skipping AI analysis", call_id)
        return

    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            analysis = await analyze_call(transcript_text)
            await persist_analysis(call_id, analysis)
            logger.info("Call %s: analysis persisted (attempt %d)", call_id, attempt)
            return
        except Exception as exc:  # noqa: BLE001 - retry+record any SDK/validation failure
            last_error = exc
            logger.warning("Call %s: analysis attempt %d failed: %s", call_id, attempt, exc)

    logger.error("Call %s: analysis failed after retry: %s", call_id, last_error)
    try:
        await _persist_failure_summary(call_id, str(last_error))
    except Exception:
        logger.exception("Call %s: failed to persist failure summary", call_id)
