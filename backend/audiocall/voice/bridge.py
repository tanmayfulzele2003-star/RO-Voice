"""The live conversation engine: one customer ↔ one Gemini Live agent session.

Transport-agnostic (see transports.py) — the same engine runs real Twilio
phone calls and the browser WebRTC demo.

Per call it:
  1. loads the call's customer + business profile and starts an ADK Live
     session whose state carries them (the agent's instructions and tools read
     it — see agent.py);
  2. tells the agent to open the conversation (outbound calls: the agent
     speaks first, nobody has to say "hello");
  3. streams audio both ways, with barge-in (customer interrupts → buffered
     agent audio is dropped);
  4. persists every finished turn of the transcript;
  5. watches for silence, unrecognised speech, AI failure, the call running
     too long, and the agent's own `end_call` decision — recording each as a
     call event and reacting (nudge, apologise, hang up);
  6. on teardown, flushes pending writes, records the final status and lets
     post-call analysis run.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

import audioop  # type: ignore[import-not-found]

from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from audiocall.agent import root_agent
from audiocall.core.config import (
    INTERRUPTION_THRESHOLD,
    MAX_CALL_SECONDS,
    SILENCE_HANGUP_SECONDS,
    SILENCE_PROMPT_SECONDS,
)
from audiocall.services import calls_service, events_service, transcript_service
from audiocall.services.outcome import outcome_from_analysis
from audiocall.voice.transports import Inbound

logger = logging.getLogger(__name__)

APP_NAME = "audiocall"
session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)

HANGUP_MARK = "hangup"
# If the far end never confirms playback of the goodbye, hang up anyway.
END_CALL_FALLBACK_SECONDS = 12
# Speech-recognition failure heuristic: this much voiced audio (by RMS energy)
# with no transcription at all means the customer is talking but nothing is
# being recognised.
SPEECH_RMS_THRESHOLD = 900
UNRECOGNISED_SPEECH_MS = 5000
STT_NUDGE_COOLDOWN_SECONDS = 20


class Transport(Protocol):
    channel: str

    async def wait_for_start(self) -> uuid.UUID | None: ...
    def receive(self): ...  # AsyncIterator[Inbound]
    async def send_audio(self, pcm_24k: bytes) -> None: ...
    async def clear(self) -> None: ...
    async def send_mark(self, name: str) -> None: ...
    async def notify(self, payload: dict) -> None: ...
    async def hang_up(self) -> None: ...
    async def abort(self, message: str = ...) -> None: ...


def _system(text: str) -> types.Content:
    """A note from the call system to the agent (not customer speech)."""
    return types.Content(role="user", parts=[types.Part(text=f"[SYSTEM: {text}]")])


class CallBridge:
    def __init__(self, transport: Transport) -> None:
        self.t = transport
        self.call_id: uuid.UUID | None = None
        self.queue = LiveRequestQueue()
        self.done = asyncio.Event()
        self.pending_writes: set[asyncio.Task] = set()

        # Lifecycle flags (read at teardown)
        self.customer_spoke = False
        self.ai_error: str | None = None
        self.silence_timeout = False
        self.interruptions = 0
        self.customer_hung_up = False

        # Ending
        self.end_requested = False
        self.end_reason: str | None = None
        self.agent_assessment: dict | None = None
        self._fallback_task: asyncio.Task | None = None

        # Silence / speech-recognition tracking
        self.started_at = time.monotonic()
        self.last_activity = time.monotonic()
        self.silence_nudged = False
        self.agent_speaking = False
        self.voiced_ms_untranscribed = 0.0
        self.last_stt_nudge = 0.0

    # ── helpers ──────────────────────────────────────────────────────────────
    def _bg(self, coro) -> None:  # noqa: ANN001
        """Schedule a DB write without blocking the audio pipeline on it."""
        task = asyncio.create_task(coro)
        self.pending_writes.add(task)
        task.add_done_callback(self.pending_writes.discard)

    def _event(self, event_type: str, detail: str | None = None) -> None:
        logger.info("call %s event %s: %s", self.call_id, event_type, detail or "")
        if self.call_id is not None:
            self._bg(events_service.record(self.call_id, event_type, detail))

    def request_end(self, reason: str) -> None:
        """End the call once the agent's current speech has played out."""
        if self.end_requested:
            return
        self.end_requested = True
        self.end_reason = reason

        async def fallback() -> None:
            await asyncio.sleep(END_CALL_FALLBACK_SECONDS)
            self.done.set()

        self._fallback_task = asyncio.create_task(fallback())

    # ── main entry ───────────────────────────────────────────────────────────
    async def run(self) -> None:
        self.call_id = await self.t.wait_for_start()
        if self.call_id is None:
            logger.warning("Stream has no call_id — transcript/status will not be persisted")

        context = await calls_service.load_call_context(self.call_id) if self.call_id else None
        state: dict[str, Any] = {
            "call_id": str(self.call_id) if self.call_id else "",
            "channel": self.t.channel,
            "collected": {},
            **(context or {}),
        }
        session_id = str(uuid.uuid4())
        await session_service.create_session(
            app_name=APP_NAME, user_id="customer", session_id=session_id, state=state
        )

        if self.call_id is not None:
            self._bg(calls_service.mark_stream_started(self.call_id, datetime.now(timezone.utc)))
            self._event("stream_started", f"channel={self.t.channel}")

        # Outbound call: the agent opens the conversation.
        self.queue.send_content(
            _system(
                "The call has just connected and the customer is on the line. "
                "Start the conversation now with your greeting."
            )
        )

        tasks = [
            asyncio.create_task(self._upstream()),
            asyncio.create_task(self._downstream(session_id)),
            asyncio.create_task(self._watchdog()),
        ]
        try:
            await self.done.wait()
        finally:
            await self._teardown(tasks)

    # ── customer → agent ─────────────────────────────────────────────────────
    async def _upstream(self) -> None:
        try:
            async for item in self.t.receive():
                if item.kind == "audio":
                    self.queue.send_realtime(
                        types.Blob(mime_type="audio/pcm;rate=16000", data=item.audio)
                    )
                    self._track_voice(item)
                elif item.kind == "mark":
                    if item.name == HANGUP_MARK and self.end_requested:
                        self.done.set()
                elif item.kind == "hangup":
                    if not self.end_requested:
                        self.customer_hung_up = True
                        self._event("customer_hung_up")
                    break
        except Exception:
            logger.exception("Error receiving customer audio")
        finally:
            self.done.set()

    def _track_voice(self, item: Inbound) -> None:
        """Speech-recognition failure heuristic (see constants above)."""
        if self.agent_speaking or not item.audio:
            return
        try:
            loud = audioop.rms(item.audio, 2) > SPEECH_RMS_THRESHOLD
        except audioop.error:
            return
        if not loud:
            return
        self.voiced_ms_untranscribed += len(item.audio) / 2 / 16000 * 1000
        now = time.monotonic()
        if (
            self.voiced_ms_untranscribed > UNRECOGNISED_SPEECH_MS
            and now - self.last_stt_nudge > STT_NUDGE_COOLDOWN_SECONDS
        ):
            self.voiced_ms_untranscribed = 0
            self.last_stt_nudge = now
            self._event("speech_not_recognized", "customer audio detected but not transcribed")
            self.queue.send_content(
                _system(
                    "The customer seems to be speaking but their speech could not be "
                    "recognised. Politely say the line isn't clear and ask them to repeat."
                )
            )

    # ── agent → customer ─────────────────────────────────────────────────────
    async def _downstream(self, session_id: str) -> None:
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=["AUDIO"],
            # Speech-to-text of both sides, for the transcript.
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Tighten VAD: respond ~300 ms after the caller stops speaking
            # instead of the default ~800 ms.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=300,
                )
            ),
        )
        try:
            async for event in runner.run_live(
                user_id="customer",
                session_id=session_id,
                live_request_queue=self.queue,
                run_config=run_config,
            ):
                await self._handle_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("AI agent failure")
            self.ai_error = f"{type(exc).__name__}: {exc}"[:500]
            self._event("ai_error", self.ai_error)
            await self.t.abort()
        finally:
            self.done.set()

    async def _handle_event(self, event) -> None:  # noqa: ANN001, C901
        now = datetime.now(timezone.utc)

        # Customer speech-to-text
        if event.input_transcription and event.input_transcription.text:
            text = event.input_transcription.text
            self.last_activity = time.monotonic()
            self.silence_nudged = False
            self.voiced_ms_untranscribed = 0
            final = bool(event.input_transcription.finished)
            await self.t.notify(
                {"type": "transcript", "speaker": "customer", "text": text, "final": final}
            )
            if final and text.strip():
                self.customer_spoke = True
                if self.call_id is not None:
                    self._bg(transcript_service.append_message(self.call_id, "customer", text, now))

        # Agent speech (text of what it said)
        if event.output_transcription and event.output_transcription.text:
            text = event.output_transcription.text
            final = bool(event.output_transcription.finished)
            await self.t.notify({"type": "transcript", "speaker": "ai", "text": text, "final": final})
            if final and text.strip() and self.call_id is not None:
                self._bg(transcript_service.append_message(self.call_id, "ai", text, now))

        # Agent tool use: surface collected fields live, and honour end_call.
        for response in event.get_function_responses():
            data = response.response or {}
            if response.name == "save_customer_info" and data.get("saved"):
                await self.t.notify({"type": "field", **data["saved"]})
        for call in event.get_function_calls():
            if call.name == "end_call":
                args = dict(call.args or {})
                self.agent_assessment = args
                self.request_end(str(args.get("reason") or "agent ended call"))

        # Barge-in: the customer started talking over the agent.
        if event.interrupted:
            self.interruptions += 1
            self.agent_speaking = False
            if self.interruptions % 3 == 1:
                self._event("interruption", f"customer interrupted the agent (#{self.interruptions})")
            await self.t.clear()
            return

        if event.turn_complete:
            self.agent_speaking = False
            self.last_activity = time.monotonic()  # silence clock starts after the agent finishes
            if self.end_requested:
                # Hang up once the far end has actually played the goodbye.
                await self.t.send_mark(HANGUP_MARK)
            return

        if event.content and event.content.parts:
            for part in event.content.parts:
                blob = part.inline_data
                if blob and blob.data and (blob.mime_type or "").startswith("audio/pcm"):
                    self.agent_speaking = True
                    await self.t.send_audio(blob.data)

    # ── silence & duration watchdog ──────────────────────────────────────────
    async def _watchdog(self) -> None:
        while not self.done.is_set():
            await asyncio.sleep(1)
            if self.end_requested:
                continue
            if time.monotonic() - self.started_at > MAX_CALL_SECONDS:
                self._event("max_duration", f"call exceeded {MAX_CALL_SECONDS}s")
                self.queue.send_content(
                    _system(
                        "The call has reached its time limit. Thank the customer, say the team "
                        "will follow up, say goodbye and call end_call."
                    )
                )
                self.request_end("max_duration")
                continue
            if self.agent_speaking:
                continue
            silent_for = time.monotonic() - self.last_activity
            if silent_for > SILENCE_HANGUP_SECONDS:
                self.silence_timeout = True
                self._event("silence_timeout", f"no response for {silent_for:.0f}s")
                self.queue.send_content(
                    _system(
                        "The customer has not responded for a long time. Say a short, polite "
                        "goodbye (mention you'll try again later) and call end_call with "
                        "reason 'customer_silent'."
                    )
                )
                self.request_end("customer_silent")
            elif silent_for > SILENCE_PROMPT_SECONDS and not self.silence_nudged:
                self.silence_nudged = True
                self._event("customer_silence", f"no response for {silent_for:.0f}s")
                self.queue.send_content(
                    _system(
                        "The customer has been silent for a while. Politely check whether "
                        "they're still there and can hear you."
                    )
                )

    # ── teardown ─────────────────────────────────────────────────────────────
    async def _teardown(self, tasks: list[asyncio.Task]) -> None:
        self.queue.close()
        if self._fallback_task:
            self._fallback_task.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Persist the final state BEFORE closing the line: once the socket
        # closes, the server may cancel this handler. Shielded so that a
        # cancellation mid-write can't leave the call stuck "in_progress".
        try:
            await asyncio.shield(self._finalize())
        except asyncio.CancelledError:
            logger.warning("Call %s teardown cancelled; finalisation continues in background", self.call_id)
            raise
        finally:
            if self.ai_error is None:
                await self.t.hang_up()
        logger.info("Call %s bridge closed", self.call_id)

    async def _finalize(self) -> None:
        # Flush transcript/event writes still in flight before recording the
        # call's final state, so the persisted transcript is complete.
        if self.pending_writes:
            await asyncio.gather(*self.pending_writes, return_exceptions=True)

        if self.call_id is None:
            return

        status_override: str | None = None
        error_reason: str | None = None
        if self.ai_error:
            status_override, error_reason = "failed", "ai_error"
        elif self.silence_timeout or not self.customer_spoke:
            error_reason = "customer_silent"
        elif self.interruptions > INTERRUPTION_THRESHOLD:
            error_reason = "excessive_interruptions"
        elif self.customer_hung_up and not self.end_requested:
            error_reason = "customer_hung_up"
        if self.t.channel == "browser" and not self.ai_error:
            status_override = "completed"  # no telephony provider to report it

        if self.agent_assessment and self.customer_spoke:
            # The agent's own verdict, until post-call analysis refines it.
            await calls_service.set_outcome(
                self.call_id, outcome_from_analysis(self.agent_assessment.get("lead_status"))
            )

        ended_by = self.end_reason or ("customer_hung_up" if self.customer_hung_up else "stream closed")
        await events_service.record(self.call_id, "stream_ended", f"reason={ended_by}")
        await calls_service.mark_stream_ended(
            self.call_id,
            datetime.now(timezone.utc),
            status_override=status_override,
            error_reason=error_reason,
        )
