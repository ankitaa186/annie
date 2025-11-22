"""
Langfuse client singleton for tracing and observability.

This module provides a singleton Langfuse client with lazy initialization,
background flushing, and graceful degradation when Langfuse is unavailable.
"""
from typing import Optional, Any
import atexit

from api.config import (
    get_langfuse_public_key,
    get_langfuse_secret_key,
    get_langfuse_host,
    is_langfuse_enabled,
)
from api.logging import get_logger

logger = get_logger(__name__)

_langfuse_client: Optional[Any] = None


def get_langfuse_client() -> Optional[Any]:
    """Get or create the singleton Langfuse client.

    This function implements lazy initialization with singleton pattern.
    The client is configured with background flushing for performance.

    Returns:
        Langfuse client if enabled and configured, None otherwise.
    """
    global _langfuse_client

    if not is_langfuse_enabled():
        logger.info("Langfuse tracing disabled (keys not configured)")
        return None

    if _langfuse_client is None:
        try:
            from langfuse import Langfuse
            import os

            # Get environment for release tagging
            environment = os.getenv("ENVIRONMENT", "dev")

            _langfuse_client = Langfuse(
                public_key=get_langfuse_public_key(),
                secret_key=get_langfuse_secret_key(),
                host=get_langfuse_host(),
                release=f"annie-{environment}",  # Tag traces with release/environment
                flush_at=10,  # Batch size - send after 10 traces
                flush_interval=1.0,  # Flush every second
                enabled=True,  # Explicitly enable
                debug=False  # Set to True for SDK debug logging
            )

            # Ensure traces are flushed on app shutdown
            def flush_on_exit():
                if _langfuse_client:
                    logger.info("Flushing Langfuse traces on shutdown...")
                    _langfuse_client.flush()
                    logger.info("Langfuse traces flushed successfully")

            atexit.register(flush_on_exit)

            logger.info(
                "Langfuse client initialized successfully",
                extra={
                    "host": get_langfuse_host(),
                    "release": f"annie-{environment}",
                    "batch_size": 10,
                    "flush_interval": 1.0,
                    "public_key_prefix": get_langfuse_public_key()[:10] + "..."
                }
            )

        except ImportError:
            # Langfuse not installed, graceful degradation
            logger.warning("Langfuse package not installed, tracing disabled")
            return None
        except Exception as e:
            # Log error but don't crash the app (fire-and-forget pattern)
            logger.warning(
                "Failed to initialize Langfuse client, tracing disabled",
                extra={"error": str(e)}
            )
            return None

    return _langfuse_client


def ping_langfuse() -> bool:
    """Check if Langfuse client is available and functional.

    This is a non-blocking health check that returns immediately.

    Returns:
        True if client is available, False otherwise.
    """
    client = get_langfuse_client()
    return client is not None
