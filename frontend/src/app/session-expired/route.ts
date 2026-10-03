import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE_NAME = "audiocall_session";

/**
 * The backend rejected the session (expired, user disabled, company
 * suspended). Drop the cookie before showing /login — otherwise proxy.ts sees
 * a cookie, sends the visitor back to "/", which 401s again: a redirect loop.
 */
export function GET(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/login", request.url));
  response.cookies.delete(SESSION_COOKIE_NAME);
  return response;
}
