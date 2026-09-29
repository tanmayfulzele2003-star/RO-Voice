# Database

This directory holds a read-only snapshot of the PostgreSQL schema for the RO Sales Voice-Agent
Platform:

- `schema.sql` — full `pg_dump --schema-only` snapshot, regenerated after every migration. **Not**
  applied directly — it exists for quick reading/review only.

The actual source of truth for schema changes is `backend/alembic/versions/` (Alembic migration
scripts). To stand up a database, run migrations from `backend/`, not from this file:

```bash
cd backend
python -m alembic upgrade head
```

6 tables: `customers`, `calls`, `conversation_messages`, `requirements`, `call_summaries`,
`admin_users` (plus Alembic's own `alembic_version` bookkeeping table). See
[../ARCHITECTURE.md](../ARCHITECTURE.md) for the ER diagram and relationships.

The backend connects to a managed Postgres
instance (e.g. Neon/Render Postgres) via `DATABASE_URL` in every environment — there is no local
Docker Compose Postgres; local dev points `DATABASE_URL` at any local or managed Postgres 14+
instance you have.
