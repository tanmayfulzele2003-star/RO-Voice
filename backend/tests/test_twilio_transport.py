import base64
import json
import uuid

import audioop  # type: ignore[import-not-found]

from audiocall.voice.transports import TwilioTransport


class FakeWS:
    def __init__(self, messages, query=None):
        self.query_params = query or {}
        self._messages = [json.dumps(m) for m in messages]
        self.sent = []

    async def receive_text(self):
        return self._messages.pop(0)

    async def send_json(self, data):
        self.sent.append(data)


async def test_call_id_recovered_from_custom_parameters_and_audio_converted():
    call_id = uuid.uuid4()
    ulaw = audioop.lin2ulaw(b"\x10\x00" * 160, 2)  # 20 ms at 8 kHz
    ws = FakeWS(
        [
            {"event": "connected", "protocol": "Call"},
            {
                "event": "start",
                "streamSid": "MZ1",
                "start": {"callSid": "CA1", "customParameters": {"call_id": str(call_id)}},
            },
            {"event": "media", "media": {"payload": base64.b64encode(ulaw).decode()}},
            {"event": "mark", "mark": {"name": "hangup"}},
            {"event": "stop"},
        ]
    )
    t = TwilioTransport(ws)
    assert await t.wait_for_start() == call_id
    assert t.twilio_call_sid == "CA1"

    items = [i async for i in t.receive()]
    assert [i.kind for i in items] == ["audio", "mark", "hangup"]
    # 8 kHz μ-law (160 bytes) → 16 kHz PCM-16 (~640 bytes)
    assert abs(len(items[0].audio) - 640) <= 4

    await t.send_audio(b"\x00\x10" * 480)  # 20 ms at 24 kHz
    await t.send_mark("hangup")
    await t.clear()
    media, mark, clear = ws.sent
    assert media["event"] == "media" and media["streamSid"] == "MZ1"
    assert abs(len(base64.b64decode(media["media"]["payload"])) - 160) <= 2  # back to 8 kHz μ-law
    assert mark == {"event": "mark", "streamSid": "MZ1", "mark": {"name": "hangup"}}
    assert clear == {"event": "clear", "streamSid": "MZ1"}
