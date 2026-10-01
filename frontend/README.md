# Frontend — Next.js admin dashboard

The dashboard for the AI calling agent: customers, business profiles, phone and browser calls,
call history with filters, transcripts, AI summaries and statistics.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL → the FastAPI backend
npm install
npm run dev                  # http://localhost:3000
npm run lint && npm run build
```

Setup, architecture and API docs are in the [root README](../README.md).

Browser calls need microphone access, which browsers only allow on `https://` or
`http://localhost`.
