#!/bin/bash
set -e

ENVIRONMENT="${ENVIRONMENT:-production}"

if [ "$ENVIRONMENT" = "dev" ]; then
    WORKERS=3
    echo "🔧 Dev mode - starting uvicorn with $WORKERS workers"
else
    WORKERS=5
    echo "🚀 Production mode - starting uvicorn with $WORKERS workers"
fi

exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers $WORKERS
