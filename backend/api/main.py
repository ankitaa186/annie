"""
Backend API Main Module

FastAPI application entry point for Annie backend service.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_config
from api.logging import get_logger
from api.mcp_client import MCPClient, MCPClientError
from api.routes import chat, stream

logger = get_logger(__name__)
config = get_config()

# Create FastAPI app
app = FastAPI(
    title="Annie Backend API",
    description="Backend API for Annie - Personal AI Companion",
    version="1.0.0"
)

# Include routers
app.include_router(chat.router)
app.include_router(stream.router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with method, path, status code, and response time."""
    start_time = time.time()

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


def check_mcp_server_health() -> str:
    """Check MCP server health via HTTP."""
    try:
        with MCPClient() as client:
            health = client.health_check()
            if health.get("status") == "ok":
                return "ok"
            else:
                return "degraded"
    except Exception as e:
        logger.warning(f"MCP server health check failed: {str(e)}")
        return "unavailable"


def check_redis_health() -> str:
    """Check Redis health via connection test."""
    # TODO: Implement actual Redis health check in Story 2.5
    # For now, return "ok" as placeholder
    return "ok"


def check_llm_api_health() -> str:
    """Check LLM API availability."""
    try:
        from api.llm_client import LLMClient
        client = LLMClient()
        status = client.health_check()
        return status
    except Exception as e:
        logger.error(f"LLM health check failed: {str(e)}")
        return "unavailable"


def check_agentic_memories_health() -> str:
    """Check agentic-memories service availability."""
    # TODO: Implement actual agentic-memories health check in Story 3.1
    # For now, return "ok" as placeholder
    return "ok"


@app.on_event("startup")
async def startup_event():
    """Application startup handler."""
    logger.info("Annie Backend API starting up...")
    logger.info(f"Environment: {config.get('ENVIRONMENT', 'unknown')}")
    logger.info(f"Log level: {config.get('LOG_LEVEL', 'INFO')}")
    logger.info(f"MCP Server URL: {config.get('MCP_SERVER_URL', 'not configured')}")


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


@app.get("/health/detailed")
async def detailed_health_check() -> JSONResponse:
    """
    Detailed health check endpoint with component status.

    Returns component health status without failing if components are down.
    This allows monitoring to track individual component health.

    Returns:
        JSON response with overall status, component statuses, and timestamp
    """
    # Check all components
    components = {
        "mcp_server": check_mcp_server_health(),
        "redis": check_redis_health(),
        "llm_api": check_llm_api_health(),
        "agentic_memories": check_agentic_memories_health()
    }

    # Overall status is "ok" if at least the API itself is running
    # Individual component failures don't fail the health check
    overall_status = "ok"

    # If any critical component is unavailable, set status to "degraded"
    if components["mcp_server"] == "unavailable" or components["redis"] == "unavailable":
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
            "detailed_health": "/health/detailed",
            "chat": "/api/chat",
            "stream": "/api/stream/{conversation_id}",
            "stream_health": "/api/stream/health"
        }
    })
