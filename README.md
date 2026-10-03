# AI-Powered Two-Way Calling Agent

An AI calling agent that **places an outbound call itself, holds a natural two-way voice
conversation, keeps context, collects the information it needs, decides when the call is done, and
hands everything to an admin dashboard**. No human operator is needed. When a caller wants one,
the agent can hand the call to a real person.

* **Calling:** a real phone call through Twilio, or a **browser (WebRTC) call** from the dashboard
  when a free or trial telephony plan can't reach the number. Both channels share the same agent.
* **Several numbers, inbound and outbound:** a pool of Twilio numbers. Each can belong to a
  business, outbound calls take turns across them, and people who call a number reach that
  business's agent.
* **Many calls at once:** campaigns dial a customer list in parallel, within a concurrency limit,
  and retry unanswered calls.
* **Transfer to a person:** the agent hands the live call to a profile's transfer number with a
  spoken summary, and falls back to "we'll call you back" if nobody answers.
* **Agentic AI:** a Google ADK agent on Gemini Live with tools (`save_customer_info`,
  `get_call_progress`, `end_call`, `transfer_to_human`). It tracks a checklist, asks only for
  what's missing, and makes its own lead assessment.
* **Any business:** the agent is configured by **business profiles** (persona, products, call
  objective, fields to collect), which you edit in the dashboard. RO water systems is the seeded
  default; add a hotel, solar, insurance or clinic profile without touching code.
* **Persistence:** PostgreSQL stores every call, each conversation turn, the requirements collected
  live, an event log (errors, silences, interruptions), an AI summary and the call outcome.
* **Dashboard:** Next.js. Customers, one-click calling, live browser calls, call history with
  filters, transcript, AI summary and statistics.

Built on the open-source [`Iamsdt/audiocall`](https://github.com/Iamsdt/audiocall) Twilio ↔ FastAPI
↔ Google ADK audio bridge. The μ-law/PCM conversion comes from there; everything else is new. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

---

## Technology used (and what's free)

| Concern | Used | Free / trial tier |
|---|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic | Open source |
| Frontend | Next.js 16 (App Router, TypeScript), Tailwind CSS v4 | Open source |
| Database | PostgreSQL 14+ | Open source; Neon / Render free tiers |
| **AI model (conversation)** | **Gemini Live API**, `gemini-2.5-flash-native-audio-preview-12-2025`, via **Google ADK** (agent framework) | Google AI Studio free tier |
| **Speech-to-text** | Gemini Live **input audio transcription** (built into the Live session) | Same free tier |
| **Text-to-speech** | Gemini Live **native audio output**, prebuilt voice `Puck` (configurable) | Same free tier |
| AI model (post-call summary) | `gemini-2.5-flash` with structured JSON output, or NVIDIA NIM (`SUMMARY_PROVIDER=nvidia`) | Free tiers |
| **Calling provider** | **Twilio Programmable Voice + Media Streams** | Twilio trial account |
| Fallback calling mode | Browser microphone over WebSocket (WebRTC `getUserMedia` + AudioWorklet) | Free, no provider |

Gemini native audio is a speech-to-speech model. The six steps in the brief (capture speech, STT,
send to the agent, generate a response, TTS, play back) all happen inside one low-latency Live
session instead of three separate services. That's what keeps turn latency around 0.5 s. Both
sides of the conversation are still transcribed as text, saved turn by turn, and analysed after the
call.

---

## Setup instructions

### 1. Clone the project

```bash
git clone https://github.com/tanmayfulzele2003-star/RO-Voice.git
cd RO-Voice
```

Prerequisites: Python 3.13+, Node.js 20+, PostgreSQL 14+, a
[Google AI Studio API key](https://aistudio.google.com/apikey). A Twilio account is optional and
only needed for real phone calls.

### 2. Install dependencies

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .                                     # or: uv sync
cd ../frontend
npm install
```

### 3. Configure environment variables

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

[`.env.example`](.env.example) at the repo root lists every variable in one place. The minimum to
run the dashboard and browser calls:

| Variable | Where | Value |
|---|---|---|
| `DATABASE_URL` | backend | `postgresql+asyncpg://user:pass@localhost:5432/calling_agent` |
| `SESSION_SECRET` | backend | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_API_KEY` | backend | your AI Studio key |
| `SERVER_HOST` | backend | `localhost:8000` for local browser calls (a public host for Twilio, see step 7) |
| `USE_TLS` | backend | `false` locally, `true` behind ngrok/production |
| `NEXT_PUBLIC_API_URL` | frontend | `http://localhost:8000` |

No secrets are committed. `.env` files are git-ignored.

### 4. Set up PostgreSQL

```bash
createdb calling_agent                 # or create one on Neon / Render
cd backend
python -m alembic upgrade head         # creates tables + seeds the default RO business profile
python scripts/create_admin.py admin <password>
```

### 5. Run FastAPI

```bash
cd backend
python -m audiocall.main               # or: uvicorn audiocall.main:app --port 8000
```

`http://localhost:8000/health` returns `{"status":"ok"}`. Interactive API docs are at
`http://localhost:8000/docs`.

### 6. Run Next.js

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000` and sign in with the admin you created.

### 7. Configure the calling provider (Twilio, for real phone calls)

1. Create a free [Twilio trial account](https://www.twilio.com/try-twilio) and get a phone number
   with Voice capability.
2. **Verify the number you'll call:** Console → Phone Numbers → Manage → **Verified Caller IDs**.
   Trial accounts can only call verified numbers.
3. **Enable the destination country:** Console → Voice → Settings → **Geo permissions**. For
   example, tick India to call `+91` numbers. Most countries are off by default.
4. Expose the backend publicly so Twilio can reach it: `ngrok http 8000`.
5. In `backend/.env` set:
   ```bash
   SERVER_HOST=abc123.ngrok-free.app   # no https://, no trailing slash
   USE_TLS=true
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+1...           # your Twilio number, E.164
   ```
6. Restart the backend. You don't need to set a webhook on the Twilio number for outbound calls,
   because the backend passes the `/voice` and `/call-status` URLs to Twilio with each call.
7. **More numbers and inbound calls (optional):** in **Phone numbers**, add each Twilio number you
   own, assign it to a business profile (or leave it in the shared pool), and click **Sync to
   Twilio**. That points the number's *A call comes in* webhook at `/voice`, so people who call it
   reach the agent for that business. Outbound calls take turns across a profile's numbers.
8. **Transfer to a person (optional):** set **Transfer number** on a business profile. On phone
   calls the agent can then hand the caller to that number. The person hears a one-line summary
   first, and if nobody answers, the caller is told the team will call back.

### 8. Start a test call

1. **Business profiles:** use the default *AquaPure RO Systems*, or click **New profile** to set up
   another business.
2. **Customers → Add customer:** name, phone in international format (`+919876543210`), purpose,
   product and business profile.
3. Start the call:
   * **Phone call:** the backend dials through Twilio. Answer, and on a trial account **press any key
     after the trial message**. The agent then greets you by name and starts qualifying.
   * **Browser call:** opens a page where you play the customer through your microphone. This works
     with no Twilio account at all. Use headphones.
4. Talk naturally: *"I need a commercial RO system for my hotel, around 500 LPH."* The agent saves
   each detail as you give it (shown live in browser calls), asks only for what's missing, reads
   back a summary, says goodbye and hangs up.
5. **Calls** shows the call with status, outcome, transcript, collected requirements, the AI
   summary and an event timeline.
6. **Many calls at once:** in **Campaigns → New campaign**, pick customers, a concurrency limit and
   retries, then **Start**. The dialer calls them in parallel (within `MAX_CONCURRENT_CALLS`) and
   retries the ones who didn't answer.

### Tests

```bash
cd backend && pytest       # 32 tests: conversation logic, validation, transports, simulated calls
cd frontend && npm run lint && npm run build
```

The backend tests need no database or API keys. Gemini, Twilio and Postgres are faked, and full
calls (greeting → collection → barge-in → `end_call` → hang-up after playback, AI failure,
silence, customer hang-up) run through the real conversation engine.

---

## Architecture

```mermaid
flowchart LR
    subgraph Customer
        Phone((Phone))
        Browser((Browser mic))
    end
    Twilio[Twilio Voice<br/>Media Streams]
    subgraph Backend["FastAPI backend"]
        TT[TwilioTransport<br/>μ-law 8k ⇄ PCM]
        BT[BrowserTransport<br/>PCM 16k/24k]
        Bridge[CallBridge<br/>conversation engine:<br/>silence · barge-in ·<br/>errors · hang-up]
        Agent[ADK agent<br/>+ tools]
        API[REST /api/*]
        Post[Post-call analysis]
    end
    Gemini[Gemini Live<br/>STT + LLM + TTS]
    Text[Gemini text model]
    DB[(PostgreSQL)]
    Dash[Next.js dashboard]

    Phone <--> Twilio <-->|WS /stream| TT --> Bridge
    Browser <-->|WS /browser-stream| BT --> Bridge
    Bridge <--> Agent <--> Gemini
    Agent -->|fields collected live| DB
    Bridge -->|turns · events · status| DB
    Bridge -->|call ended| Post --> Text
    Post -->|summary · requirements · outcome| DB
    Dash <--> API <--> DB
    API -->|start call| Twilio
```

[ARCHITECTURE.md](ARCHITECTURE.md) has the detailed component diagram, the security model and
design decisions.

---

## AI workflow (agentic)

The agent isn't a "send every sentence to an LLM" loop. Each call runs one Gemini Live agent session
whose **state** carries the call's business profile, the customer record and what has been
collected so far. The agent acts through tools:

| Tool | When the agent calls it | What it does |
|---|---|---|
| `save_customer_info(field, value)` | Every time the customer gives a checklist item, even unprompted or several at once | Saves the value to Postgres immediately and returns `collected`, `still_missing`, `next_field_to_ask` and `all_required_collected` |
| `get_call_progress()` | After a digression, when unsure what's left | Returns the same progress snapshot |
| `end_call(lead_status, follow_up_required, reason)` | After its goodbye, or when the customer isn't interested or wants to stop | Records its own lead verdict. The bridge hangs up **after the goodbye has finished playing** |

How the agent keeps context and avoids repeating questions:

1. **The checklist decides, not the model's memory.** `conversation.py` computes the next missing
   field (required ones first, in profile order) and returns it with every tool call. The agent is
   told never to ask about anything in `collected`.
2. **Known facts are pre-filled.** The name and company already stored on the customer count as
   collected from the start, so the agent confirms them instead of asking again.
3. **The prompt is built per call** from the profile: persona, business description, products,
   call objective, language policy, the customer's purpose and product, and the checklist. The
   prompt also tells the agent to use context ("You mentioned this is for a hotel…").
4. **The agent speaks first.** On connect, the bridge tells the agent to greet the customer by name,
   so nobody has to say "hello" first.
5. **Post-call analysis.** When the stream ends, a separate text model reads the full transcript
   and returns structured JSON:
   * the profile's fields
   * a summary
   * customer intent
   * key requirements
   * important points
   * lead status
   * follow-up needed, with notes
   * a one-line call outcome

   This fills any gaps left by the live collection, and sets the call's **outcome**. If analysis
   fails, the agent's own `end_call` verdict is kept.

**Outcome** values: `qualified`, `not_interested`, `callback`, `incomplete`, `no_answer`,
`no_conversation`, `failed`. They come from the call status plus the AI assessment
(`services/outcome.py`).

## Calling workflow

```mermaid
sequenceDiagram
    participant A as Admin (dashboard)
    participant B as FastAPI
    participant T as Twilio
    participant C as Customer phone
    participant G as Gemini Live agent
    A->>B: POST /api/calls {customer_id}
    B->>B: validate E.164, config; create calls row (queued)
    B->>T: calls.create(to, url=/voice?call_id, statusCallback)
    T-->>B: POST /call-status (initiated → ringing)
    T->>C: rings
    C-->>T: answers
    T->>B: POST /voice (signed)
    B-->>T: TwiML <Connect><Stream url=wss://…/stream>
    T->>B: WS /stream (start event, call_id)
    B->>G: open Live session (profile + customer in state), "greet now"
    loop conversation
        G-->>B: speech audio + transcript
        B-->>T: μ-law audio → customer hears agent
        C->>T: customer speaks
        T->>B: μ-law audio
        B->>G: PCM 16 kHz
        G->>B: tool call save_customer_info → saved to DB
    end
    G->>B: end_call(lead_status, follow_up)
    B-->>T: mark after the goodbye audio
    T->>B: mark played
    B->>B: save status/duration/outcome, then close stream (call ends)
    T-->>B: POST /call-status (completed)
    B->>B: post-call AI analysis → summary, requirements, outcome
```

**Inbound calls** follow the same path from `POST /voice` onwards. The dialled number (`To`) picks
the business profile, and the agent answers ("thanks for calling…") instead of pitching.
**Campaign calls** are the same `calls.create` placed by the background dialer. **Transfers:**
when the agent calls `transfer_to_human`, the bridge waits for its "connecting you" line to play,
then redirects the live call to `<Dial>` the profile's transfer number. See
[ARCHITECTURE.md](ARCHITECTURE.md#telephony-numbers-inbound-calls-campaigns-and-human-transfer).

The **browser call** is identical except the dashboard plays Twilio's role.
`POST /api/calls/browser` returns a short-lived signed token, and the page streams 16 kHz PCM from
the microphone over `WS /browser-stream` and plays the agent's 24 kHz PCM back.

## Error handling

Every case below is handled **and recorded** in the `call_events` table, shown on the call's
detail page as a timeline.

| Situation | What happens |
|---|---|
| Invalid phone number | Rejected when the customer is saved (E.164 check in the dashboard and API). Twilio's invalid-number errors (21211/21214/21217) become `invalid_number` events |
| Calling provider failure | Twilio REST errors are translated into a clear message (unverified trial number, geo permission off, bad credentials) and shown in the dashboard. The call is marked `failed` |
| Twilio not configured / unreachable host | Refused up front with a clear message pointing to browser-call mode |
| Customer doesn't answer / busy | Twilio status callback → `no_answer` status and outcome (30 s ring timeout) |
| Answered but audio never connected | Detected (`answered_but_stream_never_connected`). Usually the trial "press any key" prompt wasn't answered, or `/voice` couldn't be reached |
| Call gets disconnected / customer hangs up | Stream `stop` → `customer_hung_up` event. Transcript and duration saved, analysis still runs |
| Customer stays silent | After 10 s the agent checks "are you still there?". After 30 s it says a polite goodbye and the call ends as `customer_silent` / `no_conversation` |
| Customer interrupts the AI | Barge-in: the agent's buffered audio is cleared at once and it answers what the customer said. Interruptions are counted and logged |
| Speech-recognition failure | Sustained speech energy with no transcription → `speech_not_recognized` event, and the agent asks the customer to repeat |
| AI / API failure | The customer hears an apology ("we'll call you back") instead of dead air, then the call ends. Status `failed`, reason `ai_error`. Post-call analysis is retried once, and its failure is logged without losing the agent's verdict |
| Call runs too long | The agent wraps up at `MAX_CALL_SECONDS` (default 600 s) |
| Every line busy | Manual calls get a 429. The campaign dialer waits for a free line. Inbound callers go straight to the transfer number, or hear "all lines are busy" (`capacity`) |
| Transfer not answered | The caller hears "we'll call you back". A `transfer_failed` event is logged and the outcome is set to `callback` |
| Campaign call unanswered / failed | Retried after `retry_delay_minutes` until `max_attempts`, then the contact is marked `failed` |

## API documentation

Interactive OpenAPI docs: **`/docs`** (Swagger) and `/redoc`. All `/api/*` routes except login
need the admin session cookie.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` · `/api/auth/logout` · `GET /api/auth/me` | Admin session (httpOnly signed cookie) |
| `GET` / `POST` | `/api/profiles` | List / create business profiles |
| `GET` / `PATCH` / `DELETE` | `/api/profiles/{id}` | Read / edit / delete a profile (the default or an in-use profile can't be deleted) |
| `GET` / `POST` | `/api/customers` | List (paginated) / create customers (`name, phone, company, purpose, product, profile_id`) |
| `GET` / `PATCH` | `/api/customers/{id}` | Read / edit a customer |
| `POST` | `/api/calls` | **Start a phone call** via Twilio (rate-limited 5/min, and capped by `MAX_CONCURRENT_CALLS`) |
| `POST` | `/api/calls/browser` | **Start a browser call**. Returns `call_id`, `token`, `stream_url` |
| `GET` | `/api/calls` | Call list. Filters: `status, lead_status, outcome, follow_up, channel, direction, campaign_id, profile_id, customer_name, date_from, date_to`, plus `limit/offset` |
| `GET` | `/api/calls/{id}` | Call detail: info, transcript, events, requirements (labelled by profile), AI summary |
| `GET` / `POST` | `/api/numbers` | List / register phone numbers (`number, label, profile_id, inbound_enabled, outbound_enabled, is_active`) |
| `PATCH` / `DELETE` | `/api/numbers/{id}` | Edit / remove a number |
| `POST` | `/api/numbers/{id}/sync-twilio` | Point the Twilio number's webhooks at this server |
| `GET` / `POST` | `/api/campaigns` | List / create campaigns (`name, customer_ids, profile_id, max_concurrent, max_attempts, retry_delay_minutes`) |
| `GET` / `DELETE` | `/api/campaigns/{id}` | Campaign with per-contact progress / delete a finished campaign |
| `POST` | `/api/campaigns/{id}/start` · `/pause` · `/cancel` | Control the dialer for a campaign |
| `GET` | `/api/stats/overview` | Total / completed / failed calls, interested leads, follow-ups, average duration |
| `POST` | `/voice` · `/call-status` · `/transfer-status` · `/transfer-whisper` | Twilio webhooks (signature-validated) |
| `WS` | `/stream` | Twilio Media Stream ↔ agent |
| `WS` | `/browser-stream?call_id&token` | Browser microphone ↔ agent |
| `POST` | `/call` | Legacy manual-test endpoint (unauthenticated; don't expose publicly) |
| `GET` | `/health` | Health check |

Example:

```bash
curl -c jar -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
     -d '{"username":"admin","password":"..."}'
curl -b jar -X POST localhost:8000/api/customers -H 'content-type: application/json' \
     -d '{"name":"Rahul Kumar","phone":"+919876543210","purpose":"Product enquiry","product":"Commercial RO System"}'
curl -b jar -X POST localhost:8000/api/calls -H 'content-type: application/json' -d '{"customer_id":"<id>"}'
curl -b jar 'localhost:8000/api/calls?outcome=qualified&follow_up=true'
```

## Database schema

Alembic migrations in `backend/alembic/versions/` are the source of truth.
[database/schema.sql](database/schema.sql) is a `pg_dump` snapshot for reading.

| Table | Holds |
|---|---|
| `business_profiles` | Agent configuration per business: name, persona, products, objective, greeting, language, `fields` (JSONB checklist), `transfer_number`, `is_default` |
| `phone_numbers` | Twilio number pool: number, label, profile, inbound/outbound switches, `last_used_at` (round-robin) |
| `campaigns` / `campaign_contacts` | Batch calls: concurrency, retries, status; one row per customer with attempts and last outcome |
| `customers` | name, phone (E.164), company, purpose, product, `profile_id` |
| `calls` | customer, profile, Twilio SID, direction, **channel** (phone/browser), from/to number, campaign, `transferred_to`, status, start/end time, duration, error reason, **outcome** |
| `conversation_messages` | One row per turn: speaker (`customer`/`ai`), message, timestamp |
| `call_events` | Event log: provider errors, silences, interruptions, fields collected, AI errors, … |
| `requirements` | Collected fields (`fields` JSONB keyed by the profile's field keys, plus fixed RO columns) |
| `call_summaries` | summary, intent, key requirements, important points, lead status, follow-up (+ notes), call outcome text |
| `admin_users` | Dashboard login (bcrypt) |

The ER diagram is in [ARCHITECTURE.md](ARCHITECTURE.md#database).

## Free-tier limitations

| Service | Limitation | Impact / workaround |
|---|---|---|
| **Twilio trial** | Can only call **Verified Caller IDs**. Every call starts with a trial message and the callee must **press a key**. Calls to other countries need **Geo permissions** enabled. Limited trial credit | Verify the test number; press a key after the message; enable the country. Or use **browser-call mode** |
| Twilio → Indian numbers | Calls from a US trial number are international. Some carriers or DND settings may block or flag them | Try another number, or use browser-call mode for the demo |
| **Gemini API free tier** | Rate limits on Live sessions and requests; the native-audio model is a *preview*; free-tier prompts may be used by Google to improve its products | Fine for demos. Use a paid key or Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`) for production |
| **ngrok free** | New random hostname on every restart | Update `SERVER_HOST` and restart the backend each time |
| **Render free** web service | Sleeps when idle; the first request takes a while to wake it | Twilio's `/voice` request may time out on a cold backend ("application error"). Open `/health` before calling |
| Browser calls | Microphone needs `https://` or `http://localhost` | Use localhost or a TLS deployment |

## Troubleshooting: "the outbound call isn't received"

The outbound flow was checked end to end and its logic is correct. When a call doesn't go through,
it's almost always one of the trial or configuration limits above. The dashboard now tells you
which one:

| Symptom | Cause | Fix |
|---|---|---|
| Error right after clicking **Phone call** | Twilio rejected the request. The message names the reason: unverified number (21219), country disabled (21215/13227), bad number format (21211), wrong credentials (20003) | Do what the message says. Twilio Console → Monitor → Logs → Calls shows the details |
| Phone never rings, call ends `failed` / `no_answer` | Carrier or DND blocking of international calls, phone off, ring timeout | Try a different verified number; check the Twilio call log |
| You answer, hear the trial message, then the line drops | No key was pressed during the trial disclaimer | Press any key. The call now shows `answered_but_stream_never_connected` |
| "An application error has occurred" | Twilio couldn't fetch `/voice`: wrong `SERVER_HOST`, tunnel down, backend asleep, or `SERVER_HOST`/`USE_TLS` not matching the public URL (signature check fails; the backend logs a warning) | Fix `SERVER_HOST`, keep ngrok running, open `/health` first |
| Connected but nobody speaks | *(Fixed)* The agent used to wait for the callee to talk first. It now greets immediately. If it's still silent, check `GOOGLE_API_KEY` and quota: an AI failure is now announced and logged as `ai_error` | Check the call's event timeline |
| Audio can't connect through localtunnel | localtunnel's WebSocket support is unreliable | Use ngrok |

## Future improvements

* Retry and reconnect for the Gemini Live session (session resumption) instead of ending the call
* Campaign calling windows (time zones, "don't call after 8 pm") and a scheduled start time
* Ring groups / queues for transfers (several people, hold music) via Twilio TaskRouter
* Twilio answering-machine detection to leave a voicemail instead of talking to one
* Per-profile voice selection, and a knowledge base (RAG) for product and pricing questions
* Call recording storage with playback in the dashboard
* Multi-user admin with roles, session revocation, and a shared (Redis) rate limiter
* A WebSocket push channel for live call monitoring of phone calls (browser calls already stream
  live)
* CRM export / webhooks for qualified leads

## Security

* All `/api/*` routes (except login) need a signed, httpOnly session cookie, checked server-side.
  Passwords are bcrypt-hashed.
* Twilio webhooks are signature-validated. The browser stream needs a 2-minute token bound to a
  single queued call, so it can't be reused or replayed.
* Call starts are rate-limited. Inputs are validated by Pydantic: E.164 phones, profile field
  keys, and length limits.
* Security headers (CSP incl. `connect-src` for the API's WebSocket, frame denial,
  `Permissions-Policy` limiting the microphone to the dashboard's own origin) are set on both apps.
  Secrets live only in backend env vars.

## Deployment

**Render** (backend + Postgres) and **Vercel** (frontend):

1. Render web service, root `backend/`, build `pip install -e .`, start `python -m audiocall.main`.
   Set every variable from `backend/.env.example`, with `SERVER_HOST=<app>.onrender.com`,
   `USE_TLS=true` and `FRONTEND_ORIGIN=<vercel url>`. Use `DATABASE_URL` in the
   `postgresql+asyncpg://` form.
2. Run `python -m alembic upgrade head` and `python scripts/create_admin.py <user> <pass>` once.
3. Vercel: import `frontend/`, set `NEXT_PUBLIC_API_URL` to the Render URL.
