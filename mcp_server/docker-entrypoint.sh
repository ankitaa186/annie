#!/bin/bash
set -e

ENVIRONMENT="${ENVIRONMENT:-production}"

if [ "$ENVIRONMENT" = "dev" ]; then
    WORKERS=2
    echo "🔧 Dev mode - starting uvicorn with $WORKERS workers"
else
    WORKERS=5
    echo "🚀 Production mode - starting uvicorn with $WORKERS workers"
fi

export PYTHONPATH=/app
exec python -m uvicorn mcp_server.server:app --host 0.0.0.0 --port 8002 --workers $WORKERS
