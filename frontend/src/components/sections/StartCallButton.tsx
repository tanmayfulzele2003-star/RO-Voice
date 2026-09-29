"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { CallStatusBadge } from "@/components/ui/Badge";
import { useCallStatusPolling } from "@/hooks/useCallStatusPolling";
import { ApiError, apiClient } from "@/lib/apiClient";

export function StartCallButton({ customerId }: { customerId: string }) {
  const router = useRouter();
  const [callId, setCallId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const { status, error: pollError, isPolling } = useCallStatusPolling(callId);

  async function handleClick() {
    setStartError(null);
    setIsStarting(true);
    try {
      const result = await apiClient.startCall(customerId);
      setCallId(result.call_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.push("/login");
        return;
      }
      setStartError(err instanceof ApiError ? err.message : "Failed to start call.");
    } finally {
      setIsStarting(false);
    }
  }

  const error = startError ?? pollError;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="secondary"
        onClick={handleClick}
        disabled={isStarting || isPolling}
      >
        {isStarting ? "Starting…" : callId ? "Call again" : "Start call"}
      </Button>
      {status ? <CallStatusBadge status={status} /> : null}
      {error ? (
        <span role="alert" className="text-sm text-danger">
          {error}
        </span>
      ) : null}
    </div>
  );
}
