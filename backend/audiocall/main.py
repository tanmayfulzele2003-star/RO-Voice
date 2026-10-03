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
POST /call           – Initiate an outbound call via Twilio REST API (legacy/manual)
POST /voice          – Twilio voice webhook; returns TwiML <Connect><Stream>.
                       Inbound calls are routed by the dialled number (To).
POST /call-status    – Twilio status callback (ringing / answered / no-answer / ...)
POST /transfer-whisper – played to the human before a transferred call connects
POST /transfer-status  – <Dial> result of a transfer; falls back if unanswered
WS   /stream         – Twilio Media Stream ↔ agent (phone channel)
WS   /browser-stream – Browser microphone ↔ agent (WebRTC demo channel)

The conversation itself lives in audiocall/voice/bridge.py and is shared by
both channels; audiocall/voice/transports.py adapts each channel's audio.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# ── env must be loaded BEFORE google-adk imports so that os.getenv() calls
# inside the SDK (and in agent.py) see the correct values at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from audiocall import dialer  # noqa: E402
from audiocall.api import api_router  # noqa: E402
from audiocall.core.config import (  # noqa: E402
    FRONTEND_ORIGIN,
    HTTP_SCHEME,
    MAX_CONCURRENT_CALLS,
    SERVER_HOST,
    TRANSFER_RING_TIMEOUT_SECONDS,
    TWILIO_VALIDATE_SIGNATURE,
    WS_SCHEME,
)
from audiocall.core.security import verify_stream_token, verify_twilio_signature  # noqa: E402
from audiocall.db.session import check_connectivity  # noqa: E402
from audiocall.services import (  # noqa: E402
    calls_service,
    events_service,
    numbers_service,
    profiles_service,
    telephony,
)
from audiocall.voice.bridge import CallBridge  # noqa: E402
from audiocall.voice.transports import BrowserTransport, TwilioTransport  # noqa: E402

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
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail fast on boot if DATABASE_URL is unset or the database is unreachable,
    # rather than surfacing a confusing error on the first request that needs it.
    await check_connectivity()
    logger.info("Database connectivity verified")
    dialer_task = dialer.start()
    try:
        yield
    finally:
        await dialer.stop(dialer_task)


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
        logger.warning(
            "Rejected %s: invalid X-Twilio-Signature for %s — if this is a real Twilio "
            "request, SERVER_HOST/USE_TLS don't match the URL Twilio called.",
            request.url.path,
            url,
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


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
    threaded through so /stream knows which row to write to.
    """
    call_id_param = request.query_params.get("call_id")
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    twilio_call_sid = str(form.get("CallSid", ""))

    if call_id_param:
        # Outbound call: start_outbound_call already created the `calls` row.
        try:
            call_id = uuid.UUID(call_id_param)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid call_id") from exc
        if twilio_call_sid:
            await calls_service.set_twilio_sid(call_id, twilio_call_sid)
    else:
        twiml_or_call_id = await _route_inbound_call(form, twilio_call_sid)
        if isinstance(twiml_or_call_id, str):
            return Response(content=twiml_or_call_id, media_type="application/xml")
        call_id = twiml_or_call_id

    stream_url = f"{WS_SCHEME}://{SERVER_HOST}/stream?call_id={call_id}"
    logger.info("Twilio voice webhook hit; directing stream to %s", stream_url)
    return Response(
        content=telephony.stream_twiml(stream_url, call_id), media_type="application/xml"
    )


async def _route_inbound_call(form, twilio_call_sid: str) -> uuid.UUID | str:  # noqa: ANN001
    """Inbound call: nothing created a `calls` row yet. Route by the number
    that was dialled (To) and return the new call_id — or TwiML to answer
    with directly (number switched off, every line busy)."""
    from_number = str(form.get("From", ""))
    to_number = str(form.get("To", ""))
    number = await numbers_service.get_by_number(to_number) if to_number else None
    if number is not None and not (number.is_active and number.inbound_enabled):
        logger.info("Inbound call to disabled number %s rejected", to_number)
        return telephony.say_and_hangup(telephony.NUMBER_DISABLED_MESSAGE)

    customer = await calls_service.get_or_create_customer_by_phone(from_number)
    # The business that was dialled answers; otherwise the customer's own.
    profile = await profiles_service.resolve_profile(
        (number.profile_id if number else None) or customer.profile_id
    )
    busy = await calls_service.count_active_phone_calls() >= MAX_CONCURRENT_CALLS
    call = await calls_service.create_call(
        customer.id,
        direction="inbound",
        profile_id=profile.id,
        from_number=from_number,
        to_number=to_number,
        phone_number_id=number.id if number else None,
    )
    if twilio_call_sid:
        await calls_service.set_twilio_sid(call.id, twilio_call_sid)
    logger.info(
        "Inbound call: call_id=%s  SID=%s  from=%s  to=%s  profile=%s",
        call.id,
        twilio_call_sid,
        from_number,
        to_number,
        profile.name,
    )

    if busy:
        # Every AI line is taken: go straight to a person if there is one.
        if profile.transfer_number:
            await events_service.record(
                call.id, "capacity_transfer", f"all {MAX_CONCURRENT_CALLS} lines busy"
            )
            await calls_service.mark_capacity_transfer(call.id, profile.transfer_number)
            return telephony.dial_twiml(
                profile.transfer_number,
                caller_id=to_number or None,
                timeout_seconds=TRANSFER_RING_TIMEOUT_SECONDS,
                action_url=f"{HTTP_SCHEME}://{SERVER_HOST}/transfer-status?call_id={call.id}",
                announcement="Please hold while we connect you to our team.",
            )
        await events_service.record(call.id, "capacity_busy", f"all {MAX_CONCURRENT_CALLS} lines busy")
        await calls_service.set_status(call.id, "failed", error_reason="capacity")
        return telephony.say_and_hangup(telephony.BUSY_MESSAGE)
    return call.id


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

    error_reason: str | None = None
    if our_status in ("failed", "no_answer"):
        error_reason = f"twilio_status={twilio_status}"
        sip = form.get("SipResponseCode")
        if sip:
            error_reason += f" sip={sip}"

    if twilio_call_sid:
        call = await calls_service.get_call_by_twilio_sid(twilio_call_sid)
        if call is not None:
            if (
                our_status == "completed"
                and call.start_time is None
                and call.transferred_to is None  # went straight to a person
                and call.error_reason != "capacity"  # answered with "lines busy"
            ):
                # Answered, but our audio stream never connected: the customer
                # never heard the agent. Usual causes: Twilio trial disclaimer
                # ("press any key") not answered, or /voice//stream unreachable.
                our_status = "failed"
                error_reason = "answered_but_stream_never_connected"
            await events_service.record(
                call.id,
                "call_status",
                f"twilio={twilio_status}"
                + (f" duration={form.get('CallDuration')}s" if form.get("CallDuration") else "")
                + (f" ({error_reason})" if error_reason else ""),
            )
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
# Human transfer webhooks
# ---------------------------------------------------------------------------
def _call_id_param(request: Request) -> uuid.UUID:
    try:
        return uuid.UUID(request.query_params.get("call_id", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid call_id") from exc


@app.post("/transfer-whisper")
async def transfer_whisper_webhook(request: Request) -> Response:
    """Played only to the person taking a transferred call, when they pick
    up and before the customer is connected: who's calling and why."""
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    name, summary = await calls_service.transfer_context(_call_id_param(request))
    return Response(content=telephony.whisper_twiml(name, summary), media_type="application/xml")


@app.post("/transfer-status")
async def transfer_status_webhook(request: Request) -> Response:
    """The <Dial> to a person has ended. Answered: the conversation happened,
    hang up. Not answered: apologise, promise a callback, and record it."""
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    call_id = _call_id_param(request)
    dial_status = str(form.get("DialCallStatus", ""))
    if dial_status in ("completed", "answered"):
        duration = form.get("DialCallDuration")
        await events_service.record(
            call_id, "transfer_answered", f"talked to a person for {duration}s" if duration else None
        )
        return Response(content=telephony.hangup(), media_type="application/xml")

    await events_service.record(call_id, "transfer_failed", f"dial status: {dial_status or 'unknown'}")
    await calls_service.set_outcome(call_id, "callback")
    return Response(
        content=telephony.say_and_hangup(telephony.TRANSFER_FAILED_MESSAGE),
        media_type="application/xml",
    )


# ---------------------------------------------------------------------------
# WS /stream  – Twilio bidirectional Media Stream ↔ agent
# ---------------------------------------------------------------------------
@app.websocket("/stream")
async def stream_websocket(websocket: WebSocket) -> None:
    """Phone channel. Twilio sends μ-law 8 kHz; the transport converts to and
    from the PCM-16 Gemini Live uses (16 kHz in, 24 kHz out)."""
    await websocket.accept()
    logger.info("Twilio WebSocket connection accepted")
    await CallBridge(TwilioTransport(websocket)).run()


# ---------------------------------------------------------------------------
# WS /browser-stream  – browser microphone ↔ agent (WebRTC demo channel)
# ---------------------------------------------------------------------------
@app.websocket("/browser-stream")
async def browser_stream_websocket(websocket: WebSocket) -> None:
    """Browser channel, for demos without a telephony provider (e.g. Twilio
    trial restrictions). Authorised by the short-lived token returned from
    `POST /api/calls/browser`, and only for a call that hasn't started yet."""
    await websocket.accept()
    try:
        call_id = uuid.UUID(websocket.query_params.get("call_id", ""))
    except ValueError:
        await websocket.close(code=4400, reason="invalid call_id")
        return
    if not verify_stream_token(websocket.query_params.get("token", ""), call_id):
        await websocket.close(code=4401, reason="invalid or expired token")
        return
    call = await calls_service.get_call(call_id)
    if call is None or call.channel != "browser" or call.status != "queued":
        await websocket.close(code=4409, reason="call not available")
        return
    await CallBridge(BrowserTransport(websocket, call_id)).run()


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
