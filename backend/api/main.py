"""
Backend API Main Module

FastAPI application entry point for Annie backend service.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.logging import get_logger

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Annie Backend API",
    description="Backend API for Annie - Personal AI Companion",
    version="1.0.0"
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(content={"status": "ok"})


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check endpoint."""
    # TODO: Add component health checks (Redis, MCP server, etc.)
    return JSONResponse(content={
        "status": "ok",
        "components": {
            "api": "ok"
        }
    })


@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(content={
        "message": "Annie Backend API",
        "version": "1.0.0",
        "status": "running"
    })

