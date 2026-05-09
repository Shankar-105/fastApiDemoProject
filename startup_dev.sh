#!/bin/bash
# Development startup script — single worker with focus on code reload and observability
# Use this for local development where you want hot reload and full observability enabled
set -e

echo "🚀 FastAPI Development Server"
echo "────────────────────────────────────────"

# Run migrations
alembic upgrade head

echo "Settings:"
echo "  Mode: Development (observability enabled)"
echo "  Workers: 1"
echo "  Loop: auto"
echo "  HTTP: httptools"
echo "────────────────────────────────────────"

# Use direct uvicorn for the best dev experience (auto-reload)
# We pass the settings manually or let uvicorn pick up defaults
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --loop auto \
  --http httptools \
  --log-level debug
