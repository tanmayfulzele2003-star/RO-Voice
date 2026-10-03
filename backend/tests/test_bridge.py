"""Simulated calls through the conversation engine (voice/bridge.py).

Gemini Live and the phone line are faked; everything between them — turn
persistence, live field capture, barge-in, the agent's end_call → hang up
after playback, silence handling, AI-failure handling — is the real code.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from audiocall.voice import bridge as bridge_mod
from audiocall.voice.transports import Inbound

CALL_ID = uuid.uuid4()
SILENT_AUDIO = b"\x00\x00" * 320  # 20 ms of silence at 16 kHz


def ev(**kw):
    """A fake ADK event."""
    calls = kw.pop("calls", [])
    responses = kw.pop("responses", [])
    base = dict(
        input_transcription=None,
        output_transcription=None,
        interrupted=False,
        turn_complete=False,
        content=None,
    )
    base.update(kw)
    return SimpleNamespace(
        **base,
        get_function_calls=lambda: calls,
        get_function_responses=lambda: responses,
    )


def said(text, who="ai"):
    t = SimpleNamespace(text=text, finished=True)
    return ev(output_transcription=t) if who == "ai" else ev(input_transcription=t)


def audio(data=b"\x01\x02" * 100):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type="audio/pcm;rate=24000"))
    return ev(content=SimpleNamespace(parts=[part]))


class FakeTransport:
    channel = "browser"

    def __init__(self, customer_hangs_up_after=None):
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent_audio = []
        self.notifications = []
        self.marks = []
        self.cleared = 0
        self.hung_up = False
        self.aborted = None
        self.transferred = None
        for _ in range(5):
            self.inbound.put_nowait(Inbound("audio", audio=SILENT_AUDIO))
        if customer_hangs_up_after is not None:
            asyncio.get_event_loop().call_later(
                customer_hangs_up_after, self.inbound.put_nowait, Inbound("hangup")
            )

    async def wait_for_start(self):
        return CALL_ID

    async def receive(self):
        while True:
            item = await self.inbound.get()
            yield item
            if item.kind == "hangup":
                return

    async def send_audio(self, pcm):
        self.sent_audio.append(pcm)

    async def clear(self):
        self.cleared += 1

    async def send_mark(self, name):
        self.marks.append(name)
        # The far end confirms playback reached the mark.
        self.inbound.put_nowait(Inbound("mark", name=name))

    async def notify(self, payload):
        self.notifications.append(payload)

    async def hang_up(self):
        self.hung_up = True

    async def abort(self, message="sorry"):
        self.aborted = message

    async def transfer(self, twiml):
        self.transferred = twiml
        return True


class FakeRunner:
    def __init__(self, script, fail_with=None):
        self.script = script
        self.fail_with = fail_with
        self.sent_content = []

    async def run_live(self, *, user_id, session_id, live_request_queue, run_config):
        self.queue = live_request_queue
        for item in self.script:
            await asyncio.sleep(0.01)
            yield item
        if self.fail_with:
            raise self.fail_with
        await asyncio.Event().wait()  # live session stays open until cancelled


@pytest.fixture
def record(monkeypatch):
    log = {"messages": [], "events": [], "ended": None, "outcome": None, "started": False}

    async def load_call_context(call_id):
        return {"customer": {"name": "Rahul Kumar"}, "profile": {"name": "AquaPure", "fields": []}}

    async def mark_stream_started(call_id, ts):
        log["started"] = True

    async def mark_stream_ended(call_id, ts, status_override=None, error_reason=None, transferred_to=None):
        log["ended"] = {"status_override": status_override, "error_reason": error_reason}
        log["transferred_to"] = transferred_to

    async def record_agent_assessment(call_id, lead_status, follow_up):
        log["outcome"] = (lead_status, follow_up)

    async def save_fields(call_id, fields):
        log["prefilled"] = fields

    async def append_message(call_id, speaker, message, ts):
        log["messages"].append((speaker, message))

    async def record_event(call_id, event_type, detail=None):
        log["events"].append(event_type)

    cs = bridge_mod.calls_service
    monkeypatch.setattr(cs, "load_call_context", load_call_context)
    monkeypatch.setattr(cs, "mark_stream_started", mark_stream_started)
    monkeypatch.setattr(cs, "mark_stream_ended", mark_stream_ended)
    monkeypatch.setattr(cs, "record_agent_assessment", record_agent_assessment)
    monkeypatch.setattr(bridge_mod.requirements_service, "save_fields", save_fields)
    monkeypatch.setattr(bridge_mod.transcript_service, "append_message", append_message)
    monkeypatch.setattr(bridge_mod.events_service, "record", record_event)
    return log


async def run_call(monkeypatch, runner, transport, timeout=10):
    monkeypatch.setattr(bridge_mod, "runner", runner)
    await asyncio.wait_for(bridge_mod.CallBridge(transport).run(), timeout)


async def test_full_conversation_ends_after_goodbye_is_played(monkeypatch, record):
    end_call = SimpleNamespace(
        name="end_call",
        args={"lead_status": "interested", "follow_up_required": True, "reason": "requirements collected"},
    )
    saved = SimpleNamespace(
        name="save_customer_info",
        response={"saved": {"key": "ro_capacity", "label": "RO Capacity", "value": "500 LPH"}},
    )
    runner = FakeRunner(
        [
            audio(),
            said("Hi Rahul, this is Priya from AquaPure. What capacity do you need?"),
            ev(turn_complete=True),
            said("I need a 500 LPH system for my hotel.", who="customer"),
            ev(responses=[saved]),
            audio(),
            ev(interrupted=True),  # customer talks over the agent
            ev(calls=[end_call]),  # tool call first, goodbye audio after
            said("Great, thanks Rahul. Our team will follow up. Goodbye!"),
            audio(),
            ev(turn_complete=True),
        ]
    )
    transport = FakeTransport()
    await run_call(monkeypatch, runner, transport)

    # Outbound call: the bridge tells the agent to open the conversation
    # before any customer audio is forwarded.
    first = runner.queue._queue.get_nowait()
    assert first.content and "Start the conversation now" in first.content.parts[0].text
    assert record["started"]
    assert record["messages"] == [
        ("ai", "Hi Rahul, this is Priya from AquaPure. What capacity do you need?"),
        ("customer", "I need a 500 LPH system for my hotel."),
        ("ai", "Great, thanks Rahul. Our team will follow up. Goodbye!"),
    ]
    assert {"type": "field", "key": "ro_capacity", "label": "RO Capacity", "value": "500 LPH"} in transport.notifications
    assert transport.sent_audio and transport.cleared == 1
    assert transport.marks == ["hangup"] and transport.hung_up
    assert record["outcome"] == ("interested", True)
    assert record["ended"] == {"status_override": "completed", "error_reason": None}
    assert "interruption" in record["events"]


async def test_ai_failure_apologises_and_marks_call_failed(monkeypatch, record):
    runner = FakeRunner([said("Hello!")], fail_with=RuntimeError("Gemini unavailable"))
    transport = FakeTransport()
    await run_call(monkeypatch, runner, transport)

    assert transport.aborted  # customer heard an apology instead of dead air
    assert not transport.hung_up
    assert record["ended"] == {"status_override": "failed", "error_reason": "ai_error"}
    assert "ai_error" in record["events"]


async def test_customer_hang_up_is_recorded(monkeypatch, record):
    runner = FakeRunner([said("Hello Rahul!"), said("Hi, who is this?", who="customer")])
    transport = FakeTransport(customer_hangs_up_after=0.3)
    await run_call(monkeypatch, runner, transport)

    assert "customer_hung_up" in record["events"]
    assert record["ended"]["error_reason"] == "customer_hung_up"


async def test_silent_customer_is_prompted_then_call_ends(monkeypatch, record):
    monkeypatch.setattr(bridge_mod, "SILENCE_PROMPT_SECONDS", 1)
    monkeypatch.setattr(bridge_mod, "SILENCE_HANGUP_SECONDS", 2)
    monkeypatch.setattr(bridge_mod, "END_CALL_FALLBACK_SECONDS", 1)
    runner = FakeRunner([said("Hello, is this Rahul?"), ev(turn_complete=True)])
    transport = FakeTransport()
    await run_call(monkeypatch, runner, transport)

    assert record["events"].count("customer_silence") == 1
    assert "silence_timeout" in record["events"]
    assert record["ended"]["error_reason"] == "customer_silent"
    assert record["outcome"] is None  # nothing to assess — no conversation happened


async def test_known_customer_details_are_prefilled(monkeypatch, record):
    async def load_call_context(call_id):
        return {
            "collected": {"customer_name": "Rahul Kumar"},
            "customer": {"name": "Rahul Kumar"},
            "profile": {"name": "AquaPure", "fields": []},
        }

    monkeypatch.setattr(bridge_mod.calls_service, "load_call_context", load_call_context)
    runner = FakeRunner([said("Hi!")])
    await run_call(monkeypatch, runner, FakeTransport(customer_hangs_up_after=0.2))

    assert record["prefilled"] == {"customer_name": "Rahul Kumar"}
    session = list(bridge_mod.session_service.sessions["audiocall"]["customer"].values())[-1]
    assert session.state["collected"] == {"customer_name": "Rahul Kumar"}


async def test_hang_up_waits_for_goodbye_audio_after_end_call(monkeypatch, record):
    """If the model calls end_call before speaking, a turn_complete with no
    goodbye audio yet must not close the line."""
    end_call = SimpleNamespace(
        name="end_call", args={"lead_status": "uncertain", "follow_up_required": True, "reason": "call back later"}
    )
    transport = FakeTransport()
    runner = FakeRunner(
        [
            said("Is now a good time?"),
            audio(),
            ev(turn_complete=True),
            said("Call me tomorrow.", who="customer"),
            ev(calls=[end_call]),
            ev(turn_complete=True),  # no goodbye audio yet → must keep waiting
            said("Sure, we'll call you tomorrow. Bye!"),
            audio(),
            ev(turn_complete=True),
        ]
    )
    await run_call(monkeypatch, runner, transport)
    assert transport.marks == ["hangup"]  # exactly once, after the goodbye audio
    assert record["messages"][-1] == ("ai", "Sure, we'll call you tomorrow. Bye!")
    assert record["outcome"] == ("uncertain", True)


async def test_twilio_transport_skips_rest_hangup_when_customer_hung_up(monkeypatch):
    from audiocall.voice import transports

    called = []

    async def fake_hang_up(sid, apology=None):
        called.append(sid)

    from audiocall.services import calls_service

    monkeypatch.setattr(calls_service, "hang_up_phone_call", fake_hang_up)

    class WS:
        async def close(self):
            pass

    t = transports.TwilioTransport(WS())
    t.twilio_call_sid = "CA1"
    t.remote_ended = True
    await t.hang_up()
    assert called == []
    t.remote_ended = False
    await t.hang_up()
    assert called == ["CA1"]


async def test_inbound_call_agent_answers_instead_of_pitching(monkeypatch, record):
    async def load_call_context(call_id):
        return {"direction": "inbound", "customer": {}, "profile": {"name": "AquaPure", "fields": []}}

    monkeypatch.setattr(bridge_mod.calls_service, "load_call_context", load_call_context)
    runner = FakeRunner([said("Thanks for calling AquaPure, how can I help?")])
    await run_call(monkeypatch, runner, FakeTransport(customer_hangs_up_after=0.2))

    first = runner.queue._queue.get_nowait()
    assert "called in" in first.content.parts[0].text
    assert "Start the conversation now" not in first.content.parts[0].text


def _phone_transport(**kw):
    t = FakeTransport(**kw)
    t.channel = "phone"
    return t


def _transfer_context(transfer_number="+919800000001"):
    async def load_call_context(call_id):
        return {
            "direction": "outbound",
            "from_number": "+14155550100",
            "to_number": "+919876543210",
            "customer": {"name": "Rahul Kumar"},
            "profile": {"name": "AquaPure", "fields": [], "transfer_number": transfer_number},
        }

    return load_call_context


TRANSFER = SimpleNamespace(
    name="transfer_to_human",
    args={"reason": "customer asked for a human", "summary": "Rahul wants a 500 LPH quote"},
)


async def test_transfer_redirects_call_after_connecting_line_is_played(monkeypatch, record):
    monkeypatch.setattr(bridge_mod.calls_service, "load_call_context", _transfer_context())
    runner = FakeRunner(
        [
            said("Can I speak to a person?", who="customer"),
            ev(calls=[TRANSFER]),
            said("Sure, connecting you to my colleague now."),
            audio(),
            ev(turn_complete=True),
        ]
    )
    transport = _phone_transport()
    await run_call(monkeypatch, runner, transport)

    # Redirected only after the "connecting you" audio was played (mark echoed).
    assert transport.marks == ["hangup"]
    twiml = transport.transferred
    assert "<Number" in twiml and "+919800000001</Number>" in twiml
    assert 'callerId="+14155550100"' in twiml  # our outbound number, not the customer's
    assert "/transfer-status?call_id=" in twiml and "/transfer-whisper?call_id=" in twiml
    assert record["transferred_to"] == "+919800000001"
    assert record["ended"]["error_reason"] is None
    assert "transfer_started" in record["events"]


async def test_transfer_is_ignored_without_a_transfer_number(monkeypatch, record):
    monkeypatch.setattr(bridge_mod.calls_service, "load_call_context", _transfer_context(None))
    runner = FakeRunner([said("Hi!"), ev(calls=[TRANSFER])])
    transport = _phone_transport(customer_hangs_up_after=0.3)
    await run_call(monkeypatch, runner, transport)

    assert transport.transferred is None
    assert record["transferred_to"] is None


async def test_no_transfer_when_customer_already_hung_up(monkeypatch, record):
    monkeypatch.setattr(bridge_mod.calls_service, "load_call_context", _transfer_context())
    monkeypatch.setattr(bridge_mod, "END_CALL_FALLBACK_SECONDS", 5)
    runner = FakeRunner([said("Connecting you now."), ev(calls=[TRANSFER])])
    transport = _phone_transport(customer_hangs_up_after=0.3)
    await run_call(monkeypatch, runner, transport)

    assert transport.transferred is None
    assert record["transferred_to"] is None


async def test_twilio_transport_transfer_redirects_and_skips_rest_hangup(monkeypatch):
    from audiocall.services import calls_service
    from audiocall.voice import transports

    redirected, hung_up = [], []

    async def fake_redirect(sid, twiml):
        redirected.append((sid, twiml))
        return True

    async def fake_hang_up(sid, apology=None):
        hung_up.append(sid)

    monkeypatch.setattr(calls_service, "redirect_phone_call", fake_redirect)
    monkeypatch.setattr(calls_service, "hang_up_phone_call", fake_hang_up)

    class WS:
        async def close(self):
            pass

    t = transports.TwilioTransport(WS())
    t.twilio_call_sid = "CA1"
    assert await t.transfer("<Response/>")
    await t.hang_up()
    assert redirected == [("CA1", "<Response/>")]
    assert hung_up == []  # a REST hang-up would cut off the transferred call
