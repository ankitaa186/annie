"""
MCP Server Tool Registry and Tool Implementations

This module provides tool registration and basic tool implementations.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for MCP tools."""
    
    def __init__(self):
        """Initialize tool registry."""
        self.tools: Dict[str, Dict[str, Any]] = {}
    
    def register(self, tool_info: Dict[str, Any]):
        """
        Register a tool.
        
        Args:
            tool_info: Tool information dictionary with:
                - name: Tool name
                - description: Tool description
                - inputSchema: JSON schema for input parameters
                - handler: Tool handler function
        """
        tool_name = tool_info["name"]
        self.tools[tool_name] = tool_info
        logger.debug(f"Registered tool: {tool_name}")
    
    def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get tool information by name.
        
        Args:
            tool_name: Tool name
        
        Returns:
            Tool information dictionary or None if not found
        """
        return self.tools.get(tool_name)


async def health_check_tool_handler() -> Dict[str, Any]:
    """
    Health check tool handler.

    Calls the backend's full health check endpoint to get real
    component status (Redis, MCP, LLM API, agentic-memories, Langfuse).

    Returns:
        Health status dictionary with component details
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("http://backend:8000/health/full")

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "degraded",
                    "error": f"Health check returned status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }


# Health check tool definition
health_check_tool = {
    "name": "health_check",
    "description": "Check the full health status of all system components. Returns status of Redis, MCP server, LLM API, agentic-memories (with all its sub-components), and Langfuse. Use when asked about system health, status, or availability.",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "handler": health_check_tool_handler
}


async def store_memory_tool_handler(
    user_id: str,
    content: str,
    importance: float = 0.8,
    layer: str = "semantic",
    persona_tags: list = None,
    metadata: dict = None,
    # Episodic fields
    event_timestamp: str = None,
    location: str = None,
    participants: list = None,
    # Emotional fields
    emotional_state: str = None,
    valence: float = None,
    arousal: float = None,
    # Procedural fields
    skill_name: str = None,
    proficiency_level: str = None
) -> Dict[str, Any]:
    """
    Store a critical memory directly in agentic-memories service.

    This tool stores pre-formatted memory content directly using the fast
    /v1/memories/direct endpoint, bypassing the slow LangGraph extraction pipeline.
    Use for critical information that the user explicitly asks to remember.

    Args:
        user_id: User identifier
        content: Pre-formatted memory content to store (max 5000 chars)
        importance: Importance level 0.0-1.0, higher = more critical (default: 0.8)
        layer: Memory layer - "short-term", "semantic", "long-term" (default: "semantic")
        persona_tags: Tags for memory categorization (max 10)
        metadata: Optional metadata (source, conversation_id, trigger)
        event_timestamp: When the event occurred (ISO 8601) - for episodic memories
        location: Where it happened - for episodic memories
        participants: Who was involved - for episodic memories
        emotional_state: Primary emotional state (e.g., 'happy', 'anxious')
        valence: Emotional valence -1.0 (negative) to 1.0 (positive)
        arousal: Emotional arousal 0.0 (calm) to 1.0 (excited)
        skill_name: Name of skill/procedure - for procedural memories
        proficiency_level: User's proficiency ("beginner", "intermediate", "advanced", "expert")

    Returns:
        dict: Result with status, memory_id, storage details, and stored content
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Apply defaults for mutable arguments
    if persona_tags is None:
        persona_tags = []

    # Limit persona_tags to max 10 items (AC #3)
    persona_tags = persona_tags[:10]

    # Build request payload with required fields
    # Build metadata with source: "llm_explicit" merged with user-provided metadata (AC #3)
    merged_metadata = {"source": "llm_explicit"}
    if metadata:
        merged_metadata.update(metadata)

    payload = {
        # Required fields
        "user_id": user_id,
        "content": content,
        # General fields (AC #3)
        "layer": layer,
        "type": "explicit",  # Always explicit for LLM-stored memories
        "importance": importance,
        "confidence": 0.95,  # High confidence for explicit storage
        "persona_tags": persona_tags,
        "metadata": merged_metadata
    }

    # Add optional episodic fields if provided (AC #3)
    if event_timestamp is not None:
        payload["event_timestamp"] = event_timestamp
    if location is not None:
        payload["location"] = location
    if participants is not None:
        payload["participants"] = participants

    # Add optional emotional fields if provided (AC #3)
    if emotional_state is not None:
        payload["emotional_state"] = emotional_state
    if valence is not None:
        payload["valence"] = valence
    if arousal is not None:
        payload["arousal"] = arousal

    # Add optional procedural fields if provided (AC #3)
    if skill_name is not None:
        payload["skill_name"] = skill_name
    if proficiency_level is not None:
        payload["proficiency_level"] = proficiency_level

    # Error codes that should NOT trigger retry (AC #5)
    NO_RETRY_ERRORS = ["VALIDATION_ERROR", "INTERNAL_ERROR"]

    # Make HTTP request to agentic-memories with retry logic
    max_retries = 3
    retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    # Timeout reduced to 10s - direct storage should complete in 1-3s (AC #2)
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Storing critical memory via direct endpoint",
                    extra={
                        "user_id": user_id,
                        "content_length": len(content),
                        "importance": importance,
                        "layer": layer,
                        "has_episodic": event_timestamp is not None,
                        "has_emotional": emotional_state is not None,
                        "has_procedural": skill_name is not None,
                        "attempt": attempt + 1,
                        "endpoint": "/v1/memories/direct"
                    }
                )

                # Call /v1/memories/direct endpoint (AC #1)
                response = await client.post(
                    f"{memories_url}/v1/memories/direct",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                duration_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200 or response.status_code == 201:
                    result = response.json()
                    memory_id = result.get("memory_id")
                    storage_details = result.get("storage", {})

                    logger.info(
                        "Critical memory stored successfully via direct endpoint",
                        extra={
                            "user_id": user_id,
                            "memory_id": memory_id,
                            "duration_ms": duration_ms,
                            "attempts": attempt + 1,
                            "storage": storage_details
                        }
                    )

                    # Return success response with storage details (AC #4)
                    return {
                        "status": "success",
                        "memory_id": memory_id,
                        "message": result.get("message", "Memory stored successfully"),
                        "storage": storage_details,
                        "content": content
                    }
                else:
                    # Parse error response (AC #4, AC #5)
                    error_msg = f"HTTP {response.status_code}"
                    error_code = None
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                        error_code = error_data.get("error_code")
                    except Exception:
                        error_msg = response.text or error_msg

                    logger.error(
                        "Memory storage failed via direct endpoint",
                        extra={
                            "user_id": user_id,
                            "status_code": response.status_code,
                            "error": error_msg,
                            "error_code": error_code,
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms
                        }
                    )

                    # Handle error codes with appropriate retry logic (AC #5)
                    # VALIDATION_ERROR and INTERNAL_ERROR: No retry
                    if error_code in NO_RETRY_ERRORS:
                        return {
                            "status": "error",
                            "message": f"Failed to store memory: {error_msg}",
                            "error_code": error_code or response.status_code
                        }

                    # Don't retry on client errors (4xx) unless it's a retryable error code
                    if 400 <= response.status_code < 500 and error_code not in ["EMBEDDING_ERROR", "STORAGE_ERROR"]:
                        return {
                            "status": "error",
                            "message": f"Failed to store memory: {error_msg}",
                            "error_code": error_code or response.status_code
                        }

                    # EMBEDDING_ERROR, STORAGE_ERROR, and server errors (5xx): Retry with backoff
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
                        continue

                    return {
                        "status": "error",
                        "message": f"Failed to store memory after {max_retries} attempts: {error_msg}",
                        "error_code": error_code or response.status_code
                    }

            except httpx.TimeoutException as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Timeout storing memory via direct endpoint",
                    extra={
                        "user_id": user_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "duration_ms": duration_ms,
                        "timeout_seconds": 10
                    }
                )

                # Retry on timeout errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                return {
                    "status": "error",
                    "message": f"Timeout after {max_retries} attempts (10s timeout): {str(e)}",
                    "error_code": "TIMEOUT_ERROR"
                }

            except (httpx.NetworkError, httpx.ConnectError) as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Network error storing memory via direct endpoint",
                    extra={
                        "user_id": user_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "duration_ms": duration_ms
                    }
                )

                # Retry on network errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                return {
                    "status": "error",
                    "message": f"Network error after {max_retries} attempts: {str(e)}",
                    "error_code": "NETWORK_ERROR"
                }

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Unexpected error storing memory via direct endpoint",
                    extra={
                        "user_id": user_id,
                        "error": str(e),
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Unexpected error: {str(e)}",
                    "error_code": "INTERNAL_ERROR"
                }

    # Should never reach here
    return {
        "status": "error",
        "message": "Unknown error occurred",
        "error_code": "UNKNOWN_ERROR"
    }


# Store memory tool definition
store_memory_tool = {
    "name": "store_memory",
    "description": """Store a critical memory directly in agentic-memories service.

IMPORTANT: Only use this tool for CRITICAL information that:
1. User explicitly asks you to remember ("Remember that I...", "Don't forget...")
2. Is a permanent preference/constraint ("I'm allergic to...", "Never recommend...")
3. Is a life-changing decision with lasting impact
4. Would be dangerous to forget (medical conditions, safety constraints)

DO NOT use for routine information - background extraction handles that automatically.

Examples of good uses:
- "User is severely allergic to shellfish - carries EpiPen"
- "User's risk tolerance is conservative - never recommend high-risk investments"
- "User's mother passed away in March 2024 - sensitive topic"

Examples of bad uses (handled by background extraction):
- Daily activities or routine conversations
- Temporary preferences or moods
- Information already in their profile
- Topics just discussed""",
    "inputSchema": {
        "type": "object",
        "properties": {
            # Required fields
            "user_id": {
                "type": "string",
                "description": "User identifier for memory storage"
            },
            "content": {
                "type": "string",
                "description": "Pre-formatted memory content to store. Should be a clear, complete statement of what to remember.",
                "maxLength": 5000
            },

            # General fields (always stored in ChromaDB)
            "importance": {
                "type": "number",
                "description": "Importance level from 0.0 to 1.0. Higher values = more critical. Default: 0.8",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8
            },
            "layer": {
                "type": "string",
                "description": "Memory layer for storage. Default: 'semantic' (persistent).",
                "enum": ["short-term", "semantic", "long-term"],
                "default": "semantic"
            },
            "persona_tags": {
                "type": "array",
                "description": "Tags for memory categorization. Max 10 tags.",
                "items": {"type": "string"},
                "maxItems": 10,
                "default": []
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata (source, conversation_id, trigger)",
                "properties": {
                    "source": {"type": "string"},
                    "conversation_id": {"type": "string"},
                    "trigger": {"type": "string"}
                }
            },

            # Optional episodic fields -> triggers episodic_memories write
            "event_timestamp": {
                "type": "string",
                "format": "date-time",
                "description": "When the event occurred (ISO 8601). Include for episodic memories (events with time/place)."
            },
            "location": {
                "type": "string",
                "description": "Where the event happened. Used with event_timestamp for episodic memories."
            },
            "participants": {
                "type": "array",
                "description": "Who was involved in the event. Used with event_timestamp for episodic memories.",
                "items": {"type": "string"}
            },

            # Optional emotional fields -> triggers emotional_memories write
            "emotional_state": {
                "type": "string",
                "description": "Primary emotional state (e.g., 'happy', 'anxious', 'excited'). Include for emotionally significant memories."
            },
            "valence": {
                "type": "number",
                "description": "Emotional valence from -1.0 (negative) to 1.0 (positive). Used with emotional_state.",
                "minimum": -1.0,
                "maximum": 1.0
            },
            "arousal": {
                "type": "number",
                "description": "Emotional arousal from 0.0 (calm) to 1.0 (excited). Used with emotional_state.",
                "minimum": 0.0,
                "maximum": 1.0
            },

            # Optional procedural fields -> triggers procedural_memories write
            "skill_name": {
                "type": "string",
                "description": "Name of skill or procedure being learned. Include for how-to or skill memories."
            },
            "proficiency_level": {
                "type": "string",
                "description": "User's proficiency level. Used with skill_name.",
                "enum": ["beginner", "intermediate", "advanced", "expert"]
            }
        },
        "required": ["user_id", "content"]
    },
    "handler": store_memory_tool_handler
}


async def delete_memory_tool_handler(
    user_id: str,
    memory_id: str,
    reason: str = None
) -> Dict[str, Any]:
    """
    Delete a specific memory by ID from agentic-memories service.

    This tool permanently deletes a memory. The memory ID should be obtained
    from retrieve_memories first. Use when user explicitly asks to forget
    something or when a memory is identified as incorrect.

    Args:
        user_id: User identifier
        memory_id: The ID of the memory to delete (from retrieve_memories)
        reason: Optional explanation for deletion (for audit trail)

    Returns:
        dict: Result with status, deleted flag, memory_id, and message
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/memories/{memory_id}",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                if result.get("deleted"):
                    logger.info(
                        "Memory deleted successfully",
                        extra={
                            "user_id": user_id,
                            "memory_id": memory_id,
                            "reason": reason,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "success",
                        "deleted": True,
                        "memory_id": memory_id,
                        "message": "Memory deleted successfully"
                    }
                else:
                    logger.info(
                        "Memory not found for deletion",
                        extra={
                            "user_id": user_id,
                            "memory_id": memory_id,
                            "reason": reason,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "deleted": False,
                        "memory_id": memory_id,
                        "message": result.get("message", "Memory not found")
                    }

            elif response.status_code == 403:
                logger.warning(
                    "Unauthorized delete attempt",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "reason": reason,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Unauthorized: cannot delete this memory"
                }

            elif response.status_code == 404:
                logger.info(
                    "Memory not found for deletion (404)",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "reason": reason,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Memory not found"
                }

            else:
                logger.error(
                    "Delete memory failed",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "reason": reason,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": f"Delete failed: {response.status_code}"
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Delete memory timed out",
            extra={
                "user_id": user_id,
                "memory_id": memory_id,
                "reason": reason,
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": "Request timed out"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"Delete memory failed: {e}",
            extra={
                "user_id": user_id,
                "memory_id": memory_id,
                "reason": reason,
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": str(e)
        }


# Delete memory tool definition
delete_memory_tool = {
    "name": "delete_memory",
    "description": """Delete a specific memory by ID.

Use this tool when:
- User explicitly asks to forget something ("Forget that I...", "Remove the memory about...")
- A memory is identified as incorrect or outdated
- Removing duplicate or conflicting information
- User wants to correct previously stored information

IMPORTANT WORKFLOW:
1. First use retrieve_memories to find the memory ID
2. Show the user which memory you found and confirm they want to delete it
3. Only delete memories that belong to the current user
4. This action cannot be undone - always confirm with user before proceeding

Args:
    user_id: The user's ID (from system message)
    memory_id: The ID of the memory to delete (from retrieve_memories result)
    reason: Brief explanation for deletion (optional, for audit trail)

Example usage:
User: "Forget what I said about being allergic to shellfish, that was wrong"
1. Call retrieve_memories with query="allergic shellfish"
2. Find the memory with ID "mem_abc123"
3. Confirm: "I found a memory about shellfish allergy. Delete it?"
4. User confirms
5. Call delete_memory with memory_id="mem_abc123", reason="User correction - not actually allergic"
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "memory_id": {
                "type": "string",
                "description": "Memory ID to delete (from retrieve_memories)"
            },
            "reason": {
                "type": "string",
                "description": "Reason for deletion (optional, for audit trail)"
            }
        },
        "required": ["user_id", "memory_id"]
    },
    "handler": delete_memory_tool_handler
}


async def retrieve_memories_tool_handler(
    user_id: str,
    query: str,
    limit: int = 100,
    persona: str = None
) -> Dict[str, Any]:
    """
    Retrieve relevant memories from agentic-memories service for personalized decision support.

    This tool retrieves past conversation memories based on semantic similarity to the query.
    Use this when the user asks for advice, recommendations, or decisions to provide
    personalized responses based on their history.

    Args:
        user_id: User identifier
        query: Search query describing the decision context (e.g., 'stock investment decisions', 'career choices')
        limit: Maximum number of memories to retrieve (default: 100, range: 20-1000)
        persona: Optional persona filter (e.g., 'stock_trader', 'career_advisor') to filter memories by decision-making context

    Returns:
        dict: Result with status, memory_count, and formatted memories for LLM context
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate limit parameter (20-1000 range)
    if limit < 20 or limit > 1000:
        logger.warning(f"Invalid limit {limit}, clamping to range [20, 1000]")
        limit = max(20, min(1000, limit))

    try:
        logger.info(
            "Retrieving memories via MCP tool",
            extra={
                "user_id": user_id,
                "query": query,
                "limit": limit,
                "persona": persona
            }
        )

        # Build query parameters
        # params = {
        #     "user_id": user_id,
        #     "limit": limit
        # }
        # Removing query parameter as it is not supported well by the agentic-memories service
        params = {
            "user_id": user_id,
            "query": query,
            "limit": limit
        }
        if persona:
            params["persona"] = persona

        # Make HTTP request to agentic-memories with 30 second timeout
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{memories_url}/v1/retrieve",
                params=params
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                memories = result.get("results", [])  # API returns "results", not "memories"

                # Log performance warning if exceeded target
                if duration_ms > 300:
                    logger.warning(
                        "Memory retrieval via MCP tool exceeded 300ms target",
                        extra={
                            "user_id": user_id,
                            "query": query,
                            "duration_ms": duration_ms,
                            "memory_count": len(memories),
                            "exceeded_target": True
                        }
                    )
                else:
                    logger.info(
                        "Memories retrieved successfully via MCP tool",
                        extra={
                            "user_id": user_id,
                            "query": query,
                            "memory_count": len(memories),
                            "duration_ms": duration_ms
                        }
                    )

                # Return empty result if no memories found
                if not memories:
                    return {
                        "status": "success",
                        "memory_count": 0,
                        "memories": [],
                        "message": "No past decision history found for this query. Recommendations will be based on general knowledge."
                    }

                # Format memories for LLM context
                # Note: agentic-memories API structure:
                # { "id": "mem_...", "content": "...", "score": 0.X, "metadata": {...} }
                formatted_memories = []
                for i, memory in enumerate(memories, 1):
                    metadata = memory.get("metadata", {})
                    formatted_memory = {
                        "rank": i,
                        "memory_id": memory.get("id", ""),
                        "content": memory.get("content", ""),
                        "layer": memory.get("layer", ""),
                        "type": memory.get("type", ""),
                        "relevance_score": memory.get("score", 0.0),
                        "timestamp": metadata.get("timestamp", ""),
                        "tags": metadata.get("tags", "[]"),
                        "importance": memory.get("importance", 0.0)
                    }
                    formatted_memories.append(formatted_memory)

                return {
                    "status": "success",
                    "memory_count": len(memories),
                    "memories": formatted_memories,
                    "message": f"Retrieved {len(memories)} relevant memories to personalize recommendations."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Memory retrieval failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                # Return empty result on error (graceful degradation)
                return {
                    "status": "error",
                    "memory_count": 0,
                    "memories": [],
                    "message": f"Failed to retrieve memories: {error_msg}. Continuing without memory context.",
                    "error_code": response.status_code
                }

    except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning(
            "Network error retrieving memories via MCP tool, returning empty result (graceful degradation)",
            extra={
                "user_id": user_id,
                "query": query,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )

        # Return empty result on network error (graceful degradation)
        return {
            "status": "error",
            "memory_count": 0,
            "memories": [],
            "message": f"Memory service unavailable: {str(e)}. Continuing without memory context.",
            "error_code": "NETWORK_ERROR"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error retrieving memories via MCP tool",
            extra={
                "user_id": user_id,
                "query": query,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )

        # Return empty result on unexpected error (graceful degradation)
        return {
            "status": "error",
            "memory_count": 0,
            "memories": [],
            "message": f"Unexpected error: {str(e)}. Continuing without memory context.",
            "error_code": "INTERNAL_ERROR"
        }


# Retrieve memories tool definition
retrieve_memories_tool = {
    "name": "retrieve_memories",
    "description": "Retrieve relevant memories from agentic-memories service for personalized decision support. Use this tool when the user asks for advice, recommendations, or decisions (e.g., 'should I invest in X?', 'what do you recommend?', 'help me decide'). The tool retrieves past conversation memories based on semantic similarity to provide personalized responses.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "query": {
                "type": "string",
                "description": "Search query describing the decision context (e.g., 'stock investment decisions', 'career choices', 'AAPL investment')"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of memories to retrieve (default: 100, min:20, max: 1000)",
                "default": 100,
                "minimum": 20,
                "maximum": 1000
            }
        },
        "required": ["user_id", "query"]
    },
    "handler": retrieve_memories_tool_handler
}


async def compact_memories_tool_handler(
    user_id: str,
    skip_reextract: bool = True,
    skip_consolidate: bool = False
) -> Dict[str, Any]:
    """
    Run memory compaction for a user to clean up and consolidate memories.

    Compaction performs:
    - TTL cleanup: Removes expired short-term memories
    - Deduplication: Merges duplicate or near-duplicate memories
    - Consolidation: Combines related memories into "golden records", this is not as expensive as re-extraction but should be skipped unless there are conflicts or duplicates in retreieved memories.
    - Warning: re-extraction is very expensive(time and money) and should be skipped unless user explicitly requests it.

    Args:
        user_id: User identifier
        skip_reextract: Skip very expensive LLM re-extraction unless user explicitly requests it (default: True, recommended)
        skip_consolidate: Skip memory consolidation unless user explicitly requests it (default: True - consolidation runs)

    Returns:
        dict: Result with status and compaction statistics
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    logger.info(
        "Triggering memory compaction",
        extra={
            "user_id": user_id,
            "skip_reextract": skip_reextract,
            "skip_consolidate": skip_consolidate
        }
    )

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for compaction
            response = await client.post(
                f"{memories_url}/v1/maintenance/compact",
                params={
                    "user_id": user_id,
                    "skip_reextract": str(skip_reextract).lower(),
                    "skip_consolidate": str(skip_consolidate).lower()
                }
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                stats = result.get("stats", {})

                logger.info(
                    "Memory compaction completed",
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "status": result.get("status"),
                        "ttl_deleted": stats.get("ttl_deleted", 0),
                        "consolidated_count": stats.get("consolidated_count", 0),
                        "sources_removed": stats.get("sources_removed", 0)
                    }
                )

                return {
                    "status": "success",
                    "message": "Memory compaction completed",
                    "stats": {
                        "ttl_deleted": stats.get("ttl_deleted", 0),
                        "consolidated_count": stats.get("consolidated_count", 0),
                        "sources_removed": stats.get("sources_removed", 0),
                        "applied_upserts": stats.get("applied_upserts", 0),
                        "applied_deletes": stats.get("applied_deletes", 0),
                        "duration_ms": stats.get("duration_ms", duration_ms)
                    }
                }
            else:
                error_msg = f"Compaction failed with status {response.status_code}"
                logger.error(
                    error_msg,
                    extra={
                        "user_id": user_id,
                        "duration_ms": duration_ms,
                        "status_code": response.status_code
                    }
                )
                return {
                    "status": "error",
                    "message": error_msg
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Memory compaction timed out",
            extra={"user_id": user_id, "duration_ms": duration_ms}
        )
        return {
            "status": "error",
            "message": "Compaction timed out after 5 minutes"
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"Memory compaction failed: {e}",
            extra={"user_id": user_id, "duration_ms": duration_ms}
        )
        return {
            "status": "error",
            "message": str(e)
        }


compact_memories_tool = {
    "name": "compact_memories",
    "description": """Run memory compaction to clean up and consolidate user memories.

Use this tool when:
- User asks to clean up or organize their memories
- User reports duplicate or conflicting memories
- Performing periodic maintenance
- After deleting multiple memories

Compaction performs:
- TTL cleanup: Removes expired short-term memories
- Deduplication: Merges duplicate memories
- Consolidation: Combines related memories into cleaner "golden records"

Note: This operation may take 1-2 minutes to complete.
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "skip_reextract": {
                "type": "boolean",
                "description": "EXPENSIVE OPERATION - Skip LLM re-extraction. Default: true. ONLY set to false if user EXPLICITLY requests 'reprocess', 're-extract', or 'rebuild' memories.",
                "default": True
            },
            "skip_consolidate": {
                "type": "boolean",
                "description": "EXPENSIVE OPERATION - Skip memory consolidation. Default: false. ONLY set to true if user EXPLICITLY requests to skip consolidation.",
                "default": False
            }
        },
        "required": ["user_id"]
    },
    "handler": compact_memories_tool_handler
}


async def get_user_profile_tool_handler(
    user_id: str
) -> Dict[str, Any]:
    """
    Retrieve user profile from agentic-memories service.

    The profile includes 21 fields across 5 categories (basics, preferences, goals,
    interests, background) that are automatically extracted from conversations.
    Profile extraction happens during /v1/store calls.
    
    This tool provides you structured data with a well-defined schema for consistent access
    and integration across the system.

    Args:
        user_id: User identifier

    Returns:
        dict: Profile object with all fields and completeness percentage

    Example response:
        {
            "status": "success",
            "user_id": "123456",
            "completeness": 45,
            "basics": {
                "name": "Sarah",
                "age": null,
                "location": "San Francisco",
                "occupation": "Software Engineer",
                "timezone": "US/Pacific",
                "gender": null,
                "pronouns": null
            },
            "preferences": {
                "communication_style": "direct",
                "topics_of_interest": ["AI", "investing"],
                "language": "English",
                "accessibility_needs": null
            },
            "goals": {
                "short_term_goals": ["Learn AI investing"],
                "long_term_goals": ["Build wealth"],
                "values": null
            },
            "interests": {
                "hobbies": null,
                "expertise_areas": ["software engineering"]
            },
            "background": {
                "education": null,
                "work_history": null,
                "life_events": null,
                "relationships": null,
                "health_context": null
            }
        }
    """
    start_time = time.time()

    config = get_config()
    memories_url = config["AGENTIC_MEMORIES_URL"]

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for profile retrieval",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "error": "Invalid user_id: must be non-empty string",
            "user_id": user_id
        }

    try:
        # Make GET request to agentic-memories profile endpoint
        url = f"{memories_url}/v1/profile"
        params = {"user_id": user_id}

        logger.info(
            "Retrieving user profile from agentic-memories",
            extra={
                "user_id": user_id,
                "url": url,
                "params": params
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)

            # Handle HTTP errors
            if response.status_code != 200:
                error_msg = f"Profile retrieval failed with status {response.status_code}"
                logger.error(
                    error_msg,
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "response_text": response.text[:200]
                    }
                )
                return {
                    "status": "error",
                    "error": error_msg,
                    "user_id": user_id,
                    "status_code": response.status_code
                }

            # Parse response
            profile_data = response.json()

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Extract completeness percentage from agentic-memories API format
            # API returns "completeness_pct" (not "completeness")
            completeness = int(profile_data.get("completeness_pct", 0))

            # Extract nested profile data from "profile" object
            # API returns nested structure: {"profile": {"basics": {}, "preferences": {}, ...}}
            profile = profile_data.get("profile", {})

            logger.info(
                "Profile retrieved successfully",
                extra={
                    "user_id": user_id,
                    "completeness": completeness,
                    "duration_ms": duration_ms,
                    "populated_fields": profile_data.get("populated_fields", 0),
                    "total_fields": profile_data.get("total_fields", 21)
                }
            )

            return {
                "status": "success",
                "user_id": user_id,
                "completeness": completeness,
                "basics": profile.get("basics", {}),
                "preferences": profile.get("preferences", {}),
                "goals": profile.get("goals", {}),
                "interests": profile.get("interests", {}),
                "background": profile.get("background", {})
            }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Profile retrieval timed out after {duration_ms}ms"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e)
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }

    except httpx.RequestError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Network error during profile retrieval: {str(e)}"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Unexpected error during profile retrieval: {str(e)}"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }


# Get user profile tool definition
get_user_profile_tool = {
    "name": "get_user_profile",
    "description": (
        "Retrieve user profile with structured data automatically extracted from conversations. "
        "Returns 21 fields across 5 categories: "
        "(1) Basics - name, age, location, occupation, timezone; "
        "(2) Preferences - communication style, topics of interest, language; "
        "(3) Goals - short-term goals, long-term goals, values; "
        "(4) Interests - hobbies, expertise areas; "
        "(5) Background - education, work history, life events. "
        "Includes a completeness percentage (0-100) indicating how much is known. "
        "Use this to personalize responses, understand user context, tailor recommendations, "
        "or reference what you know about them. Fields may be null if not yet learned. Profile extraction happens automatically during conversation storage, you can nudge the user to give you more information if the profile is incomplete."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            }
        },
        "required": ["user_id"]
    },
    "handler": get_user_profile_tool_handler
}


# =============================================================================
# Update User Profile Tool (Story 15.4)
# =============================================================================

# Allowed categories for profile updates
ALLOWED_PROFILE_CATEGORIES = {"basics", "preferences", "goals", "interests", "background"}


async def update_user_profile_tool_handler(
    user_id: str,
    category: str,
    field_name: str,
    value: Any,
    reason: str = None
) -> Dict[str, Any]:
    """
    Update a specific field in the user's profile in agentic-memories.

    This tool makes a PUT request to the agentic-memories profile API to update
    a specific field. Use when the user explicitly shares new information about
    themselves that should be persisted.

    Args:
        user_id: User identifier
        category: Profile category (basics, preferences, goals, interests, background)
        field_name: Field name within the category (e.g., 'location', 'communication_style')
        value: New value (string, number, boolean, or array)
        reason: Optional reason for the update (for audit trail)

    Returns:
        dict: Result with status, updated value, previous value, and metadata
    """
    start_time = time.time()

    # Validate category against allowed list (AC #2)
    if category not in ALLOWED_PROFILE_CATEGORIES:
        logger.warning(
            "Invalid category for profile update",
            extra={
                "user_id": user_id,
                "category": category,
                "field_name": field_name,
                "error": "VALIDATION_ERROR"
            }
        )
        return {
            "status": "error",
            "error_message": f"Invalid category '{category}'. Allowed: {', '.join(sorted(ALLOWED_PROFILE_CATEGORIES))}",
            "error_code": "VALIDATION_ERROR"
        }

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Build request payload (AC #4: source="llm_explicit" for audit trail)
    payload = {
        "user_id": user_id,
        "value": value,
        "source": "llm_explicit"
    }

    if reason:
        payload["reason"] = reason

    # Retry configuration: exponential backoff 1s, 2s, 4s (AC #7)
    max_retries = 3
    retry_delays = [1, 2, 4]

    # 10 second timeout per request
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Updating user profile field",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "attempt": attempt + 1,
                        "has_reason": reason is not None
                    }
                )

                response = await client.put(
                    f"{memories_url}/v1/profile/{category}/{field_name}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                duration_ms = int((time.time() - start_time) * 1000)

                # Success response (AC #1)
                if response.status_code in (200, 201):
                    result = response.json()

                    logger.info(
                        "Profile field updated successfully",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "duration_ms": duration_ms,
                            "attempts": attempt + 1
                        }
                    )

                    return {
                        "status": "success",
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "value": result.get("value"),
                        "previous_value": result.get("previous_value"),
                        "confidence": 100.0,
                        "last_updated": result.get("last_updated")
                    }

                # Handle 404 Not Found (AC #5)
                elif response.status_code == 404:
                    logger.warning(
                        "Profile field not found",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": f"Profile field not found: {category}/{field_name}",
                        "error_code": "NOT_FOUND"
                    }

                # Handle 400 Bad Request (AC #6)
                elif response.status_code == 400:
                    error_msg = "Invalid request"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except Exception:
                        error_msg = response.text or error_msg

                    logger.warning(
                        "Profile update validation error",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "error": error_msg,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": error_msg,
                        "error_code": "VALIDATION_ERROR"
                    }

                # Handle 5xx Server Errors - Retry with backoff (AC #7)
                elif response.status_code >= 500:
                    logger.warning(
                        "Profile update server error, will retry",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms
                        }
                    )

                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
                        continue

                    return {
                        "status": "error",
                        "error_message": f"Server error after {max_retries} attempts",
                        "error_code": "SERVER_ERROR"
                    }

                # Other error codes
                else:
                    logger.error(
                        "Profile update failed with unexpected status",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": f"HTTP {response.status_code}",
                        "error_code": response.status_code
                    }

            except httpx.TimeoutException:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "Profile update timeout, will retry",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "attempt": attempt + 1,
                        "duration_ms": duration_ms
                    }
                )

                # Retry on timeout (AC #7)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                return {
                    "status": "error",
                    "error_message": f"Timeout after {max_retries} attempts",
                    "error_code": "TIMEOUT_ERROR"
                }

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Unexpected error updating profile",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "error": str(e),
                        "duration_ms": duration_ms
                    },
                    exc_info=True
                )
                return {
                    "status": "error",
                    "error_message": str(e),
                    "error_code": "INTERNAL_ERROR"
                }

    # Should never reach here
    return {
        "status": "error",
        "error_message": "Unknown error occurred",
        "error_code": "UNKNOWN"
    }


# Update user profile tool definition
update_user_profile_tool = {
    "name": "update_user_profile",
    "description": """Update a specific field in the user's profile.

Use this tool when the user:
1. Explicitly tells you new information about themselves ("I just moved to Seattle")
2. Corrects previously known information ("Actually, I prefer formal communication")
3. Expresses a preference or goal change ("I'm now focusing on retirement planning")

Categories and common fields:
- basics: name, age, location, occupation, timezone
- preferences: communication_style, topics_of_interest, response_length
- goals: short_term, long_term, current_focus
- interests: hobbies, favorite_topics, dislikes
- background: education, work_history, family

Do NOT use for:
- Information already in their profile (check first with get_user_profile)
- Temporary moods or states ("I'm feeling tired today")
- Speculative information ("You seem like someone who...")""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "category": {
                "type": "string",
                "enum": ["basics", "preferences", "goals", "interests", "background"],
                "description": "Profile category to update"
            },
            "field_name": {
                "type": "string",
                "description": "Field name within the category (e.g., 'location', 'communication_style')"
            },
            "value": {
                "description": "New value (string, number, boolean, or array)"
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for the update (for audit trail)"
            }
        },
        "required": ["user_id", "category", "field_name", "value"]
    },
    "handler": update_user_profile_tool_handler
}


# =============================================================================
# Portfolio Management Tools (Epic 10)
# =============================================================================

import re
import json
import redis.asyncio as redis

# Price cache TTL: 15 minutes (900 seconds)
PRICE_CACHE_TTL = 900

# Ticker validation pattern: 1-10 uppercase alphanumeric + dots (for BRK.B style)
TICKER_PATTERN = re.compile(r'^[A-Z0-9\.]{1,10}$')


def normalize_ticker(ticker: str) -> Optional[str]:
    """
    Normalize ticker to uppercase and validate format.

    Converts hyphens to dots (BRK-B -> BRK.B) for yfinance compatibility.

    Args:
        ticker: Stock ticker symbol (e.g., 'aapl', 'GOOGL', 'BRK.B', 'BRK-B')

    Returns:
        Normalized uppercase ticker or None if invalid
    """
    if not ticker:
        return None

    # Uppercase, strip whitespace, convert hyphens to dots (BRK-B -> BRK.B)
    normalized = ticker.upper().strip().replace('-', '.')

    if not normalized:
        return None

    if not TICKER_PATTERN.match(normalized):
        logger.warning(f"Invalid ticker format rejected: {ticker}")
        return None

    return normalized


async def batch_fetch_prices_with_cache(
    tickers: list,
    redis_client: Optional[redis.Redis] = None
) -> tuple[Dict[str, float], list]:
    """
    Fetch current prices for multiple tickers with Redis caching.

    Uses single batch call to yfinance for uncached tickers.
    Caches fetched prices in Redis with 15-minute TTL.

    Args:
        tickers: List of ticker symbols (already normalized to uppercase)
        redis_client: Optional Redis client. Creates new connection if not provided.

    Returns:
        tuple: (prices_dict, failed_tickers_list)
            - prices_dict: {ticker: price} for successful fetches
            - failed_tickers_list: tickers that failed to fetch
    """
    if not tickers:
        return {}, []

    prices = {}
    failed_tickers = []
    tickers_to_fetch = []

    # Get Redis connection
    own_redis = False
    if redis_client is None:
        try:
            config = get_config()
            redis_host = config.get("REDIS_HOST", "redis")
            redis_port = int(config.get("REDIS_PORT", 6379))
            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            own_redis = True
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for price caching: {e}")
            redis_client = None

    # Check cache for each ticker
    for ticker in tickers:
        if redis_client:
            try:
                cache_key = f"stock_price:{ticker}"
                cached_price = await redis_client.get(cache_key)
                if cached_price:
                    prices[ticker] = float(cached_price)
                    logger.debug(f"Price cache hit for {ticker}: {cached_price}")
                    continue
            except Exception as e:
                logger.warning(f"Redis cache check failed for {ticker}: {e}")

        tickers_to_fetch.append(ticker)

    # Batch fetch uncached tickers from yfinance
    if tickers_to_fetch:
        try:
            logger.info(
                "Batch fetching prices from yfinance",
                extra={
                    "tickers": tickers_to_fetch,
                    "count": len(tickers_to_fetch)
                }
            )

            # Single batch call to yfinance
            data = yf.download(
                tickers_to_fetch,
                period="1d",
                progress=False,
                threads=True
            )

            # Check if we got any data
            if data.empty:
                logger.warning("yfinance returned empty DataFrame")
                failed_tickers.extend(tickers_to_fetch)
            else:
                # Handle both single and multi-ticker response formats
                # yfinance returns different column structures:
                # - Single ticker: columns are ['Open', 'High', 'Low', 'Close', 'Volume']
                # - Multiple tickers: MultiIndex columns like [('Close', 'AAPL'), ('Close', 'GOOGL')]

                has_multiindex = isinstance(data.columns, pd.MultiIndex)

                for ticker in tickers_to_fetch:
                    try:
                        price = None

                        if has_multiindex:
                            # Multi-ticker format: access via ('Close', ticker)
                            if ('Close', ticker) in data.columns:
                                price_series = data[('Close', ticker)]
                                if not price_series.empty:
                                    price = price_series.iloc[-1]
                        else:
                            # Single ticker format: access via 'Close'
                            if 'Close' in data.columns:
                                price_series = data['Close']
                                if not price_series.empty:
                                    price = price_series.iloc[-1]

                        if price is not None and pd.notna(price):
                            prices[ticker] = round(float(price), 2)
                            # Cache the price
                            if redis_client:
                                try:
                                    await redis_client.setex(
                                        f"stock_price:{ticker}",
                                        PRICE_CACHE_TTL,
                                        str(prices[ticker])
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to cache price for {ticker}: {e}")
                        else:
                            failed_tickers.append(ticker)

                    except Exception as e:
                        logger.warning(f"Failed to parse price for {ticker}: {e}")
                        failed_tickers.append(ticker)

            logger.info(
                "Batch price fetch completed",
                extra={
                    "fetched_count": len(tickers_to_fetch) - len([t for t in failed_tickers if t in tickers_to_fetch]),
                    "failed_count": len([t for t in failed_tickers if t in tickers_to_fetch])
                }
            )

        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")
            # All tickers in this batch failed
            failed_tickers.extend([t for t in tickers_to_fetch if t not in prices])

    # Close Redis connection if we created it
    if own_redis and redis_client:
        try:
            await redis_client.close()
        except Exception:
            pass

    return prices, failed_tickers


async def get_portfolio_tool_handler(
    user_id: str,
    include_prices: bool = False
) -> Dict[str, Any]:
    """
    Get user's investment portfolio holdings from agentic-memories service.

    This tool provides structured data with a well-defined schema containing the user's
    stock positions, quantities, and purchase information. Use this to:
    - Answer questions about what stocks/assets the user owns
    - Calculate portfolio value, gains/losses, and performance metrics
    - Provide personalized investment insights based on their actual holdings
    - Compare their positions against market trends or news
    - Suggest rebalancing or diversification strategies
    - Any other questions about stocks or investments the user may have.
    - Use this tool in conjuction with other tools to get a comprehensive understanding of the user's investment situation.

    The holdings data includes ticker symbols, share quantities, purchase prices,
    and dates—everything needed to analyze their investment situation.

    When include_prices=True, enriches holdings with current market prices and
    calculates performance metrics (gain/loss, percentages, portfolio totals).

    Args:
        user_id: User identifier
        include_prices: If True, fetch current prices and calculate performance metrics.
                       Defaults to False for fast "what do I own?" queries.

    Returns:
        dict: Portfolio with holdings array (ticker, shares, cost_basis, purchase_date),
              total_holdings count, and last_updated timestamp.
              When include_prices=True, also includes current_price, current_value,
              gain_loss, gain_loss_pct per holding, plus portfolio totals.
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for portfolio retrieval",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string",
            "user_id": user_id
        }

    try:
        logger.info(
            "Retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "include_prices": include_prices,
                "url": memories_url
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{memories_url}/v1/portfolio",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                holdings = result.get("holdings", [])

                logger.info(
                    "Portfolio retrieved successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "holdings_count": len(holdings),
                        "include_prices": include_prices,
                        "duration_ms": duration_ms
                    }
                )

                # Build base response
                response_data = {
                    "status": "success",
                    "user_id": result.get("user_id", user_id),
                    "holdings": holdings,
                    "total_holdings": result.get("total_holdings", len(holdings)),
                    "last_updated": result.get("last_updated")
                }

                # Enrich with prices if requested
                if include_prices and holdings:
                    # Extract tickers from holdings
                    tickers = [h.get("ticker") for h in holdings if h.get("ticker")]

                    # Batch fetch prices with caching
                    prices, failed_tickers = await batch_fetch_prices_with_cache(tickers)

                    # Track totals for portfolio summary
                    total_value = 0.0
                    total_cost_basis = 0.0
                    price_fetch_errors = []

                    # Enrich each holding with price data
                    for holding in holdings:
                        ticker = holding.get("ticker")
                        if not ticker:
                            continue

                        shares = holding.get("shares", 0) or 0
                        avg_price = holding.get("avg_price", 0) or 0

                        if ticker in prices:
                            current_price = prices[ticker]
                            current_value = round(shares * current_price, 2)
                            cost_basis = round(shares * avg_price, 2)
                            gain_loss = round(current_value - cost_basis, 2)
                            gain_loss_pct = round((gain_loss / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

                            holding["current_price"] = current_price
                            holding["current_value"] = current_value
                            holding["cost_basis"] = cost_basis
                            holding["gain_loss"] = gain_loss
                            holding["gain_loss_pct"] = gain_loss_pct

                            # Add to portfolio totals
                            total_value += current_value
                            total_cost_basis += cost_basis
                        else:
                            # Price fetch failed for this ticker
                            holding["current_price"] = None
                            holding["current_value"] = None
                            holding["cost_basis"] = round(shares * avg_price, 2) if avg_price else None
                            holding["gain_loss"] = None
                            holding["gain_loss_pct"] = None
                            if ticker in failed_tickers:
                                price_fetch_errors.append(ticker)

                    # Calculate portfolio totals
                    total_gain_loss = round(total_value - total_cost_basis, 2)
                    total_gain_loss_pct = round((total_gain_loss / total_cost_basis) * 100, 2) if total_cost_basis > 0 else 0.0

                    response_data["total_value"] = round(total_value, 2)
                    response_data["total_cost_basis"] = round(total_cost_basis, 2)
                    response_data["total_gain_loss"] = total_gain_loss
                    response_data["total_gain_loss_pct"] = total_gain_loss_pct
                    response_data["price_fetch_errors"] = price_fetch_errors
                    response_data["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                    logger.info(
                        "Portfolio enriched with prices",
                        extra={
                            "user_id": user_id,
                            "total_value": total_value,
                            "total_gain_loss_pct": total_gain_loss_pct,
                            "price_errors_count": len(price_fetch_errors)
                        }
                    )

                return response_data

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Portfolio retrieval failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to retrieve portfolio: {error_msg}",
                    "error_code": response.status_code,
                    "user_id": user_id
                }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Portfolio retrieval timed out via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service timed out. Please try again.",
            "error_code": "TIMEOUT",
            "user_id": user_id
        }

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Network error retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service unavailable. Please try again later.",
            "error_code": "NETWORK_ERROR",
            "user_id": user_id
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error retrieving portfolio via MCP tool",
            extra={
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR",
            "user_id": user_id
        }


# Get portfolio tool definition
get_portfolio_tool = {
    "name": "get_portfolio",
    "description": (
        "Get user's investment portfolio holdings. Returns structured data with "
        "ticker symbols, share counts, average purchase prices, and dates for all "
        "stocks, ETFs, and assets the user owns. Use this to: "
        "(1) Answer questions about what stocks/assets they own, "
        "(2) Calculate portfolio value, gains/losses, and performance metrics, "
        "(3) Provide personalized investment insights based on actual holdings, "
        "(4) Compare positions against market trends or news, "
        "(5) Suggest rebalancing or diversification strategies. "
        "Set include_prices=true when user asks 'how is my portfolio doing?' to get "
        "current prices, values, and gain/loss calculations. Use include_prices=false "
        "(default) for fast 'what do I own?' queries."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "include_prices": {
                "type": "boolean",
                "description": "If true, fetch current market prices and calculate performance metrics (current_value, gain_loss, gain_loss_pct). Adds ~1-2s latency. Default: false",
                "default": False
            }
        },
        "required": ["user_id"]
    },
    "handler": get_portfolio_tool_handler
}


async def add_holding_tool_handler(
    user_id: str,
    ticker: str,
    asset_name: str = None,
    shares: float = None,
    avg_price: float = None
) -> Dict[str, Any]:
    """
    Add or update a stock holding in user's portfolio.

    Uses UPSERT behavior: creates new holding if ticker doesn't exist,
    updates existing holding if it does.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        asset_name: Optional human-readable name (e.g., 'Apple Inc.')
        shares: Optional number of shares
        avg_price: Optional average purchase price per share

    Returns:
        dict: Result with holding details and created/updated flag
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for add_holding",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for add_holding",
            extra={"user_id": user_id, "ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters (e.g., AAPL, GOOGL, BRK.B)."
        }

    # Build request payload
    payload = {
        "user_id": user_id,
        "ticker": normalized_ticker
    }
    if asset_name:
        payload["asset_name"] = asset_name
    if shares is not None:
        payload["shares"] = shares
    if avg_price is not None:
        payload["avg_price"] = avg_price

    try:
        logger.info(
            "Adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "shares": shares,
                "avg_price": avg_price
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{memories_url}/v1/portfolio/holding",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code in (200, 201):
                result = response.json()
                created = response.status_code == 201 or result.get("created", False)

                logger.info(
                    "Holding added/updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "was_created": created,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "holding": {
                        "id": result.get("id"),
                        "ticker": result.get("ticker"),
                        "asset_name": result.get("asset_name"),
                        "shares": result.get("shares"),
                        "avg_price": result.get("avg_price"),
                        "first_acquired": result.get("first_acquired"),
                        "last_updated": result.get("last_updated")
                    },
                    "created": created,
                    "message": f"{'Added' if created else 'Updated'} {normalized_ticker} in your portfolio."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Add holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to add holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Add holding timed out via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service timed out. Please try again.",
            "error_code": "TIMEOUT"
        }

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Network error adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "message": "Portfolio service unavailable. Please try again later.",
            "error_code": "NETWORK_ERROR"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unexpected error adding holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "error_code": "INTERNAL_ERROR"
        }


# Add holding tool definition
add_holding_tool = {
    "name": "add_holding",
    "description": "Add or update a stock holding in user's portfolio. Use this tool when the user mentions buying stocks, adding to their portfolio, or wants to record a purchase. If the ticker already exists, it will update the existing holding (UPSERT behavior).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'BRK.B'). Will be normalized to uppercase."
            },
            "asset_name": {
                "type": "string",
                "description": "Optional human-readable name for the asset (e.g., 'Apple Inc.')"
            },
            "shares": {
                "type": "number",
                "description": "Number of shares owned"
            },
            "avg_price": {
                "type": "number",
                "description": "Average purchase price per share in USD"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": add_holding_tool_handler
}


async def update_holding_tool_handler(
    user_id: str,
    ticker: str,
    asset_name: str = None,
    shares: float = None,
    avg_price: float = None
) -> Dict[str, Any]:
    """
    Update an existing stock holding in user's portfolio.

    Unlike add_holding (which creates if not exists), this tool returns 404
    if the holding doesn't exist. Supports partial updates - only provided
    fields are updated.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        asset_name: Optional new asset name
        shares: Optional new number of shares
        avg_price: Optional new average purchase price

    Returns:
        dict: Updated holding details or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    # Build request payload (only include provided fields)
    payload = {"user_id": user_id}
    if asset_name is not None:
        payload["asset_name"] = asset_name
    if shares is not None:
        payload["shares"] = shares
    if avg_price is not None:
        payload["avg_price"] = avg_price

    try:
        logger.info(
            "Updating holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker,
                "updates": {k: v for k, v in payload.items() if k != "user_id"}
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.put(
                f"{memories_url}/v1/portfolio/holding/{normalized_ticker}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                logger.info(
                    "Holding updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "ticker": result.get("ticker"),
                    "asset_name": result.get("asset_name"),
                    "shares": result.get("shares"),
                    "avg_price": result.get("avg_price"),
                    "first_acquired": result.get("first_acquired"),
                    "last_updated": result.get("last_updated"),
                    "message": f"Updated {normalized_ticker} in your portfolio."
                }

            elif response.status_code == 404:
                logger.info(
                    "Holding not found for update",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Holding not found: You don't have {normalized_ticker} in your portfolio.",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Update holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to update holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Update holding timed out", extra={"user_id": user_id, "ticker": normalized_ticker, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error updating holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error updating holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Update holding tool definition
update_holding_tool = {
    "name": "update_holding",
    "description": "Update an existing stock holding in user's portfolio. Use this when the user wants to change the number of shares or average price of a stock they already own. Returns error if the holding doesn't exist (use add_holding to create new holdings).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol to update (e.g., 'AAPL')"
            },
            "asset_name": {
                "type": "string",
                "description": "Optional new human-readable name for the asset"
            },
            "shares": {
                "type": "number",
                "description": "New number of shares owned"
            },
            "avg_price": {
                "type": "number",
                "description": "New average purchase price per share in USD"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": update_holding_tool_handler
}


async def remove_holding_tool_handler(
    user_id: str,
    ticker: str
) -> Dict[str, Any]:
    """
    Remove a stock holding from user's portfolio.

    Deletes the holding identified by user_id + ticker.
    Returns 404 if holding doesn't exist.

    Args:
        user_id: User identifier
        ticker: Stock ticker symbol to remove (e.g., 'AAPL')

    Returns:
        dict: Confirmation of deletion or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    try:
        logger.info(
            "Removing holding via MCP tool",
            extra={
                "user_id": user_id,
                "ticker": normalized_ticker
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/portfolio/holding/{normalized_ticker}",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                ticker_name = normalized_ticker
                if response.status_code == 200:
                    try:
                        result = response.json()
                        ticker_name = result.get("ticker", normalized_ticker)
                    except Exception:
                        pass

                logger.info(
                    "Holding removed successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "ticker": ticker_name,
                    "message": f"Removed {normalized_ticker} from your portfolio."
                }

            elif response.status_code == 404:
                logger.info(
                    "Holding not found for removal",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Holding not found: You don't have {normalized_ticker} in your portfolio.",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Remove holding failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "ticker": normalized_ticker,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to remove holding: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Remove holding timed out", extra={"user_id": user_id, "ticker": normalized_ticker, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error removing holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error removing holding", extra={"user_id": user_id, "ticker": normalized_ticker, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Remove holding tool definition
remove_holding_tool = {
    "name": "remove_holding",
    "description": "Remove a stock holding from user's portfolio. Use this when the user has sold all shares of a stock and wants it removed from their portfolio. Returns error if the holding doesn't exist.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol to remove (e.g., 'AAPL')"
            }
        },
        "required": ["user_id", "ticker"]
    },
    "handler": remove_holding_tool_handler
}


async def clear_portfolio_tool_handler(
    user_id: str,
    confirmation: str = None
) -> Dict[str, Any]:
    """
    Clear ALL holdings from user's portfolio.

    WARNING: This is a destructive operation that removes ALL holdings.
    Requires confirmation parameter set to 'DELETE_ALL' for safety.

    Args:
        user_id: User identifier
        confirmation: Must be exactly 'DELETE_ALL' to proceed

    Returns:
        dict: Count of deleted holdings or error
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Validate confirmation
    if confirmation != "DELETE_ALL":
        logger.warning(
            "Clear portfolio called without proper confirmation",
            extra={"user_id": user_id, "confirmation": confirmation}
        )
        return {
            "status": "error",
            "message": "Confirmation required. This will delete ALL holdings in the portfolio. Set confirmation='DELETE_ALL' to proceed.",
            "error_code": "CONFIRMATION_REQUIRED"
        }

    try:
        logger.info(
            "Clearing portfolio via MCP tool",
            extra={"user_id": user_id}
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/portfolio",
                params={"user_id": user_id, "confirmation": "DELETE_ALL"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                holdings_removed = 0
                if response.status_code == 200:
                    try:
                        result = response.json()
                        holdings_removed = result.get("holdings_removed", 0)
                    except Exception:
                        pass

                logger.info(
                    "Portfolio cleared successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "holdings_removed": holdings_removed,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "holdings_removed": holdings_removed,
                    "message": f"Cleared your entire portfolio. {holdings_removed} holding{'s' if holdings_removed != 1 else ''} removed."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Clear portfolio failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to clear portfolio: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Clear portfolio timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error clearing portfolio", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Portfolio service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error clearing portfolio", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Clear portfolio tool definition
clear_portfolio_tool = {
    "name": "clear_portfolio",
    "description": "DANGER: Clear ALL holdings from user's portfolio. This permanently deletes every stock in the portfolio. Only use when the user explicitly confirms they want to remove everything. Requires confirmation='DELETE_ALL' parameter.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "confirmation": {
                "type": "string",
                "description": "Must be exactly 'DELETE_ALL' to confirm this destructive operation",
                "enum": ["DELETE_ALL"]
            }
        },
        "required": ["user_id", "confirmation"]
    },
    "handler": clear_portfolio_tool_handler
}


# =============================================================================
# Stock Market Analysis Tools (Epic 10 - Story 10.6)
# =============================================================================

import yfinance as yf
import pandas as pd


def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: Series of closing prices
        period: RSI period (default 14 days)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None

    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Avoid division by zero
    if loss.iloc[-1] == 0:
        return 100.0 if gain.iloc[-1] > 0 else 50.0

    rs = gain.iloc[-1] / loss.iloc[-1]
    rsi = 100 - (100 / (1 + rs))

    return round(rsi, 2)


def format_market_cap(market_cap: Optional[int]) -> Optional[str]:
    """
    Format market cap into human-readable string.

    Args:
        market_cap: Market capitalization in raw number

    Returns:
        Formatted string (e.g., "2.8T", "500B", "50M") or None
    """
    if market_cap is None:
        return None

    if market_cap >= 1_000_000_000_000:
        return f"{market_cap / 1_000_000_000_000:.1f}T"
    elif market_cap >= 1_000_000_000:
        return f"{market_cap / 1_000_000_000:.1f}B"
    elif market_cap >= 1_000_000:
        return f"{market_cap / 1_000_000:.1f}M"
    else:
        return str(market_cap)


def determine_trend(ma_50: Optional[float], ma_200: Optional[float], current_price: Optional[float]) -> str:
    """
    Determine trend based on moving averages.

    Args:
        ma_50: 50-day moving average
        ma_200: 200-day moving average
        current_price: Current stock price

    Returns:
        Trend string: "bullish", "bearish", or "neutral"
    """
    if ma_50 is None or ma_200 is None or current_price is None:
        return "neutral"

    # Golden cross: 50 MA above 200 MA = bullish
    # Death cross: 50 MA below 200 MA = bearish
    if ma_50 > ma_200 and current_price > ma_50:
        return "bullish"
    elif ma_50 < ma_200 and current_price < ma_50:
        return "bearish"
    else:
        return "neutral"


async def analyze_stock_tool_handler(
    ticker: str,
    include_technicals: bool = True
) -> Dict[str, Any]:
    """
    Analyze a stock and return comprehensive market data.

    Fetches real-time price data, fundamentals, and optionally technical indicators
    via Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        include_technicals: Whether to include RSI, moving averages, trend analysis

    Returns:
        dict: Comprehensive stock analysis including price, fundamentals, and technicals
    """
    start_time = time.time()

    # Normalize ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for analyze_stock",
            extra={"ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters (e.g., AAPL, GOOGL, BRK.B)."
        }

    try:
        logger.info(
            "Analyzing stock via MCP tool",
            extra={
                "ticker": normalized_ticker,
                "include_technicals": include_technicals
            }
        )

        # Create yfinance Ticker object
        stock = yf.Ticker(normalized_ticker)

        # Get stock info (fundamentals)
        info = stock.info

        # Check if ticker is valid (yfinance returns empty info for invalid tickers)
        if not info or info.get("regularMarketPrice") is None:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Stock not found",
                extra={
                    "ticker": normalized_ticker,
                    "duration_ms": duration_ms
                }
            )
            return {
                "status": "error",
                "message": f"Could not find stock data for ticker '{normalized_ticker}'. Please check the symbol and try again.",
                "ticker": normalized_ticker
            }

        # Extract basic price data
        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        previous_close = info.get("regularMarketPreviousClose") or info.get("previousClose")

        # Calculate daily change
        change_1d = None
        change_1d_pct = None
        if current_price and previous_close:
            change_1d = round(current_price - previous_close, 2)
            change_1d_pct = round((change_1d / previous_close) * 100, 2)

        # Build basic result
        result = {
            "status": "success",
            "ticker": normalized_ticker,
            "name": info.get("shortName") or info.get("longName"),
            "current_price": current_price,
            "previous_close": previous_close,
            "change_1d": change_1d,
            "change_1d_pct": change_1d_pct,
            "day_high": info.get("regularMarketDayHigh") or info.get("dayHigh"),
            "day_low": info.get("regularMarketDayLow") or info.get("dayLow"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "market_cap": format_market_cap(info.get("marketCap")),
            "market_cap_raw": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "dividend_yield": info.get("dividendYield"),
            "volume": info.get("regularMarketVolume") or info.get("volume"),
            "avg_volume": info.get("averageVolume"),
            "exchange": info.get("exchange"),
            "currency": info.get("currency", "USD")
        }

        # Calculate volume analysis
        if result["volume"] and result["avg_volume"]:
            if result["volume"] > result["avg_volume"] * 1.2:
                result["volume_analysis"] = "above_average"
            elif result["volume"] < result["avg_volume"] * 0.8:
                result["volume_analysis"] = "below_average"
            else:
                result["volume_analysis"] = "average"
        else:
            result["volume_analysis"] = "unknown"

        # Add technical indicators if requested
        if include_technicals:
            try:
                # Get historical data for technical analysis (need ~200 days for 200 MA)
                history = stock.history(period="1y")

                if len(history) > 0:
                    close_prices = history["Close"]

                    # RSI (14-day)
                    result["rsi_14"] = calculate_rsi(close_prices, 14)

                    # Moving averages
                    if len(close_prices) >= 50:
                        result["ma_50"] = round(close_prices.rolling(window=50).mean().iloc[-1], 2)
                    else:
                        result["ma_50"] = None

                    if len(close_prices) >= 200:
                        result["ma_200"] = round(close_prices.rolling(window=200).mean().iloc[-1], 2)
                    else:
                        result["ma_200"] = None

                    # Trend determination
                    result["trend"] = determine_trend(
                        result.get("ma_50"),
                        result.get("ma_200"),
                        current_price
                    )

                    # Price vs 52-week range
                    if result["52_week_high"] and result["52_week_low"] and current_price:
                        range_size = result["52_week_high"] - result["52_week_low"]
                        if range_size > 0:
                            result["52_week_position"] = round(
                                ((current_price - result["52_week_low"]) / range_size) * 100, 1
                            )
                else:
                    result["rsi_14"] = None
                    result["ma_50"] = None
                    result["ma_200"] = None
                    result["trend"] = "unknown"

            except Exception as e:
                logger.warning(
                    "Failed to calculate technical indicators",
                    extra={
                        "ticker": normalized_ticker,
                        "error": str(e)
                    }
                )
                result["rsi_14"] = None
                result["ma_50"] = None
                result["ma_200"] = None
                result["trend"] = "unknown"

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Stock analysis completed successfully",
            extra={
                "ticker": normalized_ticker,
                "current_price": current_price,
                "change_1d_pct": change_1d_pct,
                "duration_ms": duration_ms
            }
        )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error analyzing stock",
            extra={
                "ticker": normalized_ticker,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to analyze stock: {str(e)}",
            "ticker": normalized_ticker
        }


# Analyze stock tool definition
analyze_stock_tool = {
    "name": "analyze_stock",
    "description": "Analyze a stock and get comprehensive market data including current price, daily change, 52-week range, P/E ratio, market cap, volume, and technical indicators (RSI, moving averages, trend). Use this tool when the user asks about a specific stock, wants price information, or asks 'how is [stock] doing?'",
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'TSLA', 'BRK.B')"
            },
            "include_technicals": {
                "type": "boolean",
                "description": "Whether to include technical indicators (RSI, moving averages, trend). Default: true",
                "default": True
            }
        },
        "required": ["ticker"]
    },
    "handler": analyze_stock_tool_handler
}


async def get_stock_history_tool_handler(
    ticker: str,
    period: str = "1mo"
) -> Dict[str, Any]:
    """
    Get historical price data for a stock.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        period: Time period - one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max

    Returns:
        dict: Historical OHLCV data with summary statistics
    """
    start_time = time.time()

    # Normalize ticker
    normalized_ticker = normalize_ticker(ticker)
    if normalized_ticker is None:
        logger.warning(
            "Invalid ticker format for get_stock_history",
            extra={"ticker": ticker}
        )
        return {
            "status": "error",
            "message": f"Invalid ticker format: '{ticker}'. Ticker must be 1-10 alphanumeric characters."
        }

    # Validate period
    valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
    if period not in valid_periods:
        return {
            "status": "error",
            "message": f"Invalid period: '{period}'. Valid periods: {', '.join(valid_periods)}"
        }

    try:
        logger.info(
            "Getting stock history via MCP tool",
            extra={
                "ticker": normalized_ticker,
                "period": period
            }
        )

        # Create yfinance Ticker object
        stock = yf.Ticker(normalized_ticker)

        # Get historical data
        history = stock.history(period=period)

        if history.empty:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "No historical data found",
                extra={
                    "ticker": normalized_ticker,
                    "period": period,
                    "duration_ms": duration_ms
                }
            )
            return {
                "status": "error",
                "message": f"No historical data found for ticker '{normalized_ticker}'. Please check the symbol.",
                "ticker": normalized_ticker
            }

        # Convert to list of OHLCV records
        data_points = []
        for date, row in history.iterrows():
            data_points.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })

        # Calculate summary statistics
        close_prices = history["Close"]
        start_price = close_prices.iloc[0]
        end_price = close_prices.iloc[-1]
        period_change = round(end_price - start_price, 2)
        period_change_pct = round((period_change / start_price) * 100, 2)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Stock history retrieved successfully",
            extra={
                "ticker": normalized_ticker,
                "period": period,
                "data_points": len(data_points),
                "duration_ms": duration_ms
            }
        )

        return {
            "status": "success",
            "ticker": normalized_ticker,
            "period": period,
            "data_points": len(data_points),
            "summary": {
                "start_date": data_points[0]["date"],
                "end_date": data_points[-1]["date"],
                "start_price": round(start_price, 2),
                "end_price": round(end_price, 2),
                "period_change": period_change,
                "period_change_pct": period_change_pct,
                "period_high": round(close_prices.max(), 2),
                "period_low": round(close_prices.min(), 2),
                "avg_volume": int(history["Volume"].mean())
            },
            "history": data_points
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error getting stock history",
            extra={
                "ticker": normalized_ticker,
                "period": period,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to get stock history: {str(e)}",
            "ticker": normalized_ticker
        }


# Get stock history tool definition
get_stock_history_tool = {
    "name": "get_stock_history",
    "description": "Get historical price data for a stock. Returns daily OHLCV (Open, High, Low, Close, Volume) data for the specified time period. Use this when the user asks about price history, trends over time, or wants to see how a stock has performed over a specific period.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL')"
            },
            "period": {
                "type": "string",
                "description": "Time period for history. Options: 1d (1 day), 5d (5 days), 1mo (1 month), 3mo (3 months), 6mo (6 months), 1y (1 year), 2y (2 years), 5y (5 years), max (all available). Default: 1mo",
                "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
                "default": "1mo"
            }
        },
        "required": ["ticker"]
    },
    "handler": get_stock_history_tool_handler
}


# =============================================================================
# Proactive AI: Trigger Management Tools (Epic 13)
# =============================================================================


async def create_trigger_tool_handler(
    user_id: str,
    intent_name: str,
    trigger_type: str,
    action_context: dict,
    schedule: dict = None,
    condition: dict = None,
    enabled: bool = True,
    expires_at: str = None
) -> Dict[str, Any]:
    """
    Create a new proactive trigger (called "intent" in backend).

    This tool allows the LLM to set up triggers that will cause Annie to
    initiate contact with the user based on schedules or conditions.

    Args:
        user_id: User identifier
        intent_name: Short descriptive name (e.g., 'Morning portfolio brief')
        trigger_type: 'scheduled' or 'condition'
        action_context: Comprehensive briefing for wake-up LLM (see architecture doc)
        schedule: Schedule configuration for 'scheduled' type
        condition: Condition configuration for 'condition' type
        enabled: Whether trigger is active (default: True)
        expires_at: Optional ISO datetime when trigger auto-deletes

    Returns:
        dict: Created trigger with ID and next_check time
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Validate trigger_type
    if trigger_type not in ["scheduled", "condition"]:
        return {
            "status": "error",
            "message": f"Invalid trigger_type: '{trigger_type}'. Must be 'scheduled' or 'condition'."
        }

    # Validate type-specific configuration
    if trigger_type == "scheduled" and not schedule:
        return {
            "status": "error",
            "message": "Schedule configuration required for 'scheduled' trigger type"
        }

    if trigger_type == "condition" and not condition:
        return {
            "status": "error",
            "message": "Condition configuration required for 'condition' trigger type"
        }

    # Build request payload
    # action_context must be a JSON string, not a dict
    import json
    action_context_str = action_context
    if isinstance(action_context, dict):
        action_context_str = json.dumps(action_context)
    elif not isinstance(action_context, str):
        # If it's not a dict or string, convert to string
        action_context_str = json.dumps(action_context)
    
    # Map trigger_type from MCP tool format to agentic-memories API format
    # MCP tool uses: "scheduled" or "condition"
    # API expects: "cron" | "interval" | "once" | "price" | "silence" | "portfolio"
    api_trigger_type = trigger_type
    api_schedule = None
    api_condition = None
    
    if trigger_type == "scheduled" and schedule:
        # Map scheduled trigger to API format
        # Default timezone to America/Los_Angeles (PST) if not provided
        default_timezone = "America/Los_Angeles"
        schedule_mode = schedule.get("mode", "cron")
        if schedule_mode == "once":
            api_trigger_type = "once"
            api_schedule = {
                "trigger_at": schedule.get("datetime"),  # API expects "trigger_at" not "datetime"
                "timezone": schedule.get("timezone", default_timezone)
            }
        elif schedule_mode == "cron":
            api_trigger_type = "cron"
            api_schedule = {
                "cron": schedule.get("cron_expression") or schedule.get("cron"),
                "timezone": schedule.get("timezone", default_timezone)
            }
        else:
            # Default to cron if mode not specified
            api_trigger_type = "cron"
            api_schedule = schedule
    elif trigger_type == "condition" and condition:
        # Map condition trigger to API format
        condition_type = condition.get("condition_type", "price")
        api_trigger_type = condition_type  # "price", "silence", or "portfolio"

        # Set default check_interval_minutes based on condition type
        # Price: every 2 hours (120 min) - balances responsiveness with API limits
        # Portfolio: every 24 hours (1440 min) - daily check is sufficient
        # Silence: every 60 min - checking user inactivity hourly is sufficient
        default_check_intervals = {
            "price": 120,
            "portfolio": 1440,
            "silence": 60
        }
        check_interval = condition.get(
            "check_interval_minutes",
            default_check_intervals.get(condition_type, 120)
        )

        api_condition = {
            "expression": condition.get("expression"),
            "check_interval_minutes": check_interval,
            "cooldown_hours": condition.get("cooldown_hours", 1),
            "fire_mode": condition.get("fire_mode", "recurring")
        }
    
    payload = {
        "user_id": user_id,
        "intent_name": intent_name,
        "trigger_type": api_trigger_type,
        "action_context": action_context_str,
        "enabled": enabled
    }

    if api_schedule:
        payload["trigger_schedule"] = api_schedule
    if api_condition:
        payload["trigger_condition"] = api_condition
    if expires_at:
        payload["expires_at"] = expires_at

    try:
        # Log the full request payload
        payload_json_str = json.dumps(payload, indent=2, default=str)
        logger.info(
            f"Creating proactive trigger via MCP tool - URL: {memories_url}/v1/intents\n"
            f"Payload:\n{payload_json_str}",
            extra={
                "user_id": user_id,
                "intent_name": intent_name,
                "trigger_type": trigger_type,
                "api_trigger_type": api_trigger_type,
                "payload": payload
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{memories_url}/v1/intents",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code in (200, 201):
                result = response.json()

                logger.info(
                    "Trigger created successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "intent_name": intent_name,
                        "trigger_id": result.get("id"),
                        "next_check": result.get("next_check"),
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "trigger": {
                        "id": result.get("id"),
                        "intent_name": result.get("intent_name"),
                        "description": result.get("description"),
                        "trigger_type": result.get("trigger_type"),
                        "trigger_schedule": result.get("trigger_schedule"),
                        "trigger_condition": result.get("trigger_condition"),
                        "enabled": result.get("enabled"),
                        "next_check": result.get("next_check"),
                        "execution_count": result.get("execution_count", 0),
                        "created_at": result.get("created_at"),
                        "updated_at": result.get("updated_at")
                    },
                    "message": f"Created trigger '{intent_name}'. Next fire: {result.get('next_check', 'TBD')}"
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                error_data = None
                try:
                    error_data = response.json()
                    # Handle different error response formats
                    if "errors" in error_data and isinstance(error_data["errors"], list):
                        # agentic-memories returns {"errors": ["error1", "error2"]}
                        error_msg = "; ".join(error_data["errors"])
                    elif "detail" in error_data:
                        error_msg = error_data["detail"]
                        if isinstance(error_msg, dict) and "errors" in error_msg:
                            # Handle nested errors format
                            error_msg = "; ".join(error_msg["errors"]) if isinstance(error_msg["errors"], list) else str(error_msg["errors"])
                    elif "message" in error_data:
                        error_msg = error_data["message"]
                    else:
                        error_msg = str(error_data) if error_data else error_msg
                except Exception:
                    error_msg = response.text or error_msg

                # Log full error details
                error_data_str = json.dumps(error_data, indent=2, default=str) if error_data else str(error_data)
                payload_json_str = json.dumps(payload, indent=2, default=str)
                
                logger.error(
                    f"Create trigger failed via MCP tool - Status: {response.status_code}\n"
                    f"Error: {error_msg}\n"
                    f"Error Data: {error_data_str}\n"
                    f"Response Text: {response.text}\n"
                    f"Request Payload:\n{payload_json_str}",
                    extra={
                        "user_id": user_id,
                        "intent_name": intent_name,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "error_data": error_data,
                        "response_text": response.text,
                        "request_payload": payload,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to create trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Create trigger timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error creating trigger", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error creating trigger", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Create trigger tool definition
create_trigger_tool = {
    "name": "create_trigger",
    "description": """
Create a proactive trigger that will cause Annie to initiate contact with the user.

USE THIS WHEN USER WANTS:
- Reminders: "Remind me to...", "Every morning tell me...", "On Friday..."
- Alerts: "Let me know when NVDA drops below $130", "Alert me if any stock moves 5%"
- Check-ins: "If I don't message you for 2 days, check in", "Ping me if I'm silent"
- Scheduled updates: "Every weekday, give me a portfolio summary"

CRON EXPRESSIONS (for scheduled triggers):
- "every morning at 9am" → "0 9 * * *"
- "every weekday at 8:30" → "30 8 * * 1-5"
- "every Friday at 5pm" → "0 17 * * 5"
- "twice a day (9am and 5pm)" → "0 9,17 * * *"

Cron format: [minute] [hour] [day-of-month] [month] [day-of-week]
Examples: "0 9 * * *" = 9am daily, "30 8 * * 1-5" = 8:30am weekdays

ACTION_CONTEXT GUIDANCE:
Write a COMPREHENSIVE briefing for the wake-up AI. This is its ONLY context - be thorough!

REQUIRED SECTIONS:
1. original_request: User's exact words
2. intent_summary: What this trigger should accomplish and WHY it matters
3. user_context: Name, timezone, communication style (NOT dynamic data like holdings/prices)
4. execution_instructions: Step-by-step guide including:
   - Which tools to call to gather fresh data
   - How to analyze and interpret the data
   - Decision criteria for when to skip vs send
5. message_guidance: How to compose the message:
   - If user wants brief: respect that preference
   - Otherwise: default to rich, informative messages with insights and context
   - Include voice examples showing personality
   - Explain WHY data matters, not just WHAT the numbers are
6. available_tools: Which tools are relevant and how to use them
7. edge_cases: How to handle errors, missing data, unusual situations

CRITICAL RULES:
- ⚠️ PRE-FLIGHT CHECK: Before calling this tool, you MUST call list_triggers first to check
  if a similar trigger already exists. If a similar intent exists (e.g., user wants to change
  the time of an existing alert), use update_trigger instead. Only use create_trigger for
  brand new intents. DO NOT create duplicate triggers!
- If in doubt whether to create a new trigger or update an existing one, ASK THE USER to confirm
  before proceeding. Example: "I see you already have a '9am portfolio update' - should I update
  that one to 1pm, or create a separate trigger?"
- NEVER put dynamic data (holdings, prices) in action_context - fetch fresh via tools
- Wake-up AI should use tools liberally to gather current information
- action_context preferences take precedence - if user wants brief, respect it
- Be thorough - this briefing is EVERYTHING the wake-up AI knows
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "intent_name": {
                "type": "string",
                "description": "Short descriptive name (e.g., 'Morning portfolio brief')"
            },
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition"],
                "description": "Wake-up mechanism: 'scheduled' for time-based, 'condition' for event-based"
            },
            "action_context": {
                "type": "object",
                "description": "Comprehensive briefing for wake-up LLM with all execution guidance"
            },
            "schedule": {
                "type": "object",
                "description": "Schedule configuration for 'scheduled' type triggers",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["cron", "once"],
                        "description": "'cron' for recurring, 'once' for one-time"
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "Cron expression for recurring (e.g., '0 9 * * 1-5')"
                    },
                    "datetime": {
                        "type": "string",
                        "description": "ISO datetime for one-time (e.g., '2025-12-31T09:00:00')"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone (e.g., 'America/Los_Angeles')"
                    }
                }
            },
            "condition": {
                "type": "object",
                "description": "Condition configuration for 'condition' type triggers",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["price", "portfolio", "silence"],
                        "description": "Condition type"
                    },
                    "expression": {
                        "type": "string",
                        "description": "Condition expression (e.g., 'NVDA < 130', 'inactive_hours > 48')"
                    },
                    "check_interval_minutes": {
                        "type": "integer",
                        "description": "How often to evaluate in minutes (default: 120 for price, 1440 for portfolio, 60 for silence)"
                    },
                    "cooldown_hours": {
                        "type": "integer",
                        "description": "Minimum hours between fires (default: 24)"
                    }
                }
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether trigger is active (default: true)",
                "default": True
            },
            "expires_at": {
                "type": "string",
                "description": "Optional: ISO datetime when trigger auto-deletes"
            }
        },
        "required": ["user_id", "intent_name", "trigger_type", "action_context"]
    },
    "handler": create_trigger_tool_handler
}


async def list_triggers_tool_handler(
    user_id: str,
    trigger_type: str = "all",
    include_disabled: bool = False
) -> Dict[str, Any]:
    """
    List user's proactive triggers.

    Args:
        user_id: User identifier
        trigger_type: Filter by type: 'scheduled', 'condition', or 'all' (default: 'all')
        include_disabled: Include paused triggers (default: False)

    Returns:
        dict: Array of triggers with id, name, schedule/condition, status, etc.
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Build query parameters
    params = {"user_id": user_id}
    if trigger_type != "all":
        params["trigger_type"] = trigger_type
    if include_disabled:
        params["include_disabled"] = "true"

    try:
        logger.info(
            "Listing triggers via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_type": trigger_type,
                "include_disabled": include_disabled
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{memories_url}/v1/intents",
                params=params
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                # API returns a list directly, not wrapped in an object
                if isinstance(result, list):
                    triggers = result
                else:
                    triggers = result.get("intents", [])

                logger.info(
                    "Triggers listed successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_count": len(triggers),
                        "duration_ms": duration_ms
                    }
                )

                # Format triggers for LLM consumption
                formatted_triggers = []
                for trigger in triggers:
                    formatted = {
                        "id": trigger.get("id"),
                        "intent_name": trigger.get("intent_name"),
                        "description": trigger.get("description"),
                        "trigger_type": trigger.get("trigger_type"),
                        "trigger_schedule": trigger.get("trigger_schedule"),
                        "trigger_condition": trigger.get("trigger_condition"),
                        "enabled": trigger.get("enabled"),
                        "next_check": trigger.get("next_check"),
                        "last_checked": trigger.get("last_checked"),
                        "last_executed": trigger.get("last_executed"),
                        "execution_count": trigger.get("execution_count", 0),
                        "last_execution_status": trigger.get("last_execution_status"),
                        "created_at": trigger.get("created_at"),
                        "updated_at": trigger.get("updated_at")
                    }

                    formatted_triggers.append(formatted)

                return {
                    "status": "success",
                    "trigger_count": len(formatted_triggers),
                    "triggers": formatted_triggers,
                    "message": f"Found {len(formatted_triggers)} trigger{'s' if len(formatted_triggers) != 1 else ''}."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "List triggers failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to list triggers: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("List triggers timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error listing triggers", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error listing triggers", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# List triggers tool definition
list_triggers_tool = {
    "name": "list_triggers",
    "description": """
List all proactive triggers for the current user.

USE WHEN USER ASKS:
- "What reminders do I have?"
- "Show my alerts"
- "What notifications are set up?"
- "List my triggers"
- "What's scheduled?"

Returns array of triggers with:
- id: Unique identifier
- intent_name: Display name
- trigger_type: 'scheduled' or 'condition'
- schedule/condition: Configuration details
- enabled: Active status (true/false)
- next_check: When it will next evaluate
- fire_count: Number of times it has fired
- last_fired: When it last fired (or null if never)

Use this before updating or deleting triggers to show user what exists.
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition", "all"],
                "description": "Filter by type (default: 'all')",
                "default": "all"
            },
            "include_disabled": {
                "type": "boolean",
                "description": "Include paused triggers (default: false)",
                "default": False
            }
        },
        "required": ["user_id"]
    },
    "handler": list_triggers_tool_handler
}


async def update_trigger_tool_handler(
    user_id: str,
    trigger_id: str,
    intent_name: str = None,
    schedule: dict = None,
    condition: dict = None,
    action_context: dict = None,
    enabled: bool = None
) -> Dict[str, Any]:
    """
    Update an existing proactive trigger.

    Supports partial updates - only provided fields are modified.

    Args:
        user_id: User identifier
        trigger_id: ID from list_triggers
        intent_name: New display name
        schedule: New schedule configuration
        condition: New condition configuration
        action_context: Updated briefing (merges with existing)
        enabled: Enable (True) or pause (False)

    Returns:
        dict: Updated trigger details
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id and trigger_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    if not trigger_id or not isinstance(trigger_id, str):
        return {
            "status": "error",
            "message": "Invalid trigger_id: must be non-empty string"
        }

    # Build request payload (only include provided fields)
    payload = {"user_id": user_id}
    if intent_name is not None:
        payload["intent_name"] = intent_name
    if schedule is not None:
        # Convert schedule from MCP tool format to API format
        # MCP format: {"mode": "cron", "cron_expression": "0 9 * * *", "timezone": "America/Los_Angeles"}
        # API format: {"cron": "0 9 * * *", "timezone": "America/Los_Angeles"}
        # Note: Only include timezone if provided, to preserve existing timezone on updates
        schedule_mode = schedule.get("mode", "cron")
        if schedule_mode == "once":
            trigger_schedule = {
                "trigger_at": schedule.get("datetime")
            }
            if schedule.get("timezone"):
                trigger_schedule["timezone"] = schedule["timezone"]
            payload["trigger_schedule"] = trigger_schedule
        elif schedule_mode == "cron":
            trigger_schedule = {
                "cron": schedule.get("cron_expression") or schedule.get("cron")
            }
            if schedule.get("timezone"):
                trigger_schedule["timezone"] = schedule["timezone"]
            payload["trigger_schedule"] = trigger_schedule
        else:
            # Pass through as-is for other modes
            payload["trigger_schedule"] = schedule
    if condition is not None:
        payload["trigger_condition"] = condition
    if action_context is not None:
        # action_context must be a JSON string
        if isinstance(action_context, dict):
            payload["action_context"] = json.dumps(action_context)
        else:
            payload["action_context"] = action_context
    if enabled is not None:
        payload["enabled"] = enabled

    try:
        logger.info(
            "Updating trigger via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_id": trigger_id,
                "updates": {k: v for k, v in payload.items() if k != "user_id"}
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.put(
                f"{memories_url}/v1/intents/{trigger_id}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                logger.info(
                    "Trigger updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "trigger": {
                        "id": result.get("id"),
                        "intent_name": result.get("intent_name"),
                        "description": result.get("description"),
                        "trigger_type": result.get("trigger_type"),
                        "trigger_schedule": result.get("trigger_schedule"),
                        "trigger_condition": result.get("trigger_condition"),
                        "enabled": result.get("enabled"),
                        "next_check": result.get("next_check"),
                        "execution_count": result.get("execution_count", 0),
                        "created_at": result.get("created_at"),
                        "updated_at": result.get("updated_at")
                    },
                    "message": f"Updated trigger '{result.get('intent_name')}'"
                }

            elif response.status_code == 404:
                logger.info(
                    "Trigger not found for update",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Trigger not found with ID '{trigger_id}'",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Update trigger failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to update trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Update trigger timed out", extra={"user_id": user_id, "trigger_id": trigger_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error updating trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error updating trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Update trigger tool definition
update_trigger_tool = {
    "name": "update_trigger",
    "description": """
Update an existing proactive trigger's configuration.

USE WHEN USER WANTS TO:
- Change schedule: "Make it 8am instead of 9am"
- Modify condition: "Change to alert at $125 instead of $130"
- Update preferences: "Make the messages shorter"
- Pause: "Stop the morning updates for now" → set enabled=false
- Resume: "Turn my alerts back on" → set enabled=true

PROCESS:
1. Call list_triggers to find the trigger ID
2. Call update_trigger with the changes
3. Confirm the update with user

PAUSING VS DELETING:
- Use enabled=false to pause (can resume later)
- Use delete_trigger to permanently remove

Only include fields you want to change. Omitted fields keep current values.
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "intent_name": {
                "type": "string",
                "description": "New display name"
            },
            "schedule": {
                "type": "object",
                "description": "New schedule configuration"
            },
            "condition": {
                "type": "object",
                "description": "New condition configuration"
            },
            "action_context": {
                "type": "object",
                "description": "Updated briefing (merges with existing)"
            },
            "enabled": {
                "type": "boolean",
                "description": "Enable (true) or pause (false)"
            }
        },
        "required": ["user_id", "trigger_id"]
    },
    "handler": update_trigger_tool_handler
}


async def delete_trigger_tool_handler(
    user_id: str,
    trigger_id: str,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Permanently delete a proactive trigger.

    Args:
        user_id: User identifier
        trigger_id: ID from list_triggers
        confirm: Must be True to confirm deletion

    Returns:
        dict: Confirmation of deletion
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id and trigger_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    if not trigger_id or not isinstance(trigger_id, str):
        return {
            "status": "error",
            "message": "Invalid trigger_id: must be non-empty string"
        }

    # Validate confirmation
    if not confirm:
        logger.warning(
            "Delete trigger called without confirmation",
            extra={"user_id": user_id, "trigger_id": trigger_id}
        )
        return {
            "status": "error",
            "message": "Confirmation required. This permanently deletes the trigger. Set confirm=true to proceed.",
            "error_code": "CONFIRMATION_REQUIRED"
        }

    try:
        logger.info(
            "Deleting trigger via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_id": trigger_id
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/intents/{trigger_id}",
                params={"user_id": user_id, "confirm": "true"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                # Try to get response body if available (200), otherwise use trigger_id
                intent_name = trigger_id
                if response.status_code == 200:
                    try:
                        result = response.json()
                        intent_name = result.get('intent_name', trigger_id)
                    except Exception:
                        pass

                logger.info(
                    "Trigger deleted successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "trigger_id": trigger_id,
                    "message": f"Deleted trigger '{intent_name}'"
                }

            elif response.status_code == 404:
                logger.info(
                    "Trigger not found for deletion",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Trigger not found with ID '{trigger_id}'",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Delete trigger failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to delete trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Delete trigger timed out", extra={"user_id": user_id, "trigger_id": trigger_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error deleting trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error deleting trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Delete trigger tool definition
delete_trigger_tool = {
    "name": "delete_trigger",
    "description": """
Permanently delete a proactive trigger.

USE WHEN USER WANTS TO:
- "Stop the morning reminders" (permanently)
- "Cancel the NVDA alert"
- "Remove that trigger"
- "I don't need that anymore"

IMPORTANT:
- ALWAYS confirm with user before deleting
- This is permanent - cannot be undone
- For temporary stop, use update_trigger with enabled=false instead

PROCESS:
1. Call list_triggers to show user what exists
2. Confirm which trigger to delete
3. Call delete_trigger with confirm=true
4. Confirm deletion to user

Example:
User: "Stop my morning updates"
You: "I see you have 'Morning portfolio brief' set for 8:30am weekdays. Do you want to pause it temporarily or delete it permanently?"
User: "Delete it"
You: [Call delete_trigger with confirm=true]
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true to confirm deletion"
            }
        },
        "required": ["user_id", "trigger_id", "confirm"]
    },
    "handler": delete_trigger_tool_handler
}


# =============================================================================
# Reddit Search Tool (Epic 15 - Story 15.3)
# =============================================================================


def _praw_search_sync(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int,
    include_comments: bool,
    client_id: str,
    client_secret: str,
    user_agent: str
) -> Dict[str, Any]:
    """
    Synchronous PRAW search function to be run in executor.

    PRAW is synchronous and must be run in a thread pool to avoid blocking
    the event loop.

    Args:
        query: Search query string
        subreddit: Subreddit name (without r/ prefix) or None for "all"
        sort: Sort order (relevance, hot, top, new)
        time_filter: Time filter (hour, day, week, month, year, all)
        limit: Maximum results to return
        include_comments: Whether to include top comments
        client_id: Reddit OAuth client ID
        client_secret: Reddit OAuth client secret
        user_agent: User agent string

    Returns:
        dict: Search results with provider="praw"
    """
    import praw
    from prawcore.exceptions import (
        Forbidden,
        NotFound,
        TooManyRequests,
        ServerError,
        RequestException
    )

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        # Get subreddit - use "all" if none specified
        sub = reddit.subreddit(subreddit if subreddit else "all")

        results = []
        for submission in sub.search(query, sort=sort, time_filter=time_filter, limit=limit):
            # Build post data
            post = {
                "type": "post",
                "title": submission.title,
                "subreddit": f"r/{submission.subreddit.display_name}",
                "author": f"u/{submission.author.name}" if submission.author else "[deleted]",
                "score": submission.score,
                "url": f"https://reddit.com{submission.permalink}",
                "selftext": submission.selftext[:1000] if submission.selftext else None,
                "num_comments": submission.num_comments,
                "created_utc": submission.created_utc,
                "comments": []
            }

            # Include top comments if requested
            if include_comments:
                try:
                    # Replace "more comments" links with empty to avoid extra API calls
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments[:5]:
                        # Skip deleted/removed comments
                        if comment.author is None:
                            continue
                        post["comments"].append({
                            "author": f"u/{comment.author.name}" if comment.author else "[deleted]",
                            "score": comment.score,
                            "body": comment.body[:500],
                            "replies_count": len(comment.replies) if hasattr(comment, 'replies') else 0
                        })
                except Exception as e:
                    # Log but continue - comments are optional
                    logger.warning(f"Failed to fetch comments: {e}")

            results.append(post)

        return {
            "status": "success",
            "provider": "praw",
            "query": query,
            "subreddit": subreddit or "all",
            "results": results
        }

    except Forbidden as e:
        # Private subreddit or banned
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Subreddit is private or access forbidden: {str(e)}",
            "error_code": "FORBIDDEN"
        }

    except NotFound as e:
        # Subreddit doesn't exist
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Subreddit not found: {str(e)}",
            "error_code": "NOT_FOUND"
        }

    except TooManyRequests as e:
        # Rate limited - PRAW usually handles this, but just in case
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Rate limited by Reddit: {str(e)}",
            "error_code": "RATE_LIMITED"
        }

    except (ServerError, RequestException) as e:
        # Server error or request failed
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"Reddit API error: {str(e)}",
            "error_code": "API_ERROR"
        }

    except Exception as e:
        # Unexpected error - let caller handle fallback
        return {
            "status": "error",
            "provider": "praw",
            "query": query,
            "error_message": f"PRAW error: {str(e)}",
            "error_code": "PRAW_ERROR"
        }


# Reddit JSON API cooldown tracking
# Prevents repeated requests when IP is blocked (HTTP 429 or connection errors)
_reddit_json_api_cooldown_until: float = 0.0  # Unix timestamp when cooldown expires
REDDIT_JSON_API_COOLDOWN_SECONDS = 3600  # 1 hour cooldown after failure


def _is_reddit_json_api_in_cooldown() -> tuple[bool, int]:
    """Check if Reddit JSON API is in cooldown period.
    
    Returns:
        Tuple of (is_in_cooldown, seconds_remaining)
    """
    global _reddit_json_api_cooldown_until
    now = time.time()
    if now < _reddit_json_api_cooldown_until:
        remaining = int(_reddit_json_api_cooldown_until - now)
        return True, remaining
    return False, 0


def _set_reddit_json_api_cooldown():
    """Set cooldown for Reddit JSON API after a failure."""
    global _reddit_json_api_cooldown_until
    _reddit_json_api_cooldown_until = time.time() + REDDIT_JSON_API_COOLDOWN_SECONDS
    logger.warning(
        f"Reddit JSON API cooldown activated for {REDDIT_JSON_API_COOLDOWN_SECONDS} seconds",
        extra={
            "event": "reddit_json_api.cooldown_set",
            "cooldown_seconds": REDDIT_JSON_API_COOLDOWN_SECONDS,
            "cooldown_until": _reddit_json_api_cooldown_until
        }
    )


async def _reddit_json_search(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int,
    user_agent: str
) -> Dict[str, Any]:
    """
    Search Reddit using public JSON API as fallback.

    This doesn't require authentication but has limitations:
    - Cannot include comments in search results
    - More aggressive rate limiting
    - Less reliable than OAuth

    Args:
        query: Search query string
        subreddit: Subreddit name (without r/ prefix) or None for "all"
        sort: Sort order (relevance, hot, top, new)
        time_filter: Time filter (hour, day, week, month, year, all)
        limit: Maximum results to return
        user_agent: User agent string

    Returns:
        dict: Search results with provider="json_api"
    """
    try:
        base_url = "https://www.reddit.com"
        if subreddit:
            url = f"{base_url}/r/{subreddit}/search.json"
        else:
            url = f"{base_url}/search.json"

        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 25),
            "restrict_sr": "on" if subreddit else "off"
        }

        headers = {"User-Agent": user_agent}

        # Retry with exponential backoff for rate limiting
        max_retries = 3
        retry_delays = [1, 2, 4]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(max_retries):
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    follow_redirects=True
                )

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Reddit JSON API rate limited, retrying in {retry_delays[attempt]}s",
                            extra={"attempt": attempt + 1, "query": query}
                        )
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    else:
                        return {
                            "status": "error",
                            "provider": "json_api",
                            "query": query,
                            "error_message": "Rate limited after retries",
                            "error_code": "RATE_LIMITED"
                        }

                if response.status_code == 403:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": "Subreddit is private or access forbidden",
                        "error_code": "FORBIDDEN"
                    }

                if response.status_code == 404:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": f"Subreddit not found: {subreddit}",
                        "error_code": "NOT_FOUND"
                    }

                if response.status_code != 200:
                    return {
                        "status": "error",
                        "provider": "json_api",
                        "query": query,
                        "error_message": f"HTTP {response.status_code}",
                        "error_code": "HTTP_ERROR"
                    }

                # Success - parse response
                break

            data = response.json()
            results = []

            for post_data in data.get("data", {}).get("children", []):
                post = post_data.get("data", {})

                # Skip deleted posts
                author = post.get("author", "[deleted]")
                if author == "[deleted]":
                    continue

                results.append({
                    "type": "post",
                    "title": post.get("title"),
                    "subreddit": f"r/{post.get('subreddit')}",
                    "author": f"u/{author}",
                    "score": post.get("score", 0),
                    "url": f"https://reddit.com{post.get('permalink')}",
                    "selftext": (post.get("selftext", "") or "")[:1000],
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc"),
                    "comments": []  # JSON API doesn't include comments in search
                })

            return {
                "status": "success",
                "provider": "json_api",
                "query": query,
                "subreddit": subreddit or "all",
                "results": results,
                "note": "Comments not available via JSON API fallback"
            }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "json_api",
            "query": query,
            "error_message": "Request timed out",
            "error_code": "TIMEOUT"
        }

    except Exception as e:
        return {
            "status": "error",
            "provider": "json_api",
            "query": query,
            "error_message": str(e),
            "error_code": "INTERNAL_ERROR"
        }


async def reddit_search_tool_handler(
    query: str,
    subreddit: str = None,
    search_type: str = "posts",
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 10,
    include_comments: bool = True
) -> Dict[str, Any]:
    """
    Search Reddit for posts, comments, and community discussions.

    Uses PRAW (Python Reddit API Wrapper) with OAuth for full-featured access
    when credentials are configured. Falls back to Reddit's public JSON API
    when PRAW is unavailable or fails.

    Args:
        query: Search query string
        subreddit: Limit search to specific subreddit (without r/ prefix)
        search_type: Type of content to search (posts, comments, subreddits) - currently only posts supported
        sort: Sort order (relevance, hot, top, new). Default: relevance
        time_filter: Time filter (hour, day, week, month, year, all). Default: all
        limit: Maximum results (1-25). Default: 10
        include_comments: Include top 5 comments per post (PRAW only). Default: true

    Returns:
        dict: Search results with status, provider, query, subreddit, and results array
    """
    start_time = time.time()

    # Validate parameters
    if not query or not query.strip():
        return {
            "status": "error",
            "error_message": "Query is required",
            "error_code": "VALIDATION_ERROR"
        }

    # Validate sort option
    valid_sorts = ["relevance", "hot", "top", "new"]
    if sort not in valid_sorts:
        return {
            "status": "error",
            "error_message": f"Invalid sort option '{sort}'. Valid options: {', '.join(valid_sorts)}",
            "error_code": "VALIDATION_ERROR"
        }

    # Validate time_filter option
    valid_time_filters = ["hour", "day", "week", "month", "year", "all"]
    if time_filter not in valid_time_filters:
        return {
            "status": "error",
            "error_message": f"Invalid time_filter '{time_filter}'. Valid options: {', '.join(valid_time_filters)}",
            "error_code": "VALIDATION_ERROR"
        }

    # Clamp limit to valid range
    limit = max(1, min(25, limit))

    # Get config for Reddit credentials
    try:
        config = get_config()
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
        config = {}

    client_id = config.get("REDDIT_CLIENT_ID")
    client_secret = config.get("REDDIT_CLIENT_SECRET")
    user_agent = config.get("REDDIT_USER_AGENT", "annie-bot/1.0")

    logger.info(
        "Starting Reddit search",
        extra={
            "event": "reddit_search.started",
            "query": query,
            "subreddit": subreddit,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
            "include_comments": include_comments,
            "has_praw_credentials": bool(client_id and client_secret)
        }
    )

    result = None

    # Try PRAW first if credentials are available
    if client_id and client_secret:
        try:
            # Run synchronous PRAW in executor to not block event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                _praw_search_sync,
                query,
                subreddit,
                sort,
                time_filter,
                limit,
                include_comments,
                client_id,
                client_secret,
                user_agent
            )

            # Check if PRAW succeeded
            if result.get("status") == "success":
                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "Reddit search completed via PRAW",
                    extra={
                        "event": "reddit_search.completed",
                        "provider": "praw",
                        "query": query,
                        "subreddit": subreddit,
                        "result_count": len(result.get("results", [])),
                        "duration_ms": duration_ms
                    }
                )
                return result

            # PRAW failed - log and fall through to JSON API
            logger.warning(
                "PRAW search failed, falling back to JSON API",
                extra={
                    "event": "reddit_search.fallback",
                    "query": query,
                    "praw_error": result.get("error_message"),
                    "praw_error_code": result.get("error_code")
                }
            )

        except Exception as e:
            logger.warning(
                f"PRAW search exception, falling back to JSON API: {e}",
                extra={
                    "event": "reddit_search.fallback",
                    "query": query,
                    "exception": str(e)
                }
            )

    # Check if JSON API is in cooldown (to avoid IP blocks from Reddit)
    in_cooldown, cooldown_remaining = _is_reddit_json_api_in_cooldown()
    if in_cooldown:
        logger.warning(
            "Reddit JSON API in cooldown, skipping request",
            extra={
                "event": "reddit_search.cooldown_blocked",
                "query": query,
                "cooldown_remaining_seconds": cooldown_remaining
            }
        )
        return {
            "status": "error",
            "provider": None,
            "query": query,
            "subreddit": subreddit or "all",
            "error_message": f"Reddit API temporarily unavailable. Cooldown expires in {cooldown_remaining // 60} minutes.",
            "error_code": "COOLDOWN_ACTIVE"
        }

    # Fallback to JSON API (no auth required)
    logger.info(
        "Using Reddit JSON API fallback",
        extra={
            "event": "reddit_search.json_api",
            "query": query,
            "subreddit": subreddit,
            "reason": "no_credentials" if not (client_id and client_secret) else "praw_failed"
        }
    )

    result = await _reddit_json_search(
        query=query,
        subreddit=subreddit,
        sort=sort,
        time_filter=time_filter,
        limit=limit,
        user_agent=user_agent
    )

    duration_ms = int((time.time() - start_time) * 1000)

    if result.get("status") == "success":
        logger.info(
            "Reddit search completed via JSON API",
            extra={
                "event": "reddit_search.completed",
                "provider": "json_api",
                "query": query,
                "subreddit": subreddit,
                "result_count": len(result.get("results", [])),
                "duration_ms": duration_ms
            }
        )
    else:
        # Set cooldown on failure (rate limit, connection errors, or persistent failures)
        error_code = result.get("error_code", "")
        cooldown_trigger_codes = ("RATE_LIMITED", "HTTP_ERROR", "TIMEOUT", "FORBIDDEN")
        should_cooldown = error_code in cooldown_trigger_codes
        
        if should_cooldown:
            _set_reddit_json_api_cooldown()

        logger.error(
            "Reddit search failed",
            extra={
                "event": "reddit_search.failed",
                "query": query,
                "error_message": result.get("error_message"),
                "error_code": error_code,
                "duration_ms": duration_ms,
                "cooldown_activated": should_cooldown
            }
        )

    return result


# Reddit search tool definition
reddit_search_tool = {
    "name": "reddit_search",
    "description": "Search Reddit for posts, comments, and community discussions. Useful for finding real user experiences, reviews, and opinions on topics. Great for product research, troubleshooting, and understanding public sentiment.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "subreddit": {
                "type": "string",
                "description": "Limit search to specific subreddit (without r/ prefix)"
            },
            "search_type": {
                "type": "string",
                "enum": ["posts", "comments", "subreddits"],
                "description": "Type of content to search (default: posts)",
                "default": "posts"
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "hot", "top", "new"],
                "description": "Sort order for results (default: relevance)",
                "default": "relevance"
            },
            "time_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Time filter for results (default: all)",
                "default": "all"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10, max: 25)",
                "default": 10,
                "minimum": 1,
                "maximum": 25
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include top comments for posts (default: true, PRAW only)",
                "default": True
            }
        },
        "required": ["query"]
    },
    "handler": reddit_search_tool_handler
}

# =============================================================================
# Web Search Tool (Epic 15 - Story 15.1)
# =============================================================================

from typing import List


async def _tavily_search(
    query: str,
    max_results: int,
    search_depth: str,
    include_domains: List[str],
    exclude_domains: List[str],
    api_key: str
) -> Dict[str, Any]:
    """
    Execute Tavily search API call.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10)
        search_depth: "basic" (faster/cheaper) or "advanced" (deeper)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains
        api_key: Tavily API key

    Returns:
        dict with status, provider, query, and results array (or error info)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,  # Tavily uses body, not header
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max_results,
                    "include_domains": include_domains,
                    "exclude_domains": exclude_domains
                }
            )

            if response.status_code == 429:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT"
                }

            if response.status_code >= 500:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": f"Server error: {response.status_code}",
                    "error_code": "SERVER_ERROR"
                }

            response.raise_for_status()
            data = response.json()

            return {
                "status": "success",
                "provider": "tavily",
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "score": r.get("score", None)  # Relevance score if available
                    }
                    for r in data.get("results", [])[:max_results]
                ]
            }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": str(e),
            "error_code": "UNKNOWN"
        }


async def _duckduckgo_search(query: str, max_results: int) -> Dict[str, Any]:
    """
    Search using DuckDuckGo as fallback.

    Note: duckduckgo-search is synchronous, run in executor.

    Args:
        query: Search query string
        max_results: Maximum results to return

    Returns:
        dict with status, provider, query, and results array
    """
    try:
        from duckduckgo_search import DDGS

        def _sync_search():
            ddgs = DDGS()
            return list(ddgs.text(query, max_results=max_results))

        # Run sync library in executor to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _sync_search)

        return {
            "status": "success",
            "provider": "duckduckgo",
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "score": None  # DDG doesn't provide relevance scores
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return {
            "status": "error",
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "error_message": str(e)
        }


async def web_search_tool_handler(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Execute web search using Tavily with DuckDuckGo fallback.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10, default 5)
        search_depth: "basic" (faster/cheaper) or "advanced" (deeper)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains

    Returns:
        dict with status, provider, query, and results array
    """
    start_time = time.time()

    # Validate and cap max_results to range 1-10
    max_results = max(1, min(max_results, 10))

    # Validate search_depth
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    try:
        config = get_config()
        tavily_api_key = config.get("TAVILY_API_KEY")

        if tavily_api_key:
            result = await _tavily_search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                api_key=tavily_api_key
            )
            if result["status"] == "success":
                logger.info(
                    "web_search.completed",
                    extra={
                        "query": query,
                        "provider": "tavily",
                        "results_count": len(result.get("results", [])),
                        "duration_ms": int((time.time() - start_time) * 1000)
                    }
                )
                return result
            # Tavily failed, fall through to DuckDuckGo
            logger.warning(
                "web_search.fallback",
                extra={
                    "primary": "tavily",
                    "fallback": "duckduckgo",
                    "reason": result.get("error_message", "unknown")
                }
            )
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}, falling back to DDG")

    # Fallback to DuckDuckGo
    result = await _duckduckgo_search(query, max_results)

    logger.info(
        "web_search.completed",
        extra={
            "query": query,
            "provider": "duckduckgo",
            "results_count": len(result.get("results", [])),
            "duration_ms": int((time.time() - start_time) * 1000)
        }
    )

    return result


# Web search tool definition
web_search_tool = {
    "name": "web_search",
    "description": "Search the web for current information using Tavily (primary) with DuckDuckGo fallback. Returns relevant results with titles, URLs, and snippets. Use for finding up-to-date information about news, products, services, facts, or any topic requiring current web data.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - be specific for better results"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 5, max: 10)",
                "default": 5,
                "minimum": 1,
                "maximum": 10
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "description": "Search depth: 'basic' (faster, cheaper) or 'advanced' (deeper, more thorough)",
                "default": "basic"
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains (e.g., ['reddit.com', 'stackoverflow.com'])"
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains (e.g., ['pinterest.com'])"
            }
        },
        "required": ["query"]
    },
    "handler": web_search_tool_handler
}


# =============================================================================
# Web Crawl Tool (Epic 15 - Story 15.2)
# =============================================================================

# Import regex for URL validation (re already imported above)
from urllib.parse import urlparse


def _is_valid_url(url: str) -> bool:
    """
    Validate URL format for security.

    - Must be HTTP or HTTPS
    - Must have a valid domain
    - Block private/internal IP ranges (SSRF protection)

    Args:
        url: URL string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        parsed = urlparse(url)

        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False

        # Must have a netloc (domain)
        if not parsed.netloc:
            return False

        # Block internal/private IP addresses (security - SSRF protection)
        hostname = parsed.hostname or ""

        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False

        # Block private IP ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
        if hostname.startswith("10."):
            return False
        if hostname.startswith("192.168."):
            return False
        if hostname.startswith(("172.16.", "172.17.", "172.18.", "172.19.",
                                "172.20.", "172.21.", "172.22.", "172.23.",
                                "172.24.", "172.25.", "172.26.", "172.27.",
                                "172.28.", "172.29.", "172.30.", "172.31.")):
            return False

        # Block link-local addresses (169.254.x.x)
        if hostname.startswith("169.254."):
            return False

        return True
    except Exception:
        return False


async def _crawl4ai_fetch(
    url: str,
    include_images: bool,
    max_length: int,
    wait_for_js: bool,
    request_id: str
) -> Dict[str, Any]:
    """
    Fetch page content using crawl4ai.

    Args:
        url: URL to crawl
        include_images: Include image descriptions
        max_length: Maximum content length
        wait_for_js: Wait for JavaScript rendering
        request_id: Request ID for logging

    Returns:
        Dict with crawl result

    Raises:
        Exception: On crawl failure
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError as e:
        logger.error(
            "crawl4ai not installed",
            extra={"request_id": request_id, "error": str(e)}
        )
        raise Exception("crawl4ai library not available")

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded" if not wait_for_js else "networkidle"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=run_config
        )

        # Check if crawl was successful
        if not result.success:
            error_msg = getattr(result, 'error_message', 'Unknown error')
            raise Exception(f"Crawl failed: {error_msg}")

        # Check for non-HTML content based on content
        # crawl4ai provides markdown content for HTML pages
        content = result.markdown or ""

        # If content is empty or looks like binary, it's likely non-HTML
        if not content or content.strip() == "":
            # Check if there's any raw HTML
            if hasattr(result, 'html') and result.html:
                content_type = "text/html"
            else:
                return {
                    "status": "error",
                    "provider": "crawl4ai",
                    "url": url,
                    "error_message": "No content extracted. Page may be empty or require JavaScript."
                }

        truncated = False

        # Truncate if exceeds max_length
        if len(content) > max_length:
            content = content[:max_length]
            truncated = True

        # Extract title from metadata or content
        title = ""
        if hasattr(result, 'metadata') and result.metadata:
            title = result.metadata.get("title", "")
        if not title:
            # Try to extract from markdown (first # heading)
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

        # Build metadata
        metadata = {}
        if hasattr(result, 'metadata') and result.metadata:
            metadata = {
                "description": result.metadata.get("description"),
                "author": result.metadata.get("author"),
                "published_date": result.metadata.get("published_date"),
            }

        # Count links if available
        links_count = 0
        if hasattr(result, 'links') and result.links:
            links_count = len(result.links.get("internal", [])) + len(result.links.get("external", []))
        metadata["links_count"] = links_count

        return {
            "status": "success",
            "provider": "crawl4ai",
            "url": url,
            "title": title,
            "content": content,
            "metadata": metadata,
            "truncated": truncated
        }


async def _jina_reader_fetch(url: str, max_length: int, request_id: str) -> Dict[str, Any]:
    """
    Fetch page content using Jina Reader as fallback.

    Jina Reader converts any URL to clean markdown via:
    GET https://r.jina.ai/{url}

    Args:
        url: URL to fetch
        max_length: Maximum content length
        request_id: Request ID for logging

    Returns:
        Dict with crawl result
    """
    try:
        config = get_config()
        jina_api_key = config.get("JINA_API_KEY", "")
    except Exception:
        jina_api_key = ""

    headers = {
        "User-Agent": "annie-bot/1.0",
        "Accept": "text/plain"
    }
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Jina Reader URL format: https://r.jina.ai/{url}
            jina_url = f"https://r.jina.ai/{url}"

            response = await client.get(
                jina_url,
                headers=headers,
                follow_redirects=True
            )

            if response.status_code != 200:
                return {
                    "status": "error",
                    "provider": "jina",
                    "url": url,
                    "error_message": f"Jina Reader returned HTTP {response.status_code}"
                }

            content = response.text
            truncated = False

            # Truncate if exceeds max_length
            if len(content) > max_length:
                content = content[:max_length]
                truncated = True

            # Try to extract title from markdown (first # heading)
            title = ""
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

            return {
                "status": "success",
                "provider": "jina",
                "url": url,
                "title": title,
                "content": content,
                "metadata": {
                    "description": None,
                    "author": None,
                    "published_date": None,
                    "links_count": 0
                },
                "truncated": truncated
            }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": "Jina Reader request timed out (15s limit)"
        }
    except httpx.HTTPError as e:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "jina",
            "url": url,
            "error_message": str(e)
        }


async def web_crawl_tool_handler(
    url: str,
    include_images: bool = False,
    max_length: int = 10000,
    wait_for_js: bool = False
) -> Dict[str, Any]:
    """
    Fetch and parse webpage content using crawl4ai with Jina fallback.

    This tool crawls a webpage and returns clean markdown content suitable
    for LLM consumption. Uses crawl4ai as the primary provider with Jina
    Reader as a fallback for blocked or problematic sites.

    Args:
        url: URL to crawl (must be http:// or https://)
        include_images: Include image descriptions (default: False)
        max_length: Maximum content length in characters (default: 10000)
        wait_for_js: Wait for JavaScript to render (default: False, adds latency)

    Returns:
        Dict with:
        - status: "success" or "error"
        - provider: "crawl4ai" or "jina"
        - url: The crawled URL
        - title: Page title
        - content: Clean markdown content
        - metadata: Description, author, published_date, links_count
        - truncated: True if content was truncated
        - error_message: Error details (on failure)
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    # Validate URL format
    if not _is_valid_url(url):
        logger.warning(
            "Invalid URL provided to web_crawl",
            extra={"url": url, "request_id": request_id}
        )
        return {
            "status": "error",
            "provider": None,
            "url": url,
            "error_message": "Invalid URL format. Please provide a valid HTTP/HTTPS URL (localhost and private IPs are blocked)."
        }

    # Try crawl4ai first
    try:
        result = await _crawl4ai_fetch(url, include_images, max_length, wait_for_js, request_id)
        duration_ms = int((time.time() - start_time) * 1000)

        if result.get("status") == "success":
            logger.info(
                "web_crawl completed via crawl4ai",
                extra={
                    "provider": "crawl4ai",
                    "url": url,
                    "duration_ms": duration_ms,
                    "content_length": len(result.get("content", "")),
                    "truncated": result.get("truncated", False),
                    "request_id": request_id
                }
            )
            return result
        else:
            # crawl4ai returned an error result, try Jina
            logger.warning(
                "crawl4ai returned error, falling back to Jina Reader",
                extra={
                    "url": url,
                    "error": result.get("error_message"),
                    "request_id": request_id
                }
            )
            raise Exception(result.get("error_message", "crawl4ai error"))

    except Exception as e:
        logger.warning(
            "crawl4ai failed, falling back to Jina Reader",
            extra={
                "url": url,
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": request_id
            }
        )

        # Fall back to Jina Reader
        try:
            result = await _jina_reader_fetch(url, max_length, request_id)
            duration_ms = int((time.time() - start_time) * 1000)

            if result.get("status") == "success":
                logger.info(
                    "web_crawl completed via Jina fallback",
                    extra={
                        "provider": "jina",
                        "url": url,
                        "duration_ms": duration_ms,
                        "content_length": len(result.get("content", "")),
                        "truncated": result.get("truncated", False),
                        "request_id": request_id
                    }
                )
            else:
                logger.error(
                    "Both crawl4ai and Jina Reader failed",
                    extra={
                        "url": url,
                        "crawl4ai_error": str(e),
                        "jina_error": result.get("error_message"),
                        "duration_ms": duration_ms,
                        "request_id": request_id
                    }
                )

            return result

        except Exception as jina_error:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Both crawl4ai and Jina Reader failed",
                extra={
                    "url": url,
                    "crawl4ai_error": str(e),
                    "jina_error": str(jina_error),
                    "duration_ms": duration_ms,
                    "request_id": request_id
                }
            )
            return {
                "status": "error",
                "provider": None,
                "url": url,
                "error_message": f"Failed to fetch URL: {str(jina_error)}"
            }


# Web crawl tool definition
web_crawl_tool = {
    "name": "web_crawl",
    "description": """Fetch and read the full content of a webpage.

Use this tool when you need to:
- Read an article, blog post, or news story
- Access documentation or reference material
- Get the full content of a URL the user references
- Read product pages, reviews, or detailed information

Returns clean markdown text suitable for LLM consumption. Supports JavaScript-rendered pages with wait_for_js option.

IMPORTANT: This tool is for reading webpage content. For searching the web, use web_search instead.

Examples:
- User shares a link: "Read this article for me: https://example.com/article"
- User references a page: "What does the React docs say about hooks?"
- User wants details: "Can you summarize this blog post?"
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to crawl and extract content from (must be http:// or https://)"
            },
            "include_images": {
                "type": "boolean",
                "description": "Include image descriptions in output (default: false)",
                "default": False
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum content length in characters (default: 10000, prevents context overflow)",
                "default": 10000
            },
            "wait_for_js": {
                "type": "boolean",
                "description": "Wait for JavaScript to render before extracting content. Use for SPAs or dynamic pages. Adds 1-2s latency. (default: false)",
                "default": False
            }
        },
        "required": ["url"]
    },
    "handler": web_crawl_tool_handler
}
