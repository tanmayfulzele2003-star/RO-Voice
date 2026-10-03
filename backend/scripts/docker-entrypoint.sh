#!/bin/sh
# Container start: bring the schema up to date, create the first admin when
# ADMIN_USERNAME/ADMIN_PASSWORD are set (otherwise the server logs a one-time
# setup link), then run the server.
set -e
cd /app
alembic upgrade head
python scripts/bootstrap_admin.py
exec python -m audiocall.main
