#!/usr/bin/env python3
"""
Health check script for proactive worker.

Checks Redis heartbeat to verify worker is alive and polling.
Exit code 0 = healthy, 1 = unhealthy.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import redis.asyncio as redis_async


HEARTBEAT_KEY = "proactive:worker:heartbeat"
HEARTBEAT_TTL = 120  # 2 minutes


async def check_heartbeat() -> bool:
    """Check if worker heartbeat is recent."""
    try:
        redis_host = os.environ.get("REDIS_HOST", "redis")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))

        redis_client = redis_async.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        heartbeat_json = await redis_client.get(HEARTBEAT_KEY)
        await redis_client.aclose()

        if not heartbeat_json:
            print("No heartbeat found")
            return False

        heartbeat = json.loads(heartbeat_json)
        timestamp = datetime.fromisoformat(heartbeat["timestamp"].replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()

        if age_seconds < HEARTBEAT_TTL:
            print(f"Healthy: heartbeat {age_seconds:.1f}s ago")
            return True
        else:
            print(f"Unhealthy: heartbeat {age_seconds:.1f}s ago (> {HEARTBEAT_TTL}s)")
            return False

    except Exception as e:
        print(f"Health check error: {e}")
        return False


if __name__ == "__main__":
    healthy = asyncio.run(check_heartbeat())
    sys.exit(0 if healthy else 1)

