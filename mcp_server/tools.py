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


def health_check_tool_handler() -> Dict[str, Any]:
    """
    Health check tool handler.
    
    Returns:
        Health status dictionary
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }


# Health check tool definition
health_check_tool = {
    "name": "health_check",
    "description": "Check the health status of the MCP (Model Context Protocol) server. Use this tool when asked about server health, status, or availability. Returns the current health status and timestamp.",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "handler": health_check_tool_handler
}


async def store_memory_tool_handler(
    user_id: str,
    history: list,
    metadata: dict = None
) -> Dict[str, Any]:
    """
    Store conversation transcript in agentic-memories service.

    The service will automatically extract memories from the conversation history.

    Args:
        user_id: User identifier
        history: List of conversation messages with role and content
        metadata: Optional metadata (platform, conversation_id, etc.)

    Returns:
        dict: Result with status, memories_created, and memory IDs
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Build request payload
    payload = {
        "user_id": user_id,
        "history": history
    }
    if metadata:
        payload["metadata"] = metadata

    # Make HTTP request to agentic-memories with retry logic
    max_retries = 3
    retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    async with httpx.AsyncClient(timeout=180.0) as client:  # 3 minutes for LLM-based memory extraction and storage
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Storing conversation transcript via MCP tool",
                    extra={
                        "user_id": user_id,
                        "message_count": len(history),
                        "attempt": attempt + 1,
                        "url": memories_url
                    }
                )

                response = await client.post(
                    f"{memories_url}/v1/store",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                duration_ms = int((time.time() - start_time) * 1000)

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        "Conversation transcript stored successfully via MCP tool",
                        extra={
                            "user_id": user_id,
                            "memories_created": result.get("memories_created", 0),
                            "duration_ms": duration_ms,
                            "attempts": attempt + 1
                        }
                    )
                    return {
                        "status": "success",
                        "memories_created": result.get("memories_created", 0),
                        "memory_ids": result.get("ids", []),
                        "summary": result.get("summary", "")
                    }
                else:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except Exception:
                        error_msg = response.text or error_msg

                    logger.error(
                        "Memory storage failed via MCP tool",
                        extra={
                            "user_id": user_id,
                            "status_code": response.status_code,
                            "error": error_msg,
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms
                        }
                    )

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        return {
                            "status": "error",
                            "message": f"Failed to store memory: {error_msg}",
                            "error_code": response.status_code
                        }

                    # Retry on server errors (5xx)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
                        continue

                    return {
                        "status": "error",
                        "message": f"Failed to store memory after {max_retries} attempts: {error_msg}",
                        "error_code": response.status_code
                    }

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Network error storing memory via MCP tool",
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
                    "Unexpected error storing memory via MCP tool",
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
    "description": "Store conversation transcript in agentic-memories service for long-term memory retention. The service will automatically extract key information (decisions, preferences, topics) from the conversation history. Use this tool when a conversation ends (user says goodbye/thanks) or when significant decisions are made.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier for memory storage"
            },
            "history": {
                "type": "array",
                "description": "Recent conversation messages (2-3 messages) containing the information to store. Include only the relevant context needed for memory extraction.",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": ["user", "assistant", "system"],
                            "description": "Message role"
                        },
                        "content": {
                            "type": "string",
                            "description": "Message content"
                        }
                    },
                    "required": ["role", "content"]
                }
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata (platform, conversation_id, etc.)",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "Platform identifier (e.g., telegram, web)"
                    },
                    "conversation_id": {
                        "type": "string",
                        "description": "Conversation identifier"
                    }
                }
            }
        },
        "required": ["user_id", "history"]
    },
    "handler": store_memory_tool_handler
}


async def retrieve_memories_tool_handler(
    user_id: str,
    query: str,
    limit: int = 50,
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
        limit: Maximum number of memories to retrieve (default: 50, max: 1000)
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

    # Validate limit parameter
    if limit < 50 or limit > 1000:
        logger.warning(f"Invalid limit {limit}, clamping to range [50, 1000]")
        limit = max(50, min(1000, limit))

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
                "description": "Maximum number of memories to retrieve (default: 50, max: 100)",
                "default": 50,
                "minimum": 50,
                "maximum": 100
            }
        },
        "required": ["user_id", "query"]
    },
    "handler": retrieve_memories_tool_handler
}


async def get_user_profile_tool_handler(
    user_id: str
) -> Dict[str, Any]:
    """
    Retrieve user profile from agentic-memories service.

    The profile includes 21 fields across 5 categories (basics, preferences, goals,
    interests, background) that are automatically extracted from conversations.
    Profile extraction happens during /v1/store calls.

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

        async with httpx.AsyncClient(timeout=5.0) as client:
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
    "description": "Retrieve user profile from agentic-memories service. Returns 21 profile fields across 5 categories (basics, preferences, goals, interests, background) that are automatically extracted from conversations. Use this tool to get user context for personalized responses. Profile extraction happens automatically during conversation storage.",
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
# Portfolio Management Tools (Epic 10)
# =============================================================================

import re

# Ticker validation pattern: 1-10 uppercase alphanumeric + dots (for BRK.B style)
TICKER_PATTERN = re.compile(r'^[A-Z0-9\.]{1,10}$')


def normalize_ticker(ticker: str) -> Optional[str]:
    """
    Normalize ticker to uppercase and validate format.

    Args:
        ticker: Stock ticker symbol (e.g., 'aapl', 'GOOGL', 'BRK.B')

    Returns:
        Normalized uppercase ticker or None if invalid
    """
    if not ticker:
        return None

    normalized = ticker.upper().strip()

    if not normalized:
        return None

    if not TICKER_PATTERN.match(normalized):
        logger.warning(f"Invalid ticker format rejected: {ticker}")
        return None

    return normalized


async def get_portfolio_tool_handler(
    user_id: str
) -> Dict[str, Any]:
    """
    Get user's investment portfolio holdings from agentic-memories service.

    Args:
        user_id: User identifier

    Returns:
        dict: Portfolio with holdings array, total count, and last updated timestamp
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
                "url": memories_url
            }
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
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
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "user_id": result.get("user_id", user_id),
                    "holdings": holdings,
                    "total_holdings": result.get("total_holdings", len(holdings)),
                    "last_updated": result.get("last_updated")
                }

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
    "description": "Get user's investment portfolio holdings. Returns all stocks, ETFs, and other assets the user owns with ticker symbols, share counts, and average purchase prices. Use this tool when the user asks about their portfolio, holdings, investments, or what stocks they own.",
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

        async with httpx.AsyncClient(timeout=10.0) as client:
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
