#!/usr/bin/env bash
set -e

echo "==> Running Alembic database migrations..."
alembic upgrade head

echo "==> Starting FastAPI server with Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
