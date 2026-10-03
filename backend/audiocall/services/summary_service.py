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

from audiocall import conversation
from audiocall.db.models import Call, CallSummary, ConversationMessage, Requirement
from audiocall.db.session import get_session_factory
from audiocall.schemas import CallAnalysis
from audiocall.services import calls_service, events_service
from audiocall.services.outcome import outcome_from_analysis
from audiocall.services.requirements_service import apply_fields

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
    "You are analysing the transcript of a phone call between an AI agent calling on "
    "behalf of a business and a customer. Extract the customer's stated details for each "
    "checklist field and produce a short summary and lead assessment.\n\n"
    "Business: {business}\nCall objective: {objective}\n\n"
    "Checklist fields (return one `fields` entry per key, in this order):\n{fields}\n\n"
    "Only use information actually present in the transcript — set value to null "
    "if the customer never provided it. Do not guess or invent values.\n\n"
    "lead_status must be one of: interested, not_interested, uncertain.\n"
    "follow_up_required is true if the sales team should follow up with this "
    "customer (e.g. they showed interest but the call ended before finishing, or "
    "they asked to be contacted later), false if there's clearly nothing further "
    "to do (e.g. they explicitly said not interested). follow_up_notes says what "
    "the follow-up should cover.\n"
    "key_requirements: the customer's main needs as short bullet strings.\n"
    "important_points: other notable things said (objections, questions, preferences).\n"
    "call_outcome: one sentence on how the call ended and what was agreed.\n"
    "summary must be a coherent 2-4 sentence human summary of the call, not a "
    "restatement of the JSON fields."
)


def build_instruction(profile: dict) -> str:
    return _EXTRACTION_INSTRUCTION.format(
        business=profile["name"],
        objective=profile["call_objective"],
        fields=conversation.format_fields_for_prompt(profile["fields"]),
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


async def analyze_call(transcript_text: str, instruction: str) -> CallAnalysis:
    """One non-live text call, constrained to the CallAnalysis JSON shape.

    Backend selected by SUMMARY_PROVIDER — "gemini" (default) or "nvidia".
    """
    if _SUMMARY_PROVIDER == "nvidia":
        return await _analyze_call_nvidia(transcript_text, instruction)
    return await _analyze_call_gemini(transcript_text, instruction)


async def _analyze_call_gemini(transcript_text: str, instruction: str) -> CallAnalysis:
    response = await _client().aio.models.generate_content(
        model=_SUMMARY_MODEL,
        contents=f"Transcript:\n{transcript_text}",
        config=types.GenerateContentConfig(
            system_instruction=instruction,
            response_mime_type="application/json",
            response_schema=CallAnalysis,
        ),
    )
    return CallAnalysis.model_validate_json(response.text)


async def _analyze_call_nvidia(transcript_text: str, instruction: str) -> CallAnalysis:
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
                    f"{instruction}\n\n"
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
    """Upsert into `requirements` and `call_summaries` (both unique on call_id),
    and set the call's outcome from the lead assessment."""
    async with get_session_factory()() as session:
        requirement = await session.scalar(
            select(Requirement).where(Requirement.call_id == call_id)
        )
        if requirement is None:
            requirement = Requirement(call_id=call_id, fields={})
            session.add(requirement)
        # Merges over what the agent saved live during the call; a null from
        # the extraction never erases a live-collected value.
        apply_fields(requirement, analysis.field_values())

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
        summary.follow_up_notes = analysis.follow_up_notes
        summary.call_outcome = analysis.call_outcome
        summary.lead_status = analysis.lead_status

        call = await session.get(Call, call_id)
        # A handed-off call's outcome comes from the transfer (transferred /
        # callback), not from the AI's half of the conversation.
        if call is not None and call.status != "failed" and call.transferred_to is None:
            call.outcome = outcome_from_analysis(analysis.lead_status)

        await session.commit()


async def _persist_failure_summary(call_id: uuid.UUID, reason: str) -> None:
    async with get_session_factory()() as session:
        summary = await session.scalar(
            select(CallSummary).where(CallSummary.call_id == call_id)
        )
        if summary is None:
            summary = CallSummary(call_id=call_id)
            session.add(summary)
        summary.summary = (
            "AI summary could not be generated. The lead status and follow-up shown are "
            f"the agent's own end-of-call assessment. ({reason})"
        )
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

    try:
        context = await calls_service.load_call_context(call_id)
        if context is None:
            logger.info("Call %s no longer exists — skipping AI analysis", call_id)
            return
        profile = context["profile"]
    except Exception:
        logger.exception("Call %s: failed to load business profile for analysis", call_id)
        return
    instruction = build_instruction(profile)

    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            analysis = await analyze_call(transcript_text, instruction)
            await persist_analysis(call_id, analysis)
            logger.info("Call %s: analysis persisted (attempt %d)", call_id, attempt)
            return
        except Exception as exc:  # noqa: BLE001 - retry+record any SDK/validation failure
            last_error = exc if str(exc) else RuntimeError(type(exc).__name__)
            logger.warning("Call %s: analysis attempt %d failed: %s", call_id, attempt, exc)

    logger.error("Call %s: analysis failed after retry: %s", call_id, last_error)
    reason = f"{type(last_error).__name__}: {last_error}"[:500]
    await events_service.record(call_id, "analysis_failed", reason)
    try:
        await _persist_failure_summary(call_id, reason)
    except Exception:
        logger.exception("Call %s: failed to persist failure summary", call_id)
