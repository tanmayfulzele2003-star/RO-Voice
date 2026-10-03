# Database

This directory holds a read-only snapshot of the PostgreSQL schema for the AI calling agent
platform:

- `schema.sql` — full `pg_dump --schema-only` snapshot, regenerated after every migration. **Not**
  applied directly — it exists for quick reading/review only.

The actual source of truth for schema changes is `backend/alembic/versions/` (Alembic migration
scripts). To stand up a database, run migrations from `backend/`, not from this file:

```bash
cd backend
python -m alembic upgrade head
```

12 tables: `business_profiles`, `customers`, `calls`, `conversation_messages`, `call_events`,
`requirements`, `call_summaries`, `phone_numbers`, `campaigns`, `campaign_contacts`, `app_settings`, `admin_users` (plus Alembic's own `alembic_version` bookkeeping
table). The first migration that introduces `business_profiles` seeds the default RO profile and
backfills existing calls. See [../ARCHITECTURE.md](../ARCHITECTURE.md#database) for the ER diagram
and relationships.

Regenerate the snapshot after a migration with:

```bash
pg_dump --schema-only --no-owner --no-privileges "$DATABASE_URL_WITHOUT_ASYNCPG" > database/schema.sql
```

The backend connects to a managed Postgres
instance (e.g. Neon/Render Postgres) via `DATABASE_URL` in every environment — there is no local
Docker Compose Postgres; local dev points `DATABASE_URL` at any local or managed Postgres 14+
instance you have.
