"""
Observability module for Annie Backend API.

This module provides LLM tracing and observability via Langfuse Cloud.
Includes singleton client management and request-scoped tracing utilities.
"""

from .langfuse_client import get_langfuse_client, ping_langfuse
from .tracing import (
    start_trace,
    get_current_trace,
    start_span,
    end_span,
    trace_error,
)

__all__ = [
    "get_langfuse_client",
    "ping_langfuse",
    "start_trace",
    "get_current_trace",
    "start_span",
    "end_span",
    "trace_error",
]
