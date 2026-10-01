"""Audio transports: how customer audio gets in and agent audio gets out.

The conversation engine (bridge.py) only speaks PCM-16 — 16 kHz in, 24 kHz
out, which is what Gemini Live uses. Each transport adapts one channel:

* `TwilioTransport` — a Twilio bidirectional Media Stream (real phone call).
  μ-law 8 kHz on the wire, converted in both directions.
* `BrowserTransport` — the dashboard's WebRTC microphone demo. The browser
  already captures 16 kHz PCM-16 and plays 24 kHz PCM-16, so no conversion.

Both support "marks": a named marker queued after the agent's audio that the
far end echoes back once playback reaches it. The bridge uses that to hang
up only after the goodbye has actually been heard.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

# audioop-lts is a drop-in replacement for the stdlib `audioop` module that was
# removed in Python 3.13.  Install it with: pip install audioop-lts
import audioop  # type: ignore[import-not-found]

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

APOLOGY = (
    "Sorry, we're having a technical problem on our side. "
    "Our team will call you back shortly. Goodbye."
)


@dataclass
class Inbound:
    """One thing received from the customer's side."""

    kind: str  # "audio" | "mark" | "hangup"
    audio: bytes = b""  # PCM-16 16 kHz mono, for kind == "audio"
    name: str = ""  # mark name, for kind == "mark"


class TwilioTransport:
    channel = "phone"

    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.stream_sid: str | None = None
        self.twilio_call_sid: str | None = None
        self.remote_ended = False  # Twilio stopped the stream (customer hung up)
        self._ratecv_in: tuple | None = None  # 8 kHz → 16 kHz converter state
        self._ratecv_out: tuple | None = None  # 24 kHz → 8 kHz converter state

    async def wait_for_start(self) -> uuid.UUID | None:
        """Consume Twilio's `connected`/`start` handshake; return our call_id.

        Twilio's Media Stream client doesn't reliably preserve the query
        string on the WSS URL it connects to, so the call_id is also passed as
        a <Parameter> in the TwiML and read back from `customParameters`.
        """
        raw_id = self.ws.query_params.get("call_id")
        while True:
            msg = json.loads(await self.ws.receive_text())
            event = msg.get("event")
            if event == "connected":
                logger.info("Twilio Media Stream connected (protocol=%s)", msg.get("protocol"))
            elif event == "start":
                start = msg.get("start", {})
                self.stream_sid = msg.get("streamSid") or start.get("streamSid")
                self.twilio_call_sid = start.get("callSid")
                raw_id = raw_id or start.get("customParameters", {}).get("call_id")
                logger.info(
                    "Media Stream started: streamSid=%s callSid=%s",
                    self.stream_sid,
                    self.twilio_call_sid,
                )
                break
            elif event == "stop":
                return None
        try:
            return uuid.UUID(raw_id) if raw_id else None
        except ValueError:
            return None

    async def receive(self) -> AsyncIterator[Inbound]:
        try:
            while True:
                msg = json.loads(await self.ws.receive_text())
                event = msg.get("event")
                if event == "media":
                    # Decode base64 → μ-law → PCM-16 8 kHz → resample to 16 kHz.
                    ulaw = base64.b64decode(msg["media"]["payload"])
                    pcm_8k = audioop.ulaw2lin(ulaw, 2)
                    pcm_16k, self._ratecv_in = audioop.ratecv(
                        pcm_8k, 2, 1, 8000, 16000, self._ratecv_in
                    )
                    yield Inbound("audio", audio=pcm_16k)
                elif event == "mark":
                    yield Inbound("mark", name=msg.get("mark", {}).get("name", ""))
                elif event == "dtmf":
                    logger.info("DTMF digit: %s", msg.get("dtmf", {}).get("digit", "?"))
                elif event == "stop":
                    logger.info("Media Stream stopped by Twilio")
                    self.remote_ended = True
                    yield Inbound("hangup")
                    return
        except WebSocketDisconnect:
            logger.info("Twilio WebSocket disconnected")
            self.remote_ended = True
            yield Inbound("hangup")

    async def send_audio(self, pcm_24k: bytes) -> None:
        if not self.stream_sid:
            return
        # Resample 24 kHz → 8 kHz, PCM-16 → μ-law, base64 for the JSON frame.
        pcm_8k, self._ratecv_out = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, self._ratecv_out)
        payload = base64.b64encode(audioop.lin2ulaw(pcm_8k, 2)).decode()
        await self.ws.send_json(
            {"event": "media", "streamSid": self.stream_sid, "media": {"payload": payload}}
        )

    async def clear(self) -> None:
        """Barge-in: drop audio Twilio has buffered but not yet played, and
        reset the resampler so the next response starts clean."""
        self._ratecv_out = None
        if self.stream_sid:
            await self.ws.send_json({"event": "clear", "streamSid": self.stream_sid})

    async def send_mark(self, name: str) -> None:
        if self.stream_sid:
            await self.ws.send_json(
                {"event": "mark", "streamSid": self.stream_sid, "mark": {"name": name}}
            )

    async def notify(self, payload: dict) -> None:
        """UI events (live transcript etc.) — only the browser has a UI."""

    async def hang_up(self) -> None:
        # Closing a <Connect><Stream> socket makes Twilio continue the TwiML;
        # there's nothing after <Connect>, so the call ends. The REST hang-up
        # is belt-and-braces in case the socket close is slow to propagate.
        from audiocall.services import calls_service

        await self._close()
        if self.twilio_call_sid and not self.remote_ended:
            await calls_service.hang_up_phone_call(self.twilio_call_sid)

    async def abort(self, message: str = APOLOGY) -> None:
        """System failure: tell the customer, then end the call — never leave
        them in dead air."""
        from audiocall.services import calls_service

        if self.twilio_call_sid:
            # Redirecting the live call to new TwiML also ends the stream.
            await calls_service.hang_up_phone_call(self.twilio_call_sid, apology=message)
        await self._close()

    async def _close(self) -> None:
        try:
            await self.ws.close()
        except Exception:  # already closed
            pass


class BrowserTransport:
    """Browser microphone demo channel (dashboard → /browser-stream).

    Protocol:
      browser → server: binary frames = PCM-16 LE mono 16 kHz;
                        JSON {"type": "mark", "name"} once playback reaches a mark,
                        JSON {"type": "hangup"} when the user ends the call.
      server → browser: binary frames = PCM-16 LE mono 24 kHz;
                        JSON {"type": "clear" | "mark" | "transcript" | "field" |
                              "ended" | "error", ...}.
    """

    channel = "browser"

    def __init__(self, websocket: WebSocket, call_id: uuid.UUID) -> None:
        self.ws = websocket
        self.call_id = call_id
        self._closed = False

    async def wait_for_start(self) -> uuid.UUID | None:
        return self.call_id

    async def receive(self) -> AsyncIterator[Inbound]:
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    yield Inbound("hangup")
                    return
                if message.get("bytes"):
                    yield Inbound("audio", audio=message["bytes"])
                elif message.get("text"):
                    try:
                        data = json.loads(message["text"])
                    except ValueError:
                        continue
                    if data.get("type") == "mark":
                        yield Inbound("mark", name=str(data.get("name", "")))
                    elif data.get("type") == "hangup":
                        yield Inbound("hangup")
                        return
        except WebSocketDisconnect:
            yield Inbound("hangup")

    async def send_audio(self, pcm_24k: bytes) -> None:
        await self._send(bytes_=pcm_24k)

    async def clear(self) -> None:
        await self._send(json_={"type": "clear"})

    async def send_mark(self, name: str) -> None:
        await self._send(json_={"type": "mark", "name": name})

    async def notify(self, payload: dict) -> None:
        await self._send(json_=payload)

    async def hang_up(self) -> None:
        await self._send(json_={"type": "ended"})
        await self._close()

    async def abort(self, message: str = APOLOGY) -> None:
        await self._send(json_={"type": "error", "message": message})
        await self._close()

    async def _send(self, *, bytes_: bytes | None = None, json_: dict | None = None) -> None:
        if self._closed:
            return
        try:
            if bytes_ is not None:
                await self.ws.send_bytes(bytes_)
            else:
                await self.ws.send_json(json_)
        except Exception:
            self._closed = True

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.ws.close()
        except Exception:
            pass
