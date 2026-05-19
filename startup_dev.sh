#!/bin/bash
# Development startup script — single worker with focus on code reload and observability
# Use this for local development where you want hot reload and full observability enabled
set -e

echo "🚀 FastAPI Development Server"
echo "────────────────────────────────────────"

# Run migrations
alembic upgrade head

UVICORN_LOOP=$(python3 -c "from app.config import settings; print(settings.uvicorn_loop)")

echo "Settings:"
echo "  Mode: Development (observability enabled)"
echo "  Workers: 1"
echo "  Loop: $UVICORN_LOOP"
echo "  HTTP: httptools"
echo "────────────────────────────────────────"

# Use direct uvicorn for the best dev experience (auto-reload)
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --loop auto \
  --http httptools \
  --log-level debug