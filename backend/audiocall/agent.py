"""Google ADK agent definition for the calling agent.

Agentic design
--------------
The agent isn't a script with a prompt per sentence. It runs one Gemini Live
session per call and is given:

* a **business profile** (built into its instructions per call from session
  state) — who it represents, what it sells, the call objective, and a
  checklist of fields to collect. Any business can be set up from the
  dashboard; the RO profile is just the default.
* **tools** it decides on its own when to call:
    - `save_customer_info` — record a fact the customer gave. Returns what's
      still missing and which field to ask next (see conversation.py), so the
      agent never re-asks for something it already has.
    - `get_call_progress` — re-check the checklist (e.g. after a digression).
    - `end_call` — finish the call with its own lead assessment; the bridge
      hangs up once the goodbye has finished playing.
    - `transfer_to_human` — hand the call to a real person (the profile's
      transfer number, phone calls only); the bridge redirects the live call
      once the agent's "connecting you" line has played.

Instructions adapt to the call's direction: on an outbound call the agent
introduces itself and says why it's calling; on an inbound call it thanks the
caller and asks how it can help.
"""

import contextlib
import logging
import os
import uuid
from typing import Any, AsyncIterator, Literal

from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from audiocall import conversation
from audiocall.profiles import DEFAULT_RO_PROFILE

logger = logging.getLogger(__name__)

# Use environment variable with a sensible default.
# - Gemini Live API (public):  gemini-2.5-flash-native-audio-preview-12-2025
# - Vertex AI Live API:        gemini-live-2.5-flash-native-audio
_MODEL = os.getenv("AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")


class GeminiNoThinking(Gemini):
    """Gemini subclass that disables dynamic thinking before each Live connection.

    The native-audio preview model has Dynamic Thinking enabled by default,
    which adds ~2-3 seconds of pre-response latency.  Setting thinking_budget=0
    disables it without requiring any additional SDK support in RunConfig.
    """

    @contextlib.asynccontextmanager
    async def connect(self, llm_request: LlmRequest) -> AsyncIterator:  # type: ignore[override]
        llm_request.live_connect_config.thinking_config = types.ThinkingConfig(
            thinking_budget=0
        )
        async with super().connect(llm_request) as conn:
            yield conn


# Configure a clear, professional voice for phone calls.
# Native audio models support the full TTS voice library; "Puck" is a crisp,
# articulate voice well suited for phone conversations.
_llm = GeminiNoThinking(
    model=_MODEL,
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=os.getenv("AGENT_VOICE", "Puck")
            )
        )
    ),
)



# ── Instructions (built per call from session state) ──────────────────────────
def build_instruction(ctx: ReadonlyContext) -> str:
    return render_instruction(
        ctx.state.get("profile"),
        ctx.state.get("customer"),
        direction=ctx.state.get("direction") or "outbound",
        transfer_available=transfer_available(ctx.state),
    )


def transfer_available(state) -> bool:  # noqa: ANN001 — dict or ADK State
    """A person can take over: phone channel and a transfer number set."""
    profile = state.get("profile") or {}
    return state.get("channel") == "phone" and bool(profile.get("transfer_number"))


def render_instruction(
    profile: dict | None,
    customer: dict | None,
    direction: str = "outbound",
    transfer_available: bool = False,
) -> str:
    profile = profile or DEFAULT_RO_PROFILE
    customer = customer or {}
    fields = profile.get("fields") or DEFAULT_RO_PROFILE["fields"]

    business = profile["name"]
    agent_name = profile.get("agent_name") or "Alex"
    about = "\n".join(
        line
        for line in (
            f"Industry: {profile['industry']}" if profile.get("industry") else "",
            f"About the business: {profile['description']}" if profile.get("description") else "",
            f"Products / services: {profile['products']}" if profile.get("products") else "",
        )
        if line
    )

    known = [
        f"- Name: {customer['name']}" if customer.get("name") else "",
        f"- Company: {customer['company']}" if customer.get("company") else "",
        f"- Purpose of this call: {customer['purpose']}" if customer.get("purpose") else "",
        f"- Product of interest: {customer['product']}" if customer.get("product") else "",
    ]
    known_block = "\n".join(k for k in known if k) or "- Nothing yet."

    inbound = direction == "inbound"
    if inbound:
        greeting = (
            f"The customer called YOU. Thank them for calling {business}, introduce yourself as "
            f"{agent_name}, and ask how you can help. Work out why they're calling before "
            "steering towards the checklist."
        )
    elif profile.get("greeting"):
        greeting = f'Open with this greeting (adapt naturally, keep the meaning): "{profile["greeting"]}"'
    else:
        greeting = (
            f"Open by greeting the customer by name if you know it, introduce yourself as "
            f"{agent_name} from {business}, and say briefly why you're calling."
        )

    if profile.get("language"):
        language = (
            f"Speak {profile['language']}. If the customer clearly prefers another language, "
            "switch to it."
        )
    else:
        language = (
            "Always respond in the language the customer is using. If they speak a regional "
            "language, respond only in that language; don't mix in English unless they do."
        )

    objective = profile["call_objective"]
    call_kind = "an inbound PHONE CALL (the customer called you)" if inbound else "a live outbound PHONE CALL"
    if transfer_available:
        transfer_rule = """
12. A real person from the team is available. Call `transfer_to_human` when the customer asks
    for a human, has a question you can't answer (pricing, a complaint, an existing order),
    or is clearly a hot lead ready to buy now. Pass a one-sentence summary for the person
    (who they are, what they want, what you've collected). After the tool returns, say ONE
    short line like "I'll connect you to my colleague now, please stay on the line" and say
    nothing else — don't call end_call."""
    else:
        transfer_rule = """
12. No human can take this call right now. If the customer asks for a person, say the team
    will call them back, make sure you have their name and best time to call, and finish
    with end_call (follow_up_required: true)."""
    return f"""You are {agent_name}, a friendly, professional representative of {business}, \
on {call_kind} with a customer. You talk; there is no human operator on the line.

{about}

Call objective: {objective}

Language: {language}

What the dashboard already knows about this customer (confirm, don't re-ask from scratch):
{known_block}

Checklist — information to collect during the call:
{conversation.format_fields_for_prompt(fields)}

How to work (follow strictly):
1. {greeting} Then ask your first question.
2. Ask ONE question per turn. Keep every reply to 1-2 short sentences — this is a phone call.
3. Every time the customer gives you a checklist item — even unprompted, even several at once,
   even while answering a different question — call `save_customer_info` once per item,
   with the field key and their answer in a short, normalised form (e.g. "500 LPH",
   "Bangalore", "₹1,00,000", "within 1 month"). Do this BEFORE you reply.
4. The tool tells you `next_field_to_ask`. Ask about that next. NEVER ask about anything in
   `collected` again. If you lose track (e.g. after a digression), call `get_call_progress`.
5. Use context: refer back to what they said ("You mentioned this is for a hotel…") and ask
   sensible follow-ups that depend on earlier answers.
6. If the customer declines to answer an item or doesn't know, save it as "not provided"
   and move on. If they ask a question, answer briefly from what you know about the
   business — never invent prices, stock or commitments; offer that the team will follow up.
7. If you couldn't understand what they said, apologise and ask them to repeat — don't guess.
8. If they interrupt you, stop and respond to what they said.
9. When `all_required_collected` is true, read back a short summary and ask them to confirm.
   Then thank them, explain the next step (the team will follow up), and say goodbye.
10. To finish — after your goodbye, or if they're not interested, ask you to call later,
    are the wrong person, or want to end — call `end_call` with your own judgement of
    lead_status (interested / not_interested / uncertain) and whether a follow-up is needed.
    Say your goodbye in the same turn; the line closes once you finish speaking.
11. Messages in square brackets like [SYSTEM: ...] are notes from the call system, not the
    customer. Follow them, never read them aloud.{transfer_rule}
"""


# ── Tools ─────────────────────────────────────────────────────────────────────
def _fields(tool_context: ToolContext) -> list[dict]:
    profile = tool_context.state.get("profile") or DEFAULT_RO_PROFILE
    return profile.get("fields") or DEFAULT_RO_PROFILE["fields"]


def _call_id(tool_context: ToolContext) -> uuid.UUID | None:
    raw = tool_context.state.get("call_id")
    return uuid.UUID(raw) if raw else None


async def save_customer_info(field: str, value: str, tool_context: ToolContext) -> dict[str, Any]:
    """Records one piece of information the customer has given.

    Call this every time the customer provides an item from your checklist, before replying.

    Args:
        field: The checklist field key, e.g. "ro_capacity" or "location".
        value: The customer's answer, short and normalised, e.g. "500 LPH". Use
            "not provided" if they declined to answer.

    Returns:
        What has been collected so far, what is still missing, and the next field to ask about.
    """
    fields = _fields(tool_context)
    match = conversation.match_field(fields, field)
    collected = dict(tool_context.state.get("collected") or {})
    if match is None:
        return {
            "error": f"Unknown field '{field}'. Valid keys: {[f['key'] for f in fields]}",
            **conversation.progress(fields, collected),
        }

    collected[match["key"]] = value.strip()
    tool_context.state["collected"] = collected

    call_id = _call_id(tool_context)
    if call_id is not None:
        # Local import keeps agent.py importable without a database (e.g. adk web).
        from audiocall.services import events_service, requirements_service

        try:
            collected = {**await requirements_service.save_fields(call_id, {match["key"]: value}), **collected}
        except Exception:
            logger.exception("Could not persist field %s for call %s", match["key"], call_id)
        await events_service.record(call_id, "field_collected", f"{match['label']}: {value}")

    return {
        "saved": {"key": match["key"], "label": match["label"], "value": value.strip()},
        **conversation.progress(fields, collected),
    }


async def get_call_progress(tool_context: ToolContext) -> dict[str, Any]:
    """Returns what has been collected so far, what is still missing, and the next field to ask about."""
    fields = _fields(tool_context)
    collected = dict(tool_context.state.get("collected") or {})
    call_id = _call_id(tool_context)
    if call_id is not None:
        from audiocall.services import requirements_service

        try:
            collected = {**await requirements_service.get_collected(call_id), **collected}
        except Exception:
            logger.exception("Could not load progress for call %s", call_id)
    return conversation.progress(fields, collected)


async def end_call(
    lead_status: Literal["interested", "not_interested", "uncertain"],
    follow_up_required: bool,
    reason: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Ends the phone call after your goodbye has been spoken.

    Args:
        lead_status: Your assessment: "interested", "not_interested" or "uncertain".
        follow_up_required: Whether the sales team should follow up with this customer.
        reason: Short reason the call is ending, e.g. "requirements collected",
            "customer not interested", "customer asked to call back later", "customer_silent".

    Returns:
        Confirmation; say a brief goodbye if you haven't already.
    """
    tool_context.state["end_call"] = {
        "lead_status": lead_status,
        "follow_up_required": follow_up_required,
        "reason": reason,
    }
    call_id = _call_id(tool_context)
    if call_id is not None:
        from audiocall.services import events_service

        await events_service.record(
            call_id,
            "agent_end_call",
            f"{reason} (lead: {lead_status}, follow-up: {'yes' if follow_up_required else 'no'})",
        )
    return {"status": "ending", "note": "The line will close after you finish speaking."}


async def transfer_to_human(reason: str, summary: str, tool_context: ToolContext) -> dict[str, Any]:
    """Hands the phone call over to a real person from the team.

    Use when the customer asks for a human, needs something you can't answer,
    or is ready to buy now.

    Args:
        reason: Why you're transferring, e.g. "customer asked for a human",
            "pricing question", "hot lead".
        summary: One sentence for the person taking over: who the customer is,
            what they want, and the key facts you've collected.

    Returns:
        Whether the transfer will happen. If it will, say one short "connecting
        you now" line and nothing else.
    """
    if not transfer_available(tool_context.state):
        return {
            "status": "unavailable",
            "note": "No one can take a transferred call. Offer a callback from the team instead, "
            "then finish with end_call (follow_up_required: true).",
        }
    tool_context.state["transfer"] = {"reason": reason, "summary": summary}
    call_id = _call_id(tool_context)
    if call_id is not None:
        from audiocall.services import events_service

        # The summary is read back for the whisper the person hears on pickup.
        await events_service.record(call_id, "transfer_requested", summary.strip() or reason)
    return {
        "status": "transferring",
        "note": "Say one short line telling the customer you're connecting them now. "
        "The call is handed over as soon as you finish speaking.",
    }


root_agent = Agent(
    name="calling_agent",
    model=_llm,
    description=(
        "An autonomous voice agent (outbound and inbound) that qualifies leads for a configurable "
        "business, collecting a checklist of requirements, making its own lead assessment and "
        "handing the call to a person when needed."
    ),
    instruction=build_instruction,
    tools=[save_customer_info, get_call_progress, end_call, transfer_to_human],
)
