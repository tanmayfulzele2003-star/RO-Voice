"""
Twilio + Google ADK Voice Agent server.

Architecture
============
Phone caller → Twilio → WebSocket (μ-law / 8 kHz) → this server
                                                          ↓  ↑  (audio conversion)
                                              Google ADK (PCM-16 / 16 kHz in,
                                                           PCM-16 / 24 kHz out)

Audio conversion pipeline
--------------------------
Inbound  (Twilio → ADK) :  μ-law 8 kHz  →  PCM-16 16 kHz
Outbound (ADK → Twilio) :  PCM-16 24 kHz →  μ-law 8 kHz

Endpoints
---------
POST /call   – Initiate an outbound call via Twilio REST API
POST /voice  – Twilio voice webhook; returns TwiML <Connect><Stream>
WS   /stream – Bidirectional Twilio Media Stream ↔ ADK bridge
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# audioop-lts is a drop-in replacement for the stdlib `audioop` module that was
# removed in Python 3.13.  Install it with: pip install audioop-lts
import audioop  # type: ignore[import-not-found]

from dotenv import load_dotenv

# ── env must be loaded BEFORE google-adk imports so that os.getenv() calls
# inside the SDK (and in agent.py) see the correct values at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from audiocall.agent import root_agent  # noqa: E402
from audiocall.api import api_router  # noqa: E402
from audiocall.core.config import (  # noqa: E402
    FRONTEND_ORIGIN,
    HTTP_SCHEME,
    INTERRUPTION_THRESHOLD,
    SERVER_HOST,
    SILENCE_WARNING_SECONDS,
    TWILIO_VALIDATE_SIGNATURE,
    WS_SCHEME,
)
from audiocall.core.security import verify_twilio_signature  # noqa: E402
from audiocall.db.session import check_connectivity  # noqa: E402
from audiocall.services import calls_service, transcript_service  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress the noisy "1000 None" WebSocket Normal Closure log that ADK emits
# at the end of every call — it's not an application error, just the stream
# closing cleanly, but ADK logs it at ERROR level.
logging.getLogger("google_adk.google.adk.flows.llm_flows.base_llm_flow").setLevel(
    logging.CRITICAL
)

# ---------------------------------------------------------------------------
# Configuration (env-derived config + Twilio client live in core/config.py so
# service modules and API routes can reuse them without importing main.py)
# ---------------------------------------------------------------------------
# Phase 1: Application-level objects (created once at startup)
# ---------------------------------------------------------------------------
APP_NAME = "audiocall"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on boot if DATABASE_URL is unset or the database is unreachable,
    # rather than surfacing a confusing error on the first request that needs it.
    await check_connectivity()
    logger.info("Database connectivity verified")
    yield


app = FastAPI(title="Twilio + Google ADK Voice Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,  # required so the browser sends the session cookie cross-origin
    allow_methods=["*"],
    allow_headers=["*"],
)


_DOCS_PATHS = {"/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json"}


@app.middleware("http")
async def security_headers(request: Request, call_next):  # noqa: ANN001
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    # The interactive API docs pull their JS/CSS from a CDN — a strict CSP
    # would break them, so only apply it to the actual JSON API surface.
    if request.url.path not in _DOCS_PATHS:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if HTTP_SCHEME == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(api_router)


def _verify_twilio_webhook(request: Request, form: dict) -> None:
    """Raises 403 unless the request carries a valid Twilio signature.

    Reconstructs the URL from our own known scheme/host config rather than
    trusting `request.url` — behind a proxy/tunnel (ngrok), `request.url`
    can report the wrong scheme, which would make a genuine Twilio request
    fail signature validation.
    """
    if not TWILIO_VALIDATE_SIGNATURE:
        return
    signature = request.headers.get("X-Twilio-Signature", "")
    url = f"{HTTP_SCHEME}://{SERVER_HOST}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"
    if not verify_twilio_signature(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

session_service = InMemorySessionService()

runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /call  – initiate an outbound call
# ---------------------------------------------------------------------------
class CallRequest(BaseModel):
    customer_id: uuid.UUID


@app.post("/call")
async def make_call(payload: CallRequest) -> dict:
    """
    Initiate an outbound Twilio call that connects an existing customer to the
    AI agent.

    Request body (JSON):
        {
            "customer_id": "5b1e...-uuid"
        }

    Returns:
        {
            "call_id": "...",      // our `calls.id`
            "call_sid": "CA...",   // Twilio's call SID
            "status": "queued"
        }
    """
    try:
        call = await calls_service.start_outbound_call(payload.customer_id)
    except calls_service.CustomerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except calls_service.TwilioCallFailed as exc:
        raise HTTPException(
            status_code=502, detail=f"Twilio could not place the call: {exc}"
        ) from exc

    return {
        "call_id": str(call.id),
        "call_sid": call.twilio_call_sid,
        "status": call.status,
    }


# ---------------------------------------------------------------------------
# POST /voice  – Twilio voice webhook (returns TwiML)
# ---------------------------------------------------------------------------
@app.post("/voice")
async def voice_webhook(request: Request) -> Response:
    """
    Called by Twilio when the call is answered (outbound) or received
    (inbound). Returns TwiML that instructs Twilio to open a bidirectional
    media stream to our /stream WebSocket endpoint, with our `calls.id`
    threaded through as a query param so /stream knows which row to write to.
    """
    call_id_param = request.query_params.get("call_id")
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    twilio_call_sid = str(form.get("CallSid", ""))

    if call_id_param:
        # Outbound call: /call already created the `calls` row.
        call_id = uuid.UUID(call_id_param)
        if twilio_call_sid:
            await calls_service.set_twilio_sid(call_id, twilio_call_sid)
    else:
        # Inbound call: nothing created a `calls` row yet — do it now,
        # looking up (or creating) the customer by their caller ID.
        from_number = str(form.get("From", ""))
        customer = await calls_service.get_or_create_customer_by_phone(from_number)
        call = await calls_service.create_call(customer.id, direction="inbound")
        call_id = call.id
        if twilio_call_sid:
            await calls_service.set_twilio_sid(call_id, twilio_call_sid)
        logger.info(
            "Inbound call: call_id=%s  SID=%s  from=%s",
            call_id,
            twilio_call_sid,
            from_number,
        )

    stream_url = f"{WS_SCHEME}://{SERVER_HOST}/stream?call_id={call_id}"

    # Twilio's Media Stream client doesn't reliably preserve the query string
    # on the WSS URL when it opens the actual connection (observed directly:
    # the URL logged below has ?call_id=..., but /stream's query_params come
    # back empty on the real Twilio-originated socket). <Parameter> is the
    # documented reliable channel — it's echoed back verbatim in the "start"
    # event's customParameters, so /stream falls back to reading it from
    # there when the query param didn't make it through.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Connect>"
        f'<Stream url="{stream_url}">'
        f'<Parameter name="call_id" value="{call_id}"/>'
        "</Stream>"
        "</Connect>"
        "</Response>"
    )
    logger.info("Twilio voice webhook hit; directing stream to %s", stream_url)
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# POST /call-status  – Twilio statusCallback webhook
# ---------------------------------------------------------------------------
@app.post("/call-status")
async def call_status_webhook(request: Request) -> Response:
    """
    Called by Twilio as the call progresses (per `status_callback_event` on
    `calls.create`). Updates the matching `calls` row's lifecycle status.
    """
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    twilio_call_sid = str(form.get("CallSid", ""))
    twilio_status = str(form.get("CallStatus", ""))
    our_status = calls_service.map_twilio_status(twilio_status)

    error_reason = f"twilio_status={twilio_status}" if our_status == "failed" else None

    if twilio_call_sid:
        await calls_service.set_status_by_twilio_sid(
            twilio_call_sid, our_status, error_reason
        )

    logger.info(
        "Call status update: SID=%s  twilio_status=%s -> %s",
        twilio_call_sid,
        twilio_status,
        our_status,
    )
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# WS /stream  – Twilio bidirectional Media Stream ↔ Google ADK bridge
# ---------------------------------------------------------------------------
@app.websocket("/stream")
async def stream_websocket(websocket: WebSocket) -> None:
    """
    Bridge between a Twilio bidirectional Media Stream and the ADK agent.

    Twilio sends audio as μ-law encoded at 8 000 Hz.
    Google ADK (Gemini Live API) expects 16-bit PCM at 16 000 Hz.
    Google ADK returns 16-bit PCM at 24 000 Hz.
    We must convert back to μ-law 8 000 Hz before sending to Twilio.
    """
    await websocket.accept()
    logger.info("Twilio WebSocket connection accepted")

    call_id_param = websocket.query_params.get("call_id")
    call_id: uuid.UUID | None = uuid.UUID(call_id_param) if call_id_param else None
    if call_id is None:
        logger.warning(
            "No call_id on /stream connection — transcript/status will not be persisted"
        )

    # ── Phase 2: Session Initialization ─────────────────────────────────────────
    user_id = "caller"
    session_id = str(uuid.uuid4())

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    logger.info("ADK session created: %s", session_id)

    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        # Enable transcription so we can log what was said
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Tighten VAD: respond faster after the caller stops speaking.
        # END_SENSITIVITY_HIGH + 300 ms silence reduces the "wait" after each
        # utterance from the default ~800 ms down to ~300 ms.
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                silence_duration_ms=300,
            )
        ),
    )

    live_request_queue = LiveRequestQueue()

    # Per-connection mutable state (accessed via closures below)
    stream_sid: str | None = None
    ratecv_state_in: tuple | None = None  # 8 kHz → 16 kHz converter state
    ratecv_state_out: tuple | None = None  # 24 kHz → 8 kHz converter state

    # ── Call lifecycle / transcript tracking state ──────────────────────────
    customer_spoke = False
    ai_error_occurred = False
    interruption_count = 0
    last_activity_ts = time.monotonic()
    background_tasks: set[asyncio.Task] = set()

    def fire_and_forget(coro) -> None:
        """Schedule a DB write without blocking the audio pipeline on it."""
        task = asyncio.create_task(coro)
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    async def silence_watchdog() -> None:
        """Log a warning if the customer goes quiet for too long mid-call."""
        warned = False
        try:
            while True:
                await asyncio.sleep(5)
                silence_for = time.monotonic() - last_activity_ts
                if silence_for > SILENCE_WARNING_SECONDS and not warned:
                    logger.warning(
                        "No customer speech for %.0fs (session=%s)",
                        silence_for,
                        session_id,
                    )
                    warned = True
                elif silence_for <= SILENCE_WARNING_SECONDS:
                    warned = False
        except asyncio.CancelledError:
            pass

    # ── Phase 3: Concurrent bidirectional streaming ──────────────────────────────

    async def upstream_task() -> None:
        """
        Receive audio from Twilio WebSocket and forward to the ADK agent.

        Message flow:
          Twilio WS msg (μ-law / 8 kHz, base64)
            → base64 decode
            → audioop.ulaw2lin  (μ-law → 16-bit PCM)
            → audioop.ratecv    (8 kHz → 16 kHz)
            → LiveRequestQueue.send_realtime
        """
        nonlocal stream_sid, ratecv_state_in, call_id

        try:
            while True:
                raw = await websocket.receive_text()
                msg: dict = json.loads(raw)
                event_type: str = msg.get("event", "")

                if event_type == "connected":
                    logger.info(
                        "Twilio Media Stream connected (protocol=%s)",
                        msg.get("protocol"),
                    )

                elif event_type == "start":
                    stream_sid = msg.get("streamSid")
                    start_meta = msg.get("start", {})

                    if call_id is None:
                        # The query-string call_id didn't survive to this
                        # connection (observed with real Twilio calls) — fall
                        # back to the <Parameter> echoed in customParameters.
                        custom_call_id = start_meta.get("customParameters", {}).get(
                            "call_id"
                        )
                        if custom_call_id:
                            call_id = uuid.UUID(custom_call_id)
                            logger.info(
                                "Recovered call_id=%s from Stream customParameters",
                                call_id,
                            )

                    logger.info(
                        "Media Stream started: streamSid=%s  callSid=%s",
                        stream_sid,
                        start_meta.get("callSid", "unknown"),
                    )
                    if call_id is not None:
                        fire_and_forget(
                            calls_service.mark_stream_started(
                                call_id, datetime.now(timezone.utc)
                            )
                        )

                elif event_type == "media":
                    # 1. Decode base64 → raw μ-law bytes
                    payload_b64: str = msg["media"]["payload"]
                    ulaw_data: bytes = base64.b64decode(payload_b64)

                    # 2. μ-law → 16-bit PCM @ 8 000 Hz
                    pcm_8k: bytes = audioop.ulaw2lin(ulaw_data, 2)

                    # 3. Resample 8 000 Hz → 16 000 Hz (required by ADK)
                    pcm_16k, ratecv_state_in = audioop.ratecv(
                        pcm_8k, 2, 1, 8000, 16000, ratecv_state_in
                    )

                    # 4. Send to ADK Live API
                    blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm_16k)
                    live_request_queue.send_realtime(blob)

                elif event_type == "dtmf":
                    digit = msg.get("dtmf", {}).get("digit", "?")
                    logger.info("DTMF digit: %s", digit)

                elif event_type == "stop":
                    logger.info("Media Stream stopped by Twilio")
                    break

        except WebSocketDisconnect:
            logger.info("Twilio WebSocket disconnected (upstream)")
        except Exception:
            logger.exception("Unexpected error in upstream_task")
        finally:
            # Signal the ADK runner to stop
            live_request_queue.close()

    async def downstream_task() -> None:
        """
        Receive ADK agent events and forward audio back to Twilio.

        Message flow:
          runner.run_live() → Event (inline_data PCM-16 / 24 kHz)
            → audioop.ratecv   (24 kHz → 8 kHz)
            → audioop.lin2ulaw (16-bit PCM → μ-law)
            → base64 encode
            → Twilio WS media message

        Barge-in / interruption:
          When the ADK detects that the user started speaking while the agent
          was responding, it fires event.interrupted=True.  At that point we
          must tell Twilio to discard any audio already queued for playback
          (via the Twilio 'clear' message) and reset the resampler state so
          the next response starts with a clean converter.
        """
        nonlocal ratecv_state_out, customer_spoke, ai_error_occurred
        nonlocal interruption_count, last_activity_ts

        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # ── Log + persist transcriptions ───────────────────────────────
                if event.input_transcription and event.input_transcription.text:
                    logger.info(
                        "[USER]  %s%s",
                        event.input_transcription.text,
                        "" if event.input_transcription.finished else " ...",
                    )
                    last_activity_ts = time.monotonic()
                    if event.input_transcription.finished:
                        customer_spoke = True
                        if call_id is not None:
                            fire_and_forget(
                                transcript_service.append_message(
                                    call_id,
                                    "customer",
                                    event.input_transcription.text,
                                    datetime.now(timezone.utc),
                                )
                            )
                if event.output_transcription and event.output_transcription.text:
                    logger.info(
                        "[AGENT] %s%s",
                        event.output_transcription.text,
                        "" if event.output_transcription.finished else " ...",
                    )
                    if event.output_transcription.finished and call_id is not None:
                        fire_and_forget(
                            transcript_service.append_message(
                                call_id,
                                "ai",
                                event.output_transcription.text,
                                datetime.now(timezone.utc),
                            )
                        )

                # ── Barge-in: user interrupted the agent mid-response ─────────
                # The ADK / Gemini VAD detected the caller started speaking.
                # 1. Tell Twilio to throw away all buffered audio immediately.
                # 2. Reset the 24→8 kHz resampler so the next response starts
                #    with a clean state (avoids audio glitches at the boundary).
                if event.interrupted:
                    logger.info("Agent interrupted by user – sending Twilio clear")
                    interruption_count += 1
                    ratecv_state_out = None
                    if stream_sid:
                        await websocket.send_json(
                            {"event": "clear", "streamSid": stream_sid}
                        )
                    continue  # No audio to forward for this event

                if event.turn_complete:
                    logger.info("Agent turn complete")
                    # turn_complete events carry no audio; nothing to forward.
                    continue

                # ── Forward audio parts to Twilio ─────────────────────────────
                if not (event.content and event.content.parts):
                    continue

                for part in event.content.parts:
                    if not (
                        part.inline_data
                        and part.inline_data.mime_type
                        and part.inline_data.mime_type.startswith("audio/pcm")
                        and part.inline_data.data
                    ):
                        continue

                    pcm_24k: bytes = part.inline_data.data

                    # 1. Resample 24 000 Hz → 8 000 Hz (required by Twilio)
                    pcm_8k, ratecv_state_out = audioop.ratecv(
                        pcm_24k, 2, 1, 24000, 8000, ratecv_state_out
                    )

                    # 2. 16-bit PCM → μ-law
                    ulaw_data: bytes = audioop.lin2ulaw(pcm_8k, 2)

                    # 3. Base64-encode and send Media message to Twilio
                    payload_b64 = base64.b64encode(ulaw_data).decode()

                    if stream_sid:
                        await websocket.send_json(
                            {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload_b64},
                            }
                        )

        except WebSocketDisconnect:
            logger.info("Twilio WebSocket disconnected (downstream)")
        except Exception:
            logger.exception("Unexpected error in downstream_task")
            ai_error_occurred = True

    # ── Run both directions concurrently ──────────────────────────────────────────
    watchdog_task = asyncio.create_task(silence_watchdog())
    try:
        await asyncio.gather(
            upstream_task(),
            downstream_task(),
            return_exceptions=True,
        )
    finally:
        # Phase 4: Guarantee cleanup regardless of which task finished first
        live_request_queue.close()

        watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task

        # Flush any transcript/status writes still in flight before recording
        # the call's final state, so the persisted transcript is complete.
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)

        if call_id is not None:
            status_override: str | None = None
            error_reason: str | None = None
            if ai_error_occurred:
                status_override = "failed"
                error_reason = "ai_error"
            elif interruption_count > INTERRUPTION_THRESHOLD:
                error_reason = "excessive_interruptions"
            elif not customer_spoke:
                error_reason = "customer_silent"

            await calls_service.mark_stream_ended(
                call_id,
                datetime.now(timezone.utc),
                status_override=status_override,
                error_reason=error_reason,
            )

        logger.info("Session %s terminated", session_id)


# ---------------------------------------------------------------------------
# Entry point  (python -m audiocall.main)
# ---------------------------------------------------------------------------
def main() -> None:
    import uvicorn

    uvicorn.run(
        "audiocall.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("DEV_RELOAD", "")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
