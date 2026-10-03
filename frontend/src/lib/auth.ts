import "server-only";
import { redirect } from "next/navigation";
import { ApiError } from "@/lib/apiClient";

/**
 * Call from a Server Component's catch block. If the error is an
 * unauthenticated/expired-session 401, this clears the session cookie and
 * sends the visitor to /login (via /session-expired), and never returns (any
 * code after the call site in that branch won't run). For any other error it
 * simply returns, so the caller can fall through to its own error handling.
 */
export function redirectIfUnauthenticated(err: unknown): void {
  if (err instanceof ApiError && err.status === 401) {
    redirect("/session-expired");
  }
}
