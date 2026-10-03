/**
 * The backend no longer accepts this session (expired, user disabled, company
 * suspended). A full page load through /session-expired clears the cookie
 * and lands on /login; a client-side router.push wouldn't run the route
 * handler that deletes the cookie, and proxy.ts would bounce /login back to
 * "/" while the stale cookie is still there.
 */
export function endSession(): void {
  window.location.assign(new URL("/session-expired", window.location.href).toString());
}
