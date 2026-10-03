import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Next.js 16 renamed the `middleware.ts` convention to `proxy.ts` (same
// mechanics, new name/export) — confirmed against this version's own bundled
// docs before writing this, since it postdates training data.

const SESSION_COOKIE_NAME = "audiocall_session";
const PUBLIC_PATHS = ["/login"];
// Reachable signed in or out: creating the first admin happens before anyone
// can sign in.
const OPEN_PATHS = ["/setup", "/join", "/session-expired"];

/**
 * Fast, presence-only redirect: this does NOT cryptographically verify the
 * session cookie (that needs SESSION_SECRET, which must never reach the
 * edge/client bundle). It just keeps a fully logged-out visitor from ever
 * seeing dashboard chrome. If the cookie exists but is stale/invalid, the
 * page's own server-side data fetch gets a 401 from the backend and redirects
 * to /login from there (see src/lib/auth.ts) — that's the real security
 * boundary, enforced by the FastAPI backend on every request regardless of
 * what this proxy does.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (OPEN_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) {
    return NextResponse.next();
  }
  const isPublicPath = PUBLIC_PATHS.some((path) => pathname.startsWith(path));
  const hasSessionCookie = request.cookies.has(SESSION_COOKIE_NAME);

  if (!isPublicPath && !hasSessionCookie) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (isPublicPath && hasSessionCookie) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)"],
};
