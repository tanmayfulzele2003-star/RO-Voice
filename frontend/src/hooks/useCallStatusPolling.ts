"use client";

import { useEffect, useState } from "react";
import { ApiError, apiClient } from "@/lib/apiClient";
import type { CallStatus } from "@/types/api";

const TERMINAL_STATUSES: CallStatus[] = ["completed", "failed", "no_answer", "disconnected"];
const POLL_INTERVAL_MS = 3000;

export function useCallStatusPolling(callId: string | null) {
  const [status, setStatus] = useState<CallStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    // No call started yet — nothing to poll. State already defaults to
    // null/false, so there's nothing to reset (callId never goes from a
    // real value back to null in how this hook is used).
    if (!callId) {
      return;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      setIsPolling(true);
      setError(null);
      try {
        const call = await apiClient.getCall(callId as string);
        if (cancelled) return;
        setStatus(call.status);
        if (TERMINAL_STATUSES.includes(call.status)) {
          setIsPolling(false);
          return;
        }
        timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to fetch call status.");
        setIsPolling(false);
      }
    }

    poll();

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [callId]);

  return { status, error, isPolling };
}
