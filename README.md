# RO Sales Voice-Agent Platform

An AI outbound-calling platform for RO (reverse-osmosis water system) sales qualification: it
places real phone calls via Twilio, has a live conversation through Google ADK + Gemini Live,
persists every call to Postgres, extracts structured requirements from the transcript after the
call ends, and exposes it all through a Next.js admin dashboard with authentication.

Built on top of the open-source [`Iamsdt/audiocall`](https://github.com/Iamsdt/audiocall)
Twilio ↔ FastAPI ↔ Google ADK audio bridge, which is kept as-is. Everything else — persistence,
transcript capture, AI extraction, the dashboard, auth, and hardening — is new. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-realtime-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Twilio](https://img.shields.io/badge/Twilio-Voice%20API-F22F46?logo=twilio&logoColor=white)](https://www.twilio.com/voice)
[![Google ADK](https://img.shields.io/badge/Google-ADK-4285F4?logo=google&logoColor=white)](https://google.github.io/adk-docs/)
[![Gemini Live](https://img.shields.io/badge/Gemini-Live%20API-1A73E8?logo=googlebard&logoColor=white)](https://ai.google.dev/)

## What it does

1. An admin creates a customer in the dashboard (name, phone, company).
2. The admin clicks **Start Call**; the backend dials the customer through Twilio and bridges the
   call to a Gemini Live voice agent running an RO sales-qualification script.
3. The agent collects structured requirements conversationally: capacity needed, location,
   budget, timeline, and any extra notes — while the raw transcript is persisted turn-by-turn.
4. When the call ends, a second (non-live) text model reads the saved transcript and extracts a
   structured summary, lead status (`interested` / `not_interested` / `uncertain`), and a
   follow-up flag.
5. The admin reviews all of this — transcript, requirements, summary, call outcome — in the
   dashboard, and can filter call history by status, lead status, date range, or customer name.

## Architecture at a glance

```mermaid
flowchart LR
    A[Caller/Callee] <--> B[Twilio Voice]
    B <--> C[FastAPI backend\naudio bridge]
    C <--> D[Google ADK + Gemini Live]
    C --> E[(PostgreSQL)]
    C -. post-call .-> F[Text model\nextraction + summary]
    F --> E
    G[Next.js dashboard] <--> C
```

Full diagram, request-path security table, and the ER diagram are in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Repository layout

```text
backend/    FastAPI app: Twilio↔ADK bridge, REST API, Postgres models, Alembic migrations
frontend/   Next.js 16 admin dashboard (App Router, TypeScript strict, Tailwind v4)
database/   Schema snapshot (schema.sql) — Alembic in backend/alembic is the source of truth
```

## Prerequisites

- Python 3.13+
- Node.js 20+
- A PostgreSQL 14+ database (managed — e.g. [Neon](https://neon.tech) or
  [Render Postgres](https://render.com/docs/databases) — or any local instance for development;
  there's no bundled Docker Compose Postgres)
- A Twilio account with a phone number (only required to place a **real** call — everything else
  runs without one)
- A Google AI Studio API key for Gemini Live (the live call always needs this — no substitute)
- Optionally, an NVIDIA NIM API key if you want the post-call summary/extraction step to run
  against NVIDIA instead of Gemini (see [Customizing the agent](#customizing-the-agent))

## Setup — zero to a placed test call

### 1. Database

```bash
cd backend
cp .env.example .env
```

Fill in `.env`:
- `DATABASE_URL` — your Postgres connection string (`postgresql+asyncpg://user:pass@host:5432/db`)
- `SESSION_SECRET` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- Leave `TWILIO_*` and `GOOGLE_API_KEY` for step 4 if you don't have real credentials yet — the
  dashboard, database, and auth all work without them; only placing a real call needs them.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
python -m alembic upgrade head
python scripts/create_admin.py <username> <password>
```

### 2. Backend

```bash
python -m audiocall.main
# or: uvicorn audiocall.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000/health` — should return `{"status": "ok"}`.

> `--reload` occasionally serves stale code after a file save without actually restarting the
> worker process. If a change doesn't seem to take effect, kill and restart the process manually
> rather than trusting the auto-reload.

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local   # NEXT_PUBLIC_API_URL should point at your backend
npm install
npm run dev
```

Visit `http://localhost:3000` (falls back to `3001` if `3000` is taken), sign in with the admin
user you created, and add a customer.

### 4. Place a real call (needs Twilio + Gemini credentials)

Twilio needs a public URL to reach your backend. For local development, use ngrok (or
`npx localtunnel --port 8000` if you don't want to sign up for anything):

```bash
ngrok http 8000
```

Set in `backend/.env`:
```bash
SERVER_HOST=abc123.ngrok-free.app   # no https:// prefix
USE_TLS=true
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
GOOGLE_API_KEY=...
```

Restart the backend, then click **Start Call** on a customer in the dashboard (or
`POST /api/calls` with `{"customer_id": "..."}` while logged in). The callee's phone rings, and
once answered, is bridged to the live AI agent. After the call ends, refresh the call's detail
page — the transcript, requirements, and AI summary appear once post-call analysis finishes
(usually a few seconds).

> **Twilio trial accounts** can only call phone numbers you've manually verified in the Console
> (Phone Numbers → Verified Caller IDs), and every call plays a "press any key to accept this
> call" disclaimer before your TwiML runs — press any key to let the call continue.

## API reference

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | none | Health check |
| `POST` | `/call` | none (see note below) | Legacy manual-test endpoint: start a call for `{"customer_id": ...}` |
| `POST` | `/voice` | Twilio signature | Twilio webhook; returns TwiML |
| `POST` | `/call-status` | Twilio signature | Twilio `statusCallback` webhook |
| `WS` | `/stream` | — | Bidirectional Twilio↔ADK audio bridge |
| `POST` | `/api/auth/login` | — | Admin login; sets httpOnly session cookie |
| `POST` | `/api/auth/logout` | session | Clears the session cookie |
| `GET` | `/api/auth/me` | session | "Am I logged in" check |
| `GET/POST` | `/api/customers` | session | List (paginated) / create customers |
| `GET/PATCH` | `/api/customers/{id}` | session | Fetch / edit a customer |
| `GET/POST` | `/api/calls` | session | List (filterable: `status`, `lead_status`, `date_from`, `date_to`, `customer_name`) / start a call (rate-limited) |
| `GET` | `/api/calls/{id}` | session | Call detail: metadata + transcript + requirements + summary |
| `GET` | `/api/stats/overview` | session | Dashboard totals |

`session` = a valid `audiocall_session` cookie, checked server-side on every request by the
`require_admin` FastAPI dependency — not just hidden in the frontend.

**`POST /call` is intentionally unauthenticated**, kept from the upstream project for manual curl
testing. Don't expose it publicly in a real deployment; the dashboard only ever calls the guarded
`/api/calls`.

## Security

- Every `/api/*` route except `/api/auth/login` requires a signed session cookie, verified
  server-side (`require_admin`)
- `/voice` and `/call-status` validate Twilio's `X-Twilio-Signature` header — a forged webhook
  without a valid signature gets `403` (`TWILIO_VALIDATE_SIGNATURE=true` by default; only disable
  for local dev without a real Twilio account)
- `POST /api/calls` is rate-limited per admin session (5 calls / 60s) since outbound calling is
  billable
- Passwords are bcrypt-hashed (`admin_users` table); there's no plaintext credential anywhere
- Security headers (CSP, `X-Frame-Options`, `X-Content-Type-Options`, HSTS-when-HTTPS) are set on
  both the backend (FastAPI middleware) and frontend (`next.config.ts`)
- Secrets (`SESSION_SECRET`, `TWILIO_AUTH_TOKEN`, `GOOGLE_API_KEY`) live only in backend
  environment variables — never sent to the client
- See [ARCHITECTURE.md § Known limitations](ARCHITECTURE.md#known-limitations) for what this
  does *not* cover (session revocation, multi-tenant roles, distributed rate limiting)

## Audio pipeline

Twilio and Gemini use different wire formats, so the backend converts live, in both directions,
using `audioop-lts` (a maintained replacement for the stdlib `audioop` removed in Python 3.13):

| Direction | In | Conversion | Out |
|---|---|---|---|
| Twilio → ADK | μ-law 8 kHz | `ulaw2lin` + `ratecv` 8k→16k | PCM-16 16 kHz |
| ADK → Twilio | PCM-16 24 kHz | `ratecv` 24k→8k + `lin2ulaw` | μ-law 8 kHz |

This part of the codebase is unchanged from upstream `Iamsdt/audiocall` — see
[ARCHITECTURE.md](ARCHITECTURE.md) for why it wasn't touched.

One correctness note if you're modifying `/voice`/`/stream`: Twilio's Media Stream client does not
reliably preserve query-string parameters on the WSS URL it actually connects to. Don't rely on
`?call_id=...` alone — pass it as a `<Parameter>` inside `<Stream>` too, and read it back from the
`start` event's `customParameters` on the WebSocket side as a fallback. `main.py` already does
both.

## Customizing the agent

Edit `backend/audiocall/agent.py` to change the persona, the fields it collects, or its
conversational style. Change the live model with `AGENT_MODEL` and the voice with `AGENT_VOICE`
(e.g. `Puck`, `Kore`, `Aoede`) — these always run against Gemini Live, since that's the only
real-time audio API Google ADK integrates with.

The post-call summary/extraction step is a separate, non-live text call and is pluggable via
`SUMMARY_PROVIDER` in `.env`:

- `SUMMARY_PROVIDER=gemini` (default) — uses `SUMMARY_MODEL` (e.g. `gemini-2.5-flash`) against the
  same Google API key.
- `SUMMARY_PROVIDER=nvidia` — uses `NVIDIA_API_KEY` / `NVIDIA_BASE_URL` / `NVIDIA_SUMMARY_MODEL`
  against an NVIDIA NIM endpoint (OpenAI-compatible chat completions, JSON-object mode). Useful if
  you'd rather not spend Gemini quota on the summary step. See `backend/audiocall/services/summary_service.py`.

## Deployment

Established pattern for this project: **Render** (backend + managed Postgres) + **Vercel**
(frontend).

**Render (backend):**
1. New Web Service, root directory `backend/`, build command `pip install -e .`, start command
   `python -m audiocall.main` (reads `$PORT` automatically).
2. Add a Render Postgres instance; copy its connection string into `DATABASE_URL` (as
   `postgresql+asyncpg://...` — note the `+asyncpg`, Render gives you the plain `postgresql://`
   form by default).
3. Set every variable from `backend/.env.example` in the service's environment, with real values:
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `GOOGLE_API_KEY`,
   `AGENT_MODEL`, `SUMMARY_MODEL`, `SESSION_SECRET` (freshly generated), `SERVER_HOST` (the
   Render-assigned `*.onrender.com` hostname, no scheme), `USE_TLS=true`,
   `FRONTEND_ORIGIN` (your Vercel URL), `TWILIO_VALIDATE_SIGNATURE=true`.
4. Run `python -m alembic upgrade head` once (Render's shell, or a one-off deploy hook) and
   `python scripts/create_admin.py <user> <pass>` to create the admin login.
5. In the Twilio Console, set the phone number's voice webhook to
   `https://<your-render-host>/voice` (`HTTP POST`) and, if you want call-status tracking, add
   `https://<your-render-host>/call-status` as the status callback.

**Vercel (frontend):**
1. Import `frontend/` as the project root.
2. Set `NEXT_PUBLIC_API_URL` to your Render backend's public URL.
3. Deploy. `next.config.ts`'s CSP already scopes `connect-src` to that same origin.

## Known limitations

Documented in full, with reasoning, in
[ARCHITECTURE.md § Known limitations](ARCHITECTURE.md#known-limitations) — summary: single admin
user with no role model, in-memory (non-distributed) rate limiter, no session revocation short of
rotating the signing secret, and no automated test suite (verification has been manual, end-to-end,
against real Twilio + Gemini calls).

## Further reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — full system design, data flow, ER diagram, security model
- [database/README.md](database/README.md) — schema notes
