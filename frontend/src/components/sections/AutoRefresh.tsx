"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

const MAX_WAIT_MS = 2 * 60 * 1000;

/**
 * Re-fetches the (server-rendered) page every few seconds while `active`.
 * With `stopAfter` (an ISO time), gives up two minutes after it — e.g. stop
 * waiting for an AI summary that's never going to arrive.
 */
export function AutoRefresh({
  active,
  stopAfter,
  intervalMs = 4000,
}: {
  active: boolean;
  stopAfter?: string;
  intervalMs?: number;
}) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const deadline = stopAfter ? new Date(stopAfter).getTime() + MAX_WAIT_MS : Infinity;
    if (Date.now() > deadline) return;
    const id = setInterval(() => {
      if (Date.now() > deadline) {
        clearInterval(id);
        return;
      }
      router.refresh();
    }, intervalMs);
    return () => clearInterval(id);
  }, [active, stopAfter, intervalMs, router]);
  return null;
}
