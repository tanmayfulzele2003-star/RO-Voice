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
POST /voice          – Twilio voice webhook; returns TwiML <Connect><Stream>
POST /call-status    – Twilio status callback (ringing / answered / no-answer / ...)
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
from xml.sax.saxutils import quoteattr

from dotenv import load_dotenv

# ── env must be loaded BEFORE google-adk imports so that os.getenv() calls
# inside the SDK (and in agent.py) see the correct values at import time.
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from audiocall.api import api_router  # noqa: E402
from audiocall.core.config import (  # noqa: E402
    FRONTEND_ORIGIN,
    HTTP_SCHEME,
    SERVER_HOST,
    TWILIO_VALIDATE_SIGNATURE,
    WS_SCHEME,
)
from audiocall.core.security import verify_stream_token, verify_twilio_signature  # noqa: E402
from audiocall.db.session import check_connectivity  # noqa: E402
from audiocall.services import calls_service, events_service  # noqa: E402
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
    threaded through as a query param so /stream knows which row to write to.
    """
    call_id_param = request.query_params.get("call_id")
    form = await request.form()
    _verify_twilio_webhook(request, dict(form))
    twilio_call_sid = str(form.get("CallSid", ""))

    if call_id_param:
        # Outbound call: /call already created the `calls` row.
        try:
            call_id = uuid.UUID(call_id_param)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid call_id") from exc
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
        f"<Stream url={quoteattr(stream_url)}>"
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

    error_reason: str | None = None
    if our_status in ("failed", "no_answer"):
        error_reason = f"twilio_status={twilio_status}"
        sip = form.get("SipResponseCode")
        if sip:
            error_reason += f" sip={sip}"

    if twilio_call_sid:
        call = await calls_service.get_call_by_twilio_sid(twilio_call_sid)
        if call is not None:
            if our_status == "completed" and call.start_time is None:
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
