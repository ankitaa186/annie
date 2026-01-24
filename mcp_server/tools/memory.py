"""
Memory Management Tools

Provides tools for storing, retrieving, deleting, and compacting memories
via the agentic-memories service.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Health Check Tool
# =============================================================================

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


# =============================================================================
# Store Memory Tool
# =============================================================================

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

    # Limit persona_tags to max 10 items
    persona_tags = persona_tags[:10]

    # Build metadata with source: "llm_explicit" merged with user-provided metadata
    merged_metadata = {"source": "llm_explicit"}
    if metadata:
        merged_metadata.update(metadata)

    payload = {
        "user_id": user_id,
        "content": content,
        "layer": layer,
        "type": "explicit",
        "importance": importance,
        "confidence": 0.95,
        "persona_tags": persona_tags,
        "metadata": merged_metadata
    }

    # Add optional episodic fields if provided
    if event_timestamp is not None:
        payload["event_timestamp"] = event_timestamp
    if location is not None:
        payload["location"] = location
    if participants is not None:
        payload["participants"] = participants

    # Add optional emotional fields if provided
    if emotional_state is not None:
        payload["emotional_state"] = emotional_state
    if valence is not None:
        payload["valence"] = valence
    if arousal is not None:
        payload["arousal"] = arousal

    # Add optional procedural fields if provided
    if skill_name is not None:
        payload["skill_name"] = skill_name
    if proficiency_level is not None:
        payload["proficiency_level"] = proficiency_level

    # Error codes that should NOT trigger retry
    NO_RETRY_ERRORS = ["VALIDATION_ERROR", "INTERNAL_ERROR"]

    # Make HTTP request with retry logic
    max_retries = 3
    retry_delays = [1, 2, 4]

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

                    return {
                        "status": "success",
                        "memory_id": memory_id,
                        "message": result.get("message", "Memory stored successfully"),
                        "storage": storage_details,
                        "content": content
                    }
                else:
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

                    if error_code in NO_RETRY_ERRORS:
                        return {
                            "status": "error",
                            "message": f"Failed to store memory: {error_msg}",
                            "error_code": error_code or response.status_code
                        }

                    if 400 <= response.status_code < 500 and error_code not in ["EMBEDDING_ERROR", "STORAGE_ERROR"]:
                        return {
                            "status": "error",
                            "message": f"Failed to store memory: {error_msg}",
                            "error_code": error_code or response.status_code
                        }

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

    return {
        "status": "error",
        "message": "Unknown error occurred",
        "error_code": "UNKNOWN_ERROR"
    }


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
            "user_id": {
                "type": "string",
                "description": "User identifier for memory storage"
            },
            "content": {
                "type": "string",
                "description": "Pre-formatted memory content to store. Should be a clear, complete statement of what to remember.",
                "maxLength": 5000
            },
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


# =============================================================================
# Delete Memory Tool
# =============================================================================

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


# =============================================================================
# Retrieve Memories Tool
# =============================================================================

async def retrieve_memories_tool_handler(
    user_id: str,
    query: str,
    limit: int = 100,
    persona: str = "identity"
) -> Dict[str, Any]:
    """
    Retrieve relevant memories from agentic-memories service for personalized decision support.

    Uses persona-aware retrieval with weighted scoring based on the selected persona:
    - identity: General context, who the person is (default)
    - finance: Investing, money, budgeting (higher temporal + importance weights)
    - health: Medical, wellness, fitness (balanced weights)
    - relationships: Family, friends, social dynamics (higher emotional weight)
    - creativity: Ideas, projects, brainstorming (higher semantic weight)

    Args:
        user_id: User identifier
        query: Search query describing the decision context
        limit: Maximum number of memories to retrieve (default: 100, range: 20-1000)
        persona: Persona context for weighted retrieval (default: "identity")

    Returns:
        dict: Result with status, memory_count, persona used, and formatted memories
    """
    start_time = time.time()

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

    # Validate persona parameter
    valid_personas = ["identity", "finance", "health", "relationships", "creativity"]
    if persona not in valid_personas:
        logger.warning(f"Invalid persona '{persona}', defaulting to 'identity'")
        persona = "identity"

    try:
        logger.info(
            "Retrieving memories via persona-aware MCP tool",
            extra={
                "user_id": user_id,
                "query": query,
                "limit": limit,
                "persona": persona
            }
        )

        # Build POST request body for persona-aware retrieval
        request_body = {
            "user_id": user_id,
            "query": query,
            "limit": limit,
            "persona_context": {
                "forced_persona": persona
            },
            "include_narrative": False,
            "explain": False
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{memories_url}/v1/retrieve",
                json=request_body,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                # Parse persona-aware response format
                # Response: {"persona": {...}, "results": {"memories": [...], ...}}
                persona_info = result.get("persona", {})
                selected_persona = persona_info.get("selected", persona)
                confidence = persona_info.get("confidence", 0.0)

                results_obj = result.get("results", {})
                memories = results_obj.get("memories", [])

                if duration_ms > 300:
                    logger.warning(
                        "Memory retrieval via MCP tool exceeded 300ms target",
                        extra={
                            "user_id": user_id,
                            "query": query,
                            "duration_ms": duration_ms,
                            "memory_count": len(memories),
                            "persona": selected_persona,
                            "exceeded_target": True
                        }
                    )
                else:
                    logger.info(
                        "Memories retrieved successfully via persona-aware MCP tool",
                        extra={
                            "user_id": user_id,
                            "query": query,
                            "memory_count": len(memories),
                            "persona": selected_persona,
                            "confidence": confidence,
                            "duration_ms": duration_ms
                        }
                    )

                if not memories:
                    return {
                        "status": "success",
                        "memory_count": 0,
                        "persona": selected_persona,
                        "memories": [],
                        "message": "No past decision history found for this query. Recommendations will be based on general knowledge."
                    }

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
                    "persona": selected_persona,
                    "memories": formatted_memories,
                    "message": f"Retrieved {len(memories)} relevant memories using '{selected_persona}' persona."
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

        return {
            "status": "error",
            "memory_count": 0,
            "memories": [],
            "message": f"Unexpected error: {str(e)}. Continuing without memory context.",
            "error_code": "INTERNAL_ERROR"
        }


retrieve_memories_tool = {
    "name": "retrieve_memories",
    "description": """Retrieve relevant memories from agentic-memories service for personalized decision support.

Use this tool when the user asks for advice, recommendations, or decisions.
Memories are retrieved with persona-aware weighting based on the selected persona.

PERSONA SELECTION GUIDE - Choose based on conversation topic:
- "identity" (default): General context, who the person is, background info
- "finance": Investing, stocks, money, budgeting (prioritizes recent decisions and high-importance memories)
- "health": Medical conditions, wellness, fitness, diet (balanced across all factors)
- "relationships": Family, friends, social dynamics (prioritizes emotionally significant memories)
- "creativity": Ideas, projects, brainstorming (prioritizes conceptual and thematic connections)
""",
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
            },
            "persona": {
                "type": "string",
                "description": "Persona context for weighted retrieval. Choose based on conversation topic.",
                "enum": ["identity", "finance", "health", "relationships", "creativity"],
                "default": "identity"
            }
        },
        "required": ["user_id", "query"]
    },
    "handler": retrieve_memories_tool_handler
}


# =============================================================================
# Compact Memories Tool
# =============================================================================

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
    - Consolidation: Combines related memories into "golden records"

    Args:
        user_id: User identifier
        skip_reextract: Skip expensive LLM re-extraction (default: True)
        skip_consolidate: Skip memory consolidation (default: False)

    Returns:
        dict: Result with status and compaction statistics
    """
    start_time = time.time()

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
        async with httpx.AsyncClient(timeout=300.0) as client:
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
