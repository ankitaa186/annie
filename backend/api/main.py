"""
Backend API Main Module

FastAPI application entry point for Annie backend service.
"""

import os
import time
from datetime import datetime, timezone
from typing import Dict, Any

import httpx
import redis.asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from api.config import get_config
from api.logging import get_logger
from api.mcp_client import MCPClient, MCPClientError
from api.routes import chat, stream, conversations, session
from api.middleware.cloudflare_auth import cloudflare_auth_middleware
from api.middleware.rate_limiter import rate_limit_middleware

logger = get_logger(__name__)
config = get_config()


def setup_debugger():
    """Initialize remote debugger automatically in dev environment."""
    environment = os.getenv("ENVIRONMENT", "dev")
    
    # Only enable debugging in dev environment
    if environment.lower() == "dev":
        try:
            import debugpy
            debug_port = int(os.getenv("DEBUGGER_PORT", "5678"))
            debugpy.listen(("0.0.0.0", debug_port))
            logger.info(f"🔧 Remote debugger listening on port {debug_port} (dev mode)")
        except ImportError:
            logger.debug("debugpy not available - remote debugging disabled")
        except Exception as e:
            logger.warning(f"Failed to setup debugger: {e}")


# Initialize debugger before creating app (dev only)
setup_debugger()

# Create FastAPI app
app = FastAPI(
    title="Annie Backend API",
    description="Backend API for Annie - Personal AI Companion",
    version="1.0.0"
)

# Include routers
app.include_router(chat.router)
app.include_router(stream.router)
app.include_router(conversations.router)
app.include_router(session.router)

# Add CORS middleware
# Configured via CORS_ORIGINS env var (comma-separated) or defaults
_default_origins = "https://annie.memoryforge.io,http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Cloudflare Access authentication middleware (Epic 20, Story 20.13)
# Runs before request logging to authenticate web UI users
# For Telegram bot requests (no CF headers), passes through unchanged
@app.middleware("http")
async def cf_auth(request: Request, call_next):
    """Cloudflare Access authentication wrapper."""
    return await cloudflare_auth_middleware(request, call_next)


# Rate limiting middleware (Epic 20, Story 20.14)
# Applies 60 requests/minute limit per authenticated user
# Runs after auth middleware so user_id is available
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Rate limiting middleware wrapper."""
    return await rate_limit_middleware(request, call_next)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with method, path, status code, and response time."""
    start_time = time.time()

    try:
        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Log request details
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration_ms}ms",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_host": request.client.host if request.client else None
            }
        )

        return response

    except Exception as e:
        # Calculate duration even on error
        duration_ms = int((time.time() - start_time) * 1000)

        # Log error with full context
        logger.error(
            f"{request.method} {request.url.path} - ERROR - {duration_ms}ms",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "error_type": type(e).__name__,
                "error": str(e),
                "client_host": request.client.host if request.client else None
            },
            exc_info=True  # Include full stack trace
        )

        # Re-raise to let FastAPI's exception handlers deal with it
        raise


# Global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for all unhandled exceptions.

    Ensures user-friendly error messages and comprehensive logging.
    Catches any exception that wasn't handled by route-specific handlers.
    """
    logger.error(
        "Unhandled exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "client_host": request.client.host if request.client else None
        },
        exc_info=True  # Include full stack trace
    )

    # Return user-friendly error
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with clear, user-friendly messages.

    Provides detailed validation error information for debugging while
    maintaining security (no internal implementation details exposed).
    """
    # Convert errors to JSON-serializable format
    # Pydantic v2 errors may contain non-serializable exception objects in 'ctx'
    serializable_errors = []
    for error in exc.errors():
        err = dict(error)
        # Convert ctx errors to string representations
        if "ctx" in err and isinstance(err["ctx"], dict):
            err["ctx"] = {
                k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                for k, v in err["ctx"].items()
            }
        serializable_errors.append(err)

    logger.warning(
        "Request validation failed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "errors": serializable_errors,
            "client_host": request.client.host if request.client else None
        }
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request data. Please check your input.",
                "details": serializable_errors,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }
        }
    )


async def check_mcp_server_health() -> str:
    """Check MCP server health via HTTP."""
    try:
        async with MCPClient() as client:
            health = await client.client.get(f"{client.mcp_server_url}/health")
            if health.status_code == 200 and health.json().get("status") == "ok":
                return "ok"
            else:
                return "degraded"
    except MCPClientError as e:
        logger.warning(
            "MCP server health check failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return "unavailable"
    except Exception as e:
        logger.error(
            "Unexpected error in MCP health check",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return "unavailable"


async def check_redis_health() -> str:
    """Check Redis health via connection test."""
    try:
        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", 6379))

        client = redis.asyncio.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception as e:
        logger.warning(
            "Redis health check failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return "unavailable"


def check_llm_api_health() -> str:
    """Check LLM API availability."""
    try:
        from api.llm_client import LLMClient
        client = LLMClient()
        status = client.health_check()
        return status
    except (ValueError, KeyError) as e:
        # Configuration errors (missing API keys, invalid provider, etc.)
        logger.warning(
            "LLM health check failed due to configuration error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return "unavailable"
    except Exception as e:
        logger.error(
            "Unexpected error in LLM health check",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return "unavailable"


async def check_agentic_memories_health() -> Dict[str, Any]:
    """Check agentic-memories service availability with full component status.

    Calls the /health/full endpoint to get detailed status of:
    - env: API key configuration
    - chroma: Vector database
    - timescale: Time-series database
    - neo4j: Graph database
    - redis: Cache/queue
    - portfolio: Portfolio tables
    - langfuse: Observability

    Returns:
        Dictionary with status and component checks
    """
    agentic_memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{agentic_memories_url}/health/full")

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "degraded",
                    "error": f"Health check returned status {response.status_code}"
                }
    except httpx.TimeoutException:
        logger.warning("agentic-memories health check timed out")
        return {
            "status": "unavailable",
            "error": "Connection timed out"
        }
    except httpx.ConnectError:
        logger.warning("agentic-memories service not reachable")
        return {
            "status": "unavailable",
            "error": "Service not reachable"
        }
    except Exception as e:
        logger.warning(f"agentic-memories health check failed: {e}")
        return {
            "status": "unavailable",
            "error": str(e)
        }


async def check_proactive_worker_health() -> Dict[str, Any]:
    """Check proactive worker liveness via Redis heartbeat.

    Returns:
        Dictionary with worker status including alive, last_heartbeat, and age_seconds.
    """
    try:
        from api.proactive.worker import HEARTBEAT_KEY, HEARTBEAT_TTL

        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", 6379))

        redis_client = redis.asyncio.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        heartbeat_json = await redis_client.get(HEARTBEAT_KEY)
        await redis_client.close()

        if not heartbeat_json:
            return {
                "status": "unavailable",
                "alive": False,
                "last_heartbeat": None,
                "age_seconds": None,
                "reason": "no_heartbeat"
            }

        import json
        heartbeat = json.loads(heartbeat_json)
        timestamp = datetime.fromisoformat(heartbeat["timestamp"].replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()

        if age_seconds < HEARTBEAT_TTL:
            return {
                "status": "ok",
                "alive": True,
                "last_heartbeat": heartbeat["timestamp"],
                "age_seconds": round(age_seconds, 1)
            }
        else:
            return {
                "status": "degraded",
                "alive": False,
                "last_heartbeat": heartbeat["timestamp"],
                "age_seconds": round(age_seconds, 1),
                "reason": "heartbeat_stale"
            }

    except Exception as e:
        logger.warning(
            "Proactive worker health check failed",
            extra={"error": str(e)}
        )
        return {
            "status": "unavailable",
            "alive": False,
            "last_heartbeat": None,
            "age_seconds": None,
            "reason": str(e)
        }


def check_langfuse_health() -> Dict[str, Any]:
    """Check Langfuse observability status.

    Returns:
        Dictionary with Langfuse status including enabled, available, and last_flush.
    """
    try:
        from api.observability.langfuse_client import ping_langfuse
        from api.config import is_langfuse_enabled

        enabled = is_langfuse_enabled()
        if not enabled:
            return {
                "enabled": False,
                "client_available": False,
                "last_flush": None
            }

        client_available = ping_langfuse()
        return {
            "enabled": True,
            "client_available": client_available,
            "last_flush": None  # TODO: Track actual last flush timestamp if needed
        }
    except Exception as e:
        logger.warning(
            "Langfuse health check failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return {
            "enabled": False,
            "client_available": False,
            "last_flush": None
        }


def check_cloud_logging_health() -> Dict[str, Any]:
    """Check cloud logging (Grafana Loki) configuration status.

    Returns:
        Dictionary with cloud logging status including enabled, provider, and configured.
    """
    import os

    env = os.environ.get("ENV", "dev")
    loki_url = os.environ.get("LOKI_URL", "")

    if env != "prod":
        return {
            "enabled": False,
            "provider": None,
            "status": "disabled",
            "note": "Cloud logging only active in production (ENV=prod)"
        }

    # Production mode
    if loki_url and loki_url != "REPLACE_ME":
        return {
            "enabled": True,
            "provider": "grafana_loki",
            "status": "configured"
        }
    else:
        return {
            "enabled": True,
            "provider": "grafana_loki",
            "status": "not_configured",
            "note": "LOKI_URL not set - logs not being shipped to Grafana Cloud"
        }


@app.on_event("startup")
async def startup_event():
    """Application startup handler."""
    import asyncio
    from api.config import validate_mqtt_config, HA_MQTT_BROKER

    logger.info("Annie Backend API starting up...")
    logger.info(f"Environment: {config.get('ENVIRONMENT', 'unknown')}")
    logger.info(f"Log level: {config.get('LOG_LEVEL', 'INFO')}")
    logger.info(f"MCP Server URL: {config.get('MCP_SERVER_URL', 'not configured')}")

    # Epic 16: Log MQTT configuration status once at startup
    if HA_MQTT_BROKER:
        mqtt_issues = validate_mqtt_config()
        if mqtt_issues:
            logger.warning(
                f"MQTT configuration issues: {', '.join(mqtt_issues)}. "
                "MQTT subscriber may not work correctly."
            )
        else:
            logger.info("Home Assistant MQTT subscriber configured and ready.")
    else:
        logger.info(
            "Home Assistant MQTT not configured (HA_MQTT_BROKER empty). "
            "MQTT subscriber will be skipped."
        )

    # Initialize Langfuse client to ensure environment variables are set for decorators
    try:
        from api.observability.langfuse_client import get_langfuse_client
        get_langfuse_client()
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse on startup: {e}")

    # Start background workers (Story 12-5)
    try:
        from api.memory import MemoryManager
        memory_manager = MemoryManager()

        # Start retry worker for queued memories
        asyncio.create_task(memory_manager.start_retry_worker())
        logger.info("Memory retry worker started")

        # Start flush worker for stale sessions
        asyncio.create_task(memory_manager.start_flush_worker())
        logger.info("Stale session flush worker started")
    except Exception as e:
        logger.warning(f"Failed to start background workers: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown handler."""
    logger.info("Annie Backend API shutting down...")


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Basic health check endpoint.

    Returns:
        JSON response with status and timestamp
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
    )


@app.get("/health/full")
async def full_health_check() -> JSONResponse:
    """
    Full health check endpoint with component status.

    Returns component health status without failing if components are down.
    This allows monitoring to track individual component health.

    Returns:
        JSON response with overall status, component statuses, and timestamp
    """
    # Check all components
    components = {
        "mcp_server": await check_mcp_server_health(),
        "redis": await check_redis_health(),
        "llm_api": check_llm_api_health(),
        "agentic_memories": await check_agentic_memories_health(),
        "proactive_worker": await check_proactive_worker_health(),
        "langfuse": check_langfuse_health(),
        "cloud_logging": check_cloud_logging_health()
    }

    # Overall status is "ok" if at least the API itself is running
    # Individual component failures don't fail the health check
    overall_status = "ok"

    # If any critical component is unavailable, set status to "degraded"
    agentic_status = components["agentic_memories"].get("status", "ok")
    if (components["mcp_server"] == "unavailable" or
        components["redis"] == "unavailable" or
        agentic_status in ("unavailable", "degraded")):
        overall_status = "degraded"

    return JSONResponse(
        status_code=200,  # Always return 200 to indicate API is responsive
        content={
            "status": overall_status,
            "components": components,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
    )


@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint with API information."""
    return JSONResponse(content={
        "name": "Annie Backend API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "detailed_health": "/health/full",
            "chat": "/api/chat",
            "stream": "/api/stream/{conversation_id}",
            "stream_health": "/api/stream/health",
            "conversations": {
                "list": "GET /api/conversations",
                "create": "POST /api/conversations",
                "get": "GET /api/conversations/{id}",
                "update": "PATCH /api/conversations/{id}",
                "delete": "DELETE /api/conversations/{id}",
                "messages": "GET /api/conversations/{id}/messages"
            }
        }
    })
