"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ApiError } from "@/lib/apiClient";

export interface ActionMessage {
  ok: boolean;
  text: string;
}

/**
 * Runs an async action with pending state and a success/error message, and
 * sends the user to /login if the session expired. `refresh` re-renders the
 * server page afterwards (e.g. to update the setup checklist).
 */
export function useAction() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<ActionMessage | null>(null);

  function run(work: () => Promise<ActionMessage | void>, { refresh = true } = {}) {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await work();
        if (result) setMessage(result);
        if (refresh) router.refresh();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        setMessage({
          ok: false,
          text: err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
        });
      }
    });
  }

  return { run, isPending, message, setMessage };
}
