"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { API_WS_BASE_URL, ApiError, apiClient } from "@/lib/apiClient";
import { endSession } from "@/lib/session";

/**
 * Browser (WebRTC microphone) call — the same two-way AI conversation as a
 * phone call, without a telephony provider. Useful when a free/trial calling
 * plan can't reach the customer's number.
 *
 * Audio path: mic → AudioWorklet (PCM-16 16 kHz) → WebSocket → backend →
 * Gemini Live → PCM-16 24 kHz → scheduled AudioBufferSources → speakers.
 * Protocol: see BrowserTransport in backend/audiocall/voice/transports.py.
 */

type Phase = "idle" | "connecting" | "live" | "ended" | "error";

interface Line {
  speaker: "customer" | "ai";
  text: string;
  final: boolean;
}

interface CollectedField {
  key: string;
  label: string;
  value: string;
}

const PLAYBACK_RATE = 24000;

export function BrowserCall({
  customerId,
  customerName,
  profileName,
}: {
  customerId: string;
  customerName: string;
  profileName: string;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [fields, setFields] = useState<CollectedField[]>([]);
  const [agentSpeaking, setAgentSpeaking] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playheadRef = useRef(0);
  const sourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const timersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [lines]);

  // Always release the microphone and sockets when leaving the page.
  useEffect(() => () => cleanup(), []); // eslint-disable-line react-hooks/exhaustive-deps

  function cleanup() {
    for (const timer of timersRef.current) clearTimeout(timer);
    timersRef.current.clear();
    stopPlayback();
    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;
    void captureCtxRef.current?.close().catch(() => {});
    captureCtxRef.current = null;
    void playCtxRef.current?.close().catch(() => {});
    playCtxRef.current = null;
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
  }

  function stopPlayback() {
    for (const source of sourcesRef.current) {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
    sourcesRef.current.clear();
    playheadRef.current = 0;
    setAgentSpeaking(false);
  }

  function playChunk(data: ArrayBuffer) {
    const ctx = playCtxRef.current;
    if (!ctx) return;
    const pcm = new Int16Array(data);
    const buffer = ctx.createBuffer(1, pcm.length, PLAYBACK_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 0x8000;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(playheadRef.current, ctx.currentTime + 0.02);
    source.start(startAt);
    playheadRef.current = startAt + buffer.duration;
    sourcesRef.current.add(source);
    setAgentSpeaking(true);
    source.onended = () => {
      sourcesRef.current.delete(source);
      if (sourcesRef.current.size === 0) setAgentSpeaking(false);
    };
  }

  /** Echo a mark back once everything queued before it has played. */
  function ackMarkAfterPlayback(name: string) {
    const ctx = playCtxRef.current;
    const delayMs = ctx ? Math.max(0, (playheadRef.current - ctx.currentTime) * 1000) : 0;
    const timer = setTimeout(() => {
      timersRef.current.delete(timer);
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "mark", name }));
    }, delayMs);
    timersRef.current.add(timer);
  }

  function addTranscript(speaker: Line["speaker"], text: string, final: boolean) {
    setLines((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.speaker === speaker && !last.final) {
        // Partial chunks accumulate; the final event carries the full text.
        const merged = final ? text : last.text + text;
        return [...prev.slice(0, -1), { speaker, text: merged, final }];
      }
      return [...prev, { speaker, text, final }];
    });
  }

  function handleServerMessage(message: Record<string, unknown>) {
    switch (message.type) {
      case "transcript":
        addTranscript(
          message.speaker === "customer" ? "customer" : "ai",
          String(message.text ?? ""),
          Boolean(message.final),
        );
        break;
      case "field":
        setFields((prev) => [
          ...prev.filter((f) => f.key !== message.key),
          { key: String(message.key), label: String(message.label), value: String(message.value) },
        ]);
        break;
      case "clear":
        stopPlayback(); // customer barged in
        break;
      case "mark":
        ackMarkAfterPlayback(String(message.name ?? ""));
        break;
      case "ended":
        setPhase("ended");
        cleanup();
        break;
      case "error":
        setError(String(message.message ?? "The call failed."));
        setPhase("error");
        cleanup();
        break;
    }
  }

  async function startCall() {
    setError(null);
    setLines([]);
    setFields([]);
    setPhase("connecting");

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't access a microphone here — use https:// or http://localhost.");
      setPhase("error");
      return;
    }

    // Create the audio contexts synchronously inside the click handler:
    // browsers (Safari especially) only let audio start from a user gesture.
    const playCtx = new AudioContext();
    playCtxRef.current = playCtx;
    const captureCtx = new AudioContext();
    captureCtxRef.current = captureCtx;
    void playCtx.resume();
    void captureCtx.resume();

    try {
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      micStreamRef.current = mic;

      const started = await apiClient.startBrowserCall(customerId);
      setCallId(started.call_id);

      await captureCtx.audioWorklet.addModule("/audio/pcm-capture-worklet.js");
      const micSource = captureCtx.createMediaStreamSource(mic);
      const capture = new AudioWorkletNode(captureCtx, "pcm-capture");
      // Keep the worklet pulled by the graph without playing the mic back.
      const mute = captureCtx.createGain();
      mute.gain.value = 0;
      micSource.connect(capture).connect(mute).connect(captureCtx.destination);

      // Connect to the same backend the dashboard's REST calls use (rather than
      // the server-advertised URL, which may be a public tunnel host meant for
      // Twilio) — keeps it inside the page's CSP connect-src.
      const ws = new WebSocket(
        `${API_WS_BASE_URL}/browser-stream?call_id=${encodeURIComponent(started.call_id)}&token=${encodeURIComponent(started.token)}`,
      );
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(event.data);
      };
      ws.onopen = () => setPhase("live");
      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          playChunk(event.data);
        } else {
          try {
            handleServerMessage(JSON.parse(event.data as string));
          } catch {
            // ignore malformed frames
          }
        }
      };
      ws.onclose = (event) => {
        if (wsRef.current !== ws) return; // closed by us
        setPhase((current) => (current === "live" || current === "connecting" ? "ended" : current));
        if (event.code >= 4400) {
          setError(event.reason || "The server refused the call connection.");
          setPhase("error");
        }
        cleanup();
      };
      ws.onerror = () => {
        setError("Lost connection to the call server.");
      };
    } catch (err) {
      cleanup();
      if (err instanceof ApiError && err.status === 401) {
        endSession();
        return;
      }
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setError("Microphone permission was denied. Allow microphone access and try again.");
      } else {
        setError(err instanceof ApiError || err instanceof Error ? err.message : "Could not start the call.");
      }
      setPhase("error");
    }
  }

  function hangUp() {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "hangup" }));
    setPhase("ended");
    cleanup();
  }

  const statusText: Record<Phase, string> = {
    idle: "Ready",
    connecting: "Connecting…",
    live: agentSpeaking ? "Agent is speaking — you can interrupt" : "Listening — speak naturally",
    ended: "Call ended",
    error: "Call failed",
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm text-muted-foreground">
              You play <span className="font-medium text-foreground">{customerName}</span>; the AI
              agent from <span className="font-medium text-foreground">{profileName}</span> calls you.
            </p>
            <p className="mt-1 flex items-center gap-2 text-sm font-medium text-foreground" aria-live="polite">
              <span
                aria-hidden
                className={`inline-block size-2.5 rounded-full ${
                  phase === "live" ? "animate-pulse bg-success" : phase === "error" ? "bg-danger" : "bg-muted-foreground"
                }`}
              />
              {statusText[phase]}
            </p>
          </div>
          <div className="flex gap-2">
            {phase === "live" || phase === "connecting" ? (
              <Button variant="danger" onClick={hangUp}>
                Hang up
              </Button>
            ) : (
              <Button onClick={startCall}>{phase === "idle" ? "Start browser call" : "Call again"}</Button>
            )}
          </div>
        </div>
        {error ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        ) : null}
        {callId && (phase === "ended" || phase === "error") ? (
          <p className="mt-3 text-sm">
            <Link
              href={`/calls/${callId}`}
              className="font-medium text-primary underline-offset-2 hover:underline"
            >
              View call record, transcript and AI summary →
            </Link>{" "}
            <span className="text-muted-foreground">(the summary appears a few seconds after the call)</span>
          </p>
        ) : null}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Live transcript</h2>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {phase === "idle"
                ? "Start the call and allow microphone access. The agent speaks first."
                : "Waiting for the conversation…"}
            </p>
          ) : (
            <ol className="flex max-h-[28rem] flex-col gap-3 overflow-y-auto" aria-live="polite">
              {lines.map((line, index) => (
                <li key={index} className={`flex ${line.speaker === "customer" ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[85%] rounded-lg px-4 py-2 text-sm ${
                      line.speaker === "customer"
                        ? "bg-muted text-foreground"
                        : "bg-primary text-primary-foreground"
                    } ${line.final ? "" : "opacity-70"}`}
                  >
                    <p className="mb-1 text-xs font-medium opacity-70">
                      {line.speaker === "customer" ? "You (customer)" : "AI agent"}
                    </p>
                    <p className="whitespace-pre-wrap">{line.text}</p>
                  </div>
                </li>
              ))}
              <div ref={transcriptEndRef} />
            </ol>
          )}
        </Card>
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-foreground">Collected by the agent</h2>
          {fields.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Fields appear here as the agent records them during the conversation.
            </p>
          ) : (
            <dl className="flex flex-col gap-2">
              {fields.map((field) => (
                <div key={field.key}>
                  <dt className="text-xs text-muted-foreground">{field.label}</dt>
                  <dd className="text-sm text-foreground">{field.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
      </div>
    </div>
  );
}
