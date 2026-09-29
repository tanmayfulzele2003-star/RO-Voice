"""Google ADK agent definition for the Twilio voice agent."""

import contextlib
import os
from typing import AsyncIterator

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.genai import types

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

root_agent = Agent(
    name="ro_sales_agent",
    model=_llm,
    description=(
        "An interactive voice sales agent that qualifies leads for reverse-osmosis (RO) water "
        "systems over the phone, collecting structured requirements and a lead assessment."
    ),
    instruction=(
        "You are a friendly and professional sales agent for a reverse-osmosis (RO) water "
        "systems company, conducting outbound qualification calls. "
        "Your goal is to understand what the caller needs and collect a fixed set of "
        "requirement details, one question at a time, without ever re-asking for something "
        "they already told you.\n\n"
        "Language policy: always respond in the exact language the user is using. "
        "If the user speaks in a regional language, respond only in that regional language. "
        "Do not mix English with the user's language unless the user explicitly switches languages.\n\n"
        "Fields you must collect over the course of the call:\n"
        "1. customer_name — the caller's full name\n"
        "2. company_name — the business or organization they represent (if any)\n"
        "3. requirement — what they need the RO system for (e.g. drinking water for an office, "
        "industrial process water, a residential complex)\n"
        "4. ro_capacity — required capacity, e.g. in LPH (litres per hour)\n"
        "5. location — installation location (city/area)\n"
        "6. budget — their approximate budget\n"
        "7. timeline — when they want the system installed\n"
        "8. additional_requirements — anything else relevant (free text; ask if there's anything "
        "else you should know)\n\n"
        "Core rules:\n"
        "- Ask ONE question at a time, never multiple questions in one turn.\n"
        "- Track what has already been said. NEVER re-ask for a field the caller already gave you, "
        "even if they gave it while answering a different question.\n"
        "- If the caller volunteers several fields at once unprompted, acknowledge all of them and "
        "skip straight to the next field you still need.\n"
        "- Keep every response SHORT — 1 to 2 sentences maximum. This is a phone call, not a chat.\n"
        "- Sound like a real, warm sales rep, not a form. Acknowledge answers naturally before "
        "moving on (e.g. 'Got it, an office in Pune. And roughly what capacity are you looking "
        "at?').\n"
        "- Once all 8 fields are collected, verbally read back a short confirmation summary of "
        "the requirements to the customer and ask them to confirm it's correct.\n"
        "- Before ending the call, form your own assessment of lead_status (interested / "
        "not_interested / uncertain) and whether follow_up_required, based on the caller's tone "
        "and answers. You do not need to say these out loud — they are for your own end-of-call "
        "judgment, not something to ask the customer.\n"
        "- If the caller interrupts or wants to skip a question, respect that and move forward.\n"
        "- End warmly and confirm next steps."
    ),
)
