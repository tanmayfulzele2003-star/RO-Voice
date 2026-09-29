import "server-only";
import { cookies } from "next/headers";
import { makeApiClient } from "@/lib/apiClient";

/**
 * API client for Server Components. Forwards the visiting browser's cookies
 * (including the httpOnly session cookie) to the backend explicitly, since a
 * server-side `fetch` doesn't have a browser cookie jar to draw from.
 */
export async function getServerApiClient() {
  const cookieStore = await cookies();
  // NOT cookieStore.toString(): it percent-encodes each cookie's value
  // (RequestCookies' serialization runs values through encodeURIComponent),
  // which corrupts our session token before the backend ever sees it since
  // HTTP cookie values aren't supposed to be URL-encoded. Building the
  // header from the raw `.value` of each cookie avoids that.
  const cookieHeader = cookieStore
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
  return makeApiClient(cookieHeader);
}
