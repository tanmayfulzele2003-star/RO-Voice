"""Test configuration. Env is set before any audiocall import, since config
is read at import time. No database or API keys are needed: anything that
would touch Postgres, Twilio or Gemini is faked in the tests themselves."""

import os

os.environ.setdefault("SESSION_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("TWILIO_VALIDATE_SIGNATURE", "false")
