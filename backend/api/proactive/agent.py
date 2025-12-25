"""
Wake-Up Agent Module

LLM-driven agent that executes fired triggers by reading action_context as a briefing,
gathering fresh dynamic state, and composing contextual proactive messages.

This is the core execution engine for the proactive AI system, bridging the gap between
trigger firing (time-based or condition-based) and message delivery.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytz
import redis.asyncio as redis

from api.config import get_config
from api.logging import get_logger
from api.llm_client import LLMClient
from api.mcp_client import MCPClient, MCPClientError
from api.profile import ProfileManager
from api.memory_client import MemoryClient

try:
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator
    class langfuse_context:
        @staticmethod
        def update_current_observation(**kwargs):
            pass

logger = get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class DynamicState:
    """
    Fresh dynamic context gathered at wake-up time.

    This state is injected alongside the static action_context to provide
    the wake-up agent with current information for decision-making.
    """
    current_datetime: datetime
    day_of_week: str
    market_status: str  # "open" or "closed"
    hours_since_last_message: float
    recent_context: Optional[str]  # Recent conversation summary from agentic-memories
    profile: Optional[Dict[str, Any]]  # Fresh user profile


@dataclass
class WakeUpResult:
    """
    Result returned by wake-up agent execution.

    Contains the agent's decision (skip or send message), composed message if applicable,
    tools called during execution, and reasoning for observability.
    """
    skip: bool
    skip_reason: Optional[str]
    message: Optional[str]
    tools_called: List[str]
    reasoning: str


# ============================================================================
# Restricted Tools (State-Modifying)
# ============================================================================

RESTRICTED_TOOLS = [
    "add_holding",
    "update_holding",
    "remove_holding",
    "create_trigger",
    "update_trigger",
    "delete_trigger",
]


# ============================================================================
# Dynamic State Gathering
# ============================================================================

@observe(name="gather_dynamic_state", as_type="span")
async def gather_dynamic_state(user_id: str, timezone: str = "America/Los_Angeles") -> DynamicState:
    """
    Gather fresh dynamic context at wake-up time.

    Fetches:
    - Current time in user's timezone
    - Market status (simple open/closed check)
    - Hours since user last messaged
    - Recent conversation summary from agentic-memories
    - Fresh user profile

    Args:
        user_id: User identifier
        timezone: User's timezone (default: America/Los_Angeles)

    Returns:
        DynamicState with fresh context
    """
    start_time = time.time()

    try:
        # Get current time in user's timezone
        user_tz = pytz.timezone(timezone)
        current_time = datetime.now(user_tz)

        # Get market status (simple open/closed check)
        # US stock market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
        et_tz = pytz.timezone("America/New_York")
        et_time = datetime.now(et_tz)
        is_weekday = et_time.weekday() < 5  # Monday=0, Friday=4
        is_market_hours = (et_time.hour == 9 and et_time.minute >= 30) or (10 <= et_time.hour < 16)
        market_status = "open" if (is_weekday and is_market_hours) else "closed"

        # Get hours since last user message from Redis
        # Uses activity tracking from Story 13.8
        config = get_config()
        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", 6379))
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )

        try:
            last_activity_str = await redis_client.get(f"user:{user_id}:last_activity")
            if last_activity_str:
                last_activity = datetime.fromisoformat(last_activity_str)
                # Make timezone-aware if needed
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                current_utc = datetime.now(timezone.utc)
                hours_since = (current_utc - last_activity).total_seconds() / 3600
            else:
                hours_since = 24.0  # Default if no activity tracked
        except Exception as e:
            logger.warning(f"Failed to get last activity from Redis: {e}")
            hours_since = 24.0  # Default on error
        finally:
            await redis_client.aclose()

        # Get recent conversation summary from agentic-memories
        # Uses 24h lookback for tone adjustment
        recent_context = None
        try:
            memory_client = MemoryClient()
            # Try to get recent context - this is a best-effort call
            # The MemoryClient doesn't have a get_recent_summary method, so we'll use a placeholder
            # In production, this would call the agentic-memories API for recent conversations
            recent_context = None  # TODO: Implement when agentic-memories supports this
        except Exception as e:
            logger.warning(f"Failed to get recent context: {e}")
            recent_context = None

        # Get user profile from cache (non-blocking)
        profile = None
        try:
            profile_manager = ProfileManager()
            profile = await profile_manager.load_profile_from_cache(user_id)
            # Trigger background refresh for freshness (non-blocking)
            await profile_manager.refresh_profile_background(user_id)
            await profile_manager.close()
        except Exception as e:
            logger.warning(f"Failed to get fresh profile: {e}")
            profile = None

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Dynamic state gathered",
            extra={
                "user_id": user_id,
                "market_status": market_status,
                "hours_since_last_message": round(hours_since, 2),
                "has_recent_context": recent_context is not None,
                "has_profile": profile is not None,
                "duration_ms": duration_ms
            }
        )

        # Debug: Log full dynamic state details
        logger.debug(
            "Full dynamic state",
            extra={
                "user_id": user_id,
                "current_datetime": current_time.isoformat(),
                "day_of_week": current_time.strftime("%A"),
                "market_status": market_status,
                "hours_since_last_message": hours_since,
                "recent_context": recent_context,
                "profile": profile
            }
        )

        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                output={
                    "market_status": market_status,
                    "hours_since_last_message": round(hours_since, 2),
                    "has_recent_context": recent_context is not None,
                    "has_profile": profile is not None
                }
            )

        return DynamicState(
            current_datetime=current_time,
            day_of_week=current_time.strftime("%A"),
            market_status=market_status,
            hours_since_last_message=hours_since,
            recent_context=recent_context,
            profile=profile
        )

    except Exception as e:
        logger.error(f"Failed to gather dynamic state: {e}", exc_info=True)
        # Return minimal state on error
        return DynamicState(
            current_datetime=datetime.now(pytz.UTC),
            day_of_week=datetime.now(pytz.UTC).strftime("%A"),
            market_status="unknown",
            hours_since_last_message=24.0,
            recent_context=None,
            profile=None
        )


# ============================================================================
# Prompt Construction
# ============================================================================

def build_agent_prompt(
    trigger_data: Dict[str, Any],
    dynamic_state: DynamicState,
    available_tools: List[str]
) -> str:
    """
    Build comprehensive wake-up agent prompt with all sections.

    Includes:
    - Trigger metadata (name, type, fire_count, last_fired)
    - Dynamic state (current time, market status, recent context, fresh profile)
    - Action context (briefing from creation LLM)
    - Available tools list
    - Response format specification
    - Tone adjustment guidance based on recent context

    Args:
        trigger_data: Trigger document with action_context
        dynamic_state: Fresh dynamic state
        available_tools: List of tool names available to agent

    Returns:
        str: Complete agent prompt
    """
    action_context = trigger_data.get("action_context", {})

    # Format profile for display
    profile_str = "No profile available."
    if dynamic_state.profile:
        try:
            profile_str = json.dumps(dynamic_state.profile, indent=2)
        except Exception:
            profile_str = str(dynamic_state.profile)

    # Format recent context
    recent_context_str = dynamic_state.recent_context or "No recent conversation history."

    # Build tone adjustment guidance
    hours = dynamic_state.hours_since_last_message
    if hours < 1:
        tone_guidance = (
            f"Recent Contact: User messaged {int(hours * 60)} minutes ago.\n"
            "Be BRIEF and CASUAL - they just talked to you. Keep it under 2 sentences."
        )
    elif hours < 24:
        tone_guidance = (
            f"Recent Contact: User messaged {int(hours)} hours ago.\n"
            "Normal conversational tone. Be helpful and provide meaningful detail."
        )
    else:
        tone_guidance = (
            f"Recent Contact: User messaged {int(hours)} hours ago (over a day).\n"
            "Warmer greeting is appropriate. Provide comprehensive, valuable information."
        )

    prompt_parts = [
        "You are Annie's proactive subsystem. A trigger has fired and you need to decide",
        "whether to send a message and what to say.",
        "",
        "## Trigger Information",
        "",
        f"Trigger Name: {trigger_data.get('intent_name', 'Unnamed')}",
        f"Trigger Type: {trigger_data.get('trigger_type', 'unknown')}",
        f"Fire Count: {trigger_data.get('fire_count', 0)} (times this has fired before)",
        f"Last Fired: {trigger_data.get('last_fired', 'Never')}",
        "",
        "## DYNAMIC CONTEXT (Current State)",
        "",
        "This is LIVE information at the moment of execution:",
        "",
        f"Current Time: {dynamic_state.current_datetime.isoformat()} ({dynamic_state.day_of_week})",
        f"Market Status: {dynamic_state.market_status}",
        f"Hours Since User Last Messaged: {dynamic_state.hours_since_last_message:.1f}",
        "",
        "### Recent Conversation Summary",
        recent_context_str,
        "",
        "### Current User Profile",
        profile_str,
        "",
        "⚠️ IMPORTANT: If recent_context indicates the user is going through something",
        "difficult (personal issues, bad news, stress), adjust your tone accordingly.",
        "A chirpy 'Great news about your portfolio!' is inappropriate after a breakup discussion.",
        "",
        "## Your Briefing (Created at Trigger Setup)",
        "",
        "The following action_context was written when this trigger was created.",
        "It contains the user's original intent and preferences:",
        "",
        json.dumps(action_context, indent=2),
        "",
        "## Available Tools",
        "",
        "You have access to ALL read-only tools from the MCP server:",
        "",
        ", ".join(available_tools) if available_tools else "No tools available",
        "",
        "Use any tools you need to accomplish your briefing's intent.",
        "The action_context's suggestions are guidance, but you have full flexibility.",
        "ALWAYS fetch fresh data - do not rely on any holdings/values mentioned in user_context.",
        "",
        "## Your Task",
        "",
        "1. Note the current date/time and recent context",
        "2. Read your briefing carefully",
        "3. Follow the execution_instructions step by step",
        "4. Fetch fresh data using tools (REQUIRED for financial data)",
        "5. Apply any skip conditions from your briefing",
        "6. Consider the recent_context when choosing tone",
        "7. If proceeding, compose a message following message_guidance",
        "8. Handle any edge_cases that apply",
        "",
        "## Response Format",
        "",
        "Return JSON:",
        "{",
        '    "skip": true/false,',
        '    "skip_reason": "reason if skipping",',
        '    "message": "the message to send if not skipping",',
        '    "tools_called": ["list of tools you called"],',
        '    "reasoning": "thorough explanation of your analysis and decision"',
        "}",
        "",
        "## Critical Rules",
        "",
        "1. ACTION_CONTEXT IS YOUR GUIDE - Follow your briefing's preferences for tone, length, and style",
        "2. THINK DEEPLY - Analyze the situation thoroughly before composing your message",
        "3. USE TOOLS LIBERALLY - Call relevant tools to gather fresh, current information",
        "4. FETCH FRESH DATA - Never use stale data. Always get live data via tools when needed",
        "5. DELIVER VALUE - Unless briefing says 'brief', provide rich content with insights and context",
        "6. RESPECT SKIP CONDITIONS - don't message when briefing says not to",
        "7. CONSIDER RECENT CONTEXT - adjust tone based on user's recent state",
        "8. MATCH THE TONE - use the voice examples in your briefing as guide",
        "9. EXPLAIN WHY - A good message explains why things matter, not just what the numbers are",
        "",
        "## Tone Adjustment",
        "",
        tone_guidance,
    ]

    return "\n".join(prompt_parts)


# ============================================================================
# Response Parsing
# ============================================================================

def parse_agent_response(response_content: str, tools_called: List[str]) -> WakeUpResult:
    """
    Parse LLM response into WakeUpResult.

    Handles both JSON and plain text responses gracefully.

    Args:
        response_content: LLM response content
        tools_called: List of tools called during execution

    Returns:
        WakeUpResult parsed from response
    """
    try:
        # Strip markdown code blocks if present (Gemini often wraps JSON in ```json ... ```)
        clean_content = response_content.strip()
        if clean_content.startswith("```"):
            # Remove opening ```json or ``` 
            lines = clean_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]  # Remove first line (```json)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # Remove last line (```)
            clean_content = "\n".join(lines).strip()
            logger.debug(
                "Stripped markdown code blocks from response",
                extra={"original_length": len(response_content), "clean_length": len(clean_content)}
            )

        # Try to parse as JSON
        data = json.loads(clean_content)

        return WakeUpResult(
            skip=data.get("skip", False),
            skip_reason=data.get("skip_reason"),
            message=data.get("message"),
            tools_called=data.get("tools_called", tools_called),
            reasoning=data.get("reasoning", "No reasoning provided")
        )
    except json.JSONDecodeError:
        # Fallback: treat as plain message
        logger.warning("Failed to parse agent response as JSON, treating as message")
        return WakeUpResult(
            skip=False,
            skip_reason=None,
            message=response_content,
            tools_called=tools_called,
            reasoning="Fallback: LLM did not return JSON"
        )


# ============================================================================
# Wake-Up Agent Execution
# ============================================================================

@observe(name="wake_up_agent_execution", as_type="span")
async def execute_wake_up_agent(
    trigger_data: Dict[str, Any],
    user_id: str,
    timezone: str = "America/Los_Angeles"
) -> WakeUpResult:
    """
    Execute wake-up agent for a fired trigger.

    This is the core execution function that:
    1. Gathers fresh dynamic state
    2. Gets available tools from MCP server (filtered for restrictions)
    3. Builds comprehensive agent prompt
    4. Executes LLM with tool access
    5. Parses response into WakeUpResult

    The agent has a 10-minute timeout and access to all read-only tools.

    Args:
        trigger_data: Trigger document including action_context
        user_id: User who owns this trigger
        timezone: User's timezone (default: America/Los_Angeles)

    Returns:
        WakeUpResult with skip status, message if any, and metadata

    Raises:
        asyncio.TimeoutError: If execution exceeds 10 minutes
        Exception: For other execution errors (logged and converted to skip result)
    """
    start_time = time.time()

    # Update Langfuse observation with trigger metadata
    if LANGFUSE_AVAILABLE:
        langfuse_context.update_current_observation(
            metadata={
                "trigger_id": trigger_data.get("id"),
                "trigger_type": trigger_data.get("trigger_type"),
                "intent_name": trigger_data.get("intent_name"),
                "user_id": user_id
            }
        )

    logger.info(
        "Starting wake-up agent execution",
        extra={
            "trigger_id": trigger_data.get("id"),
            "trigger_type": trigger_data.get("trigger_type"),
            "intent_name": trigger_data.get("intent_name"),
            "user_id": user_id
        }
    )

    try:
        # 1. Gather dynamic state (FRESH at execution time)
        dynamic_state = await gather_dynamic_state(user_id, timezone)

        # 2. Get available tools dynamically from MCP server
        async with MCPClient() as mcp_client:
            try:
                mcp_tools = await mcp_client.list_tools()

                # Filter out restricted tools
                allowed_tools = [
                    tool for tool in mcp_tools
                    if tool.get("name") not in RESTRICTED_TOOLS
                ]

                tool_names = [tool.get("name") for tool in allowed_tools]

                logger.info(
                    "Tools available to agent",
                    extra={
                        "total_tools": len(mcp_tools),
                        "allowed_tools": len(allowed_tools),
                        "restricted_tools": len(RESTRICTED_TOOLS)
                    }
                )
            except MCPClientError as e:
                logger.error(f"Failed to fetch tools from MCP server: {e}")
                allowed_tools = []
                tool_names = []

        # 3. Build the prompt with both static and dynamic context
        prompt = build_agent_prompt(trigger_data, dynamic_state, tool_names)

        # Debug: Log the action_context and prompt
        logger.debug(
            "Wake-up agent prompt built",
            extra={
                "trigger_id": trigger_data.get("id"),
                "user_id": user_id,
                "action_context": trigger_data.get("action_context"),
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:500] if prompt else None
            }
        )

        # 4. Execute with full tool access (10 minute timeout)
        tools_called = []

        async with LLMClient() as llm_client:
            # Create messages list
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Execute this trigger now. Follow your briefing."}
            ]

            # Convert MCP tools to LLM function format
            llm_tools = []
            if allowed_tools:
                try:
                    llm_tools = llm_client.convert_mcp_tools_to_functions(allowed_tools)
                except Exception as e:
                    logger.warning(f"Failed to convert MCP tools: {e}")
                    llm_tools = []

            # Execute with timeout wrapper
            async def _execute_with_tools():
                """Inner function for timeout wrapper."""
                nonlocal tools_called

                # Get streaming provider to handle tool calls
                async with MCPClient() as mcp_client:
                    response_content = ""
                    chunk_count = 0

                    # Use streaming to handle tool calls
                    async for chunk in llm_client.stream_chat_completion(
                        messages=messages,
                        tools=llm_tools,
                        mcp_client=mcp_client
                    ):
                        chunk_count += 1
                        chunk_type = chunk.get("type")
                        # #region agent log
                        logger.debug(
                            "Agent received chunk",
                            extra={
                                "chunk_count": chunk_count,
                                "chunk_type": chunk_type,
                                "chunk_keys": list(chunk.keys()),
                                "chunk_preview": str(chunk)[:200]
                            }
                        )
                        # #endregion
                        if chunk_type == "content":
                            delta = chunk.get("delta", "")
                            response_content += delta
                            # #region agent log
                            logger.debug(
                                "Agent content chunk",
                                extra={
                                    "delta_length": len(delta),
                                    "total_length": len(response_content)
                                }
                            )
                            # #endregion
                        elif chunk_type == "token":
                            # Gemini returns "token" type with "content" field
                            token_content = chunk.get("content", "")
                            response_content += token_content
                            # #region agent log
                            logger.debug(
                                "Agent token chunk",
                                extra={
                                    "token_length": len(token_content),
                                    "total_length": len(response_content)
                                }
                            )
                            # #endregion
                        elif chunk_type == "tool_call":
                            # Track tool calls
                            tool_name = chunk.get("name")
                            if tool_name:
                                tools_called.append(tool_name)

                    # #region agent log
                    logger.info(
                        "Agent streaming complete",
                        extra={
                            "total_chunks": chunk_count,
                            "response_length": len(response_content),
                            "response_preview": response_content[:200] if response_content else "EMPTY"
                        }
                    )
                    # #endregion
                    return response_content

            try:
                # Execute with 10 minute timeout
                response_content = await asyncio.wait_for(
                    _execute_with_tools(),
                    timeout=600  # 10 minutes
                )
            except asyncio.TimeoutError:
                logger.error("Agent execution timed out after 10 minutes")
                duration_ms = int((time.time() - start_time) * 1000)

                result = WakeUpResult(
                    skip=True,
                    skip_reason="Agent execution timeout (10 minutes)",
                    message=None,
                    tools_called=tools_called,
                    reasoning="Execution exceeded 10 minute timeout"
                )

                if LANGFUSE_AVAILABLE:
                    langfuse_context.update_current_observation(
                        output={
                            "skip": result.skip,
                            "skip_reason": result.skip_reason,
                            "tools_called": result.tools_called,
                            "duration_ms": duration_ms,
                            "timed_out": True
                        }
                    )

                return result

        # 5. Parse response
        result = parse_agent_response(response_content, tools_called)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Wake-up agent execution complete",
            extra={
                "trigger_id": trigger_data.get("id"),
                "user_id": user_id,
                "skip": result.skip,
                "skip_reason": result.skip_reason,
                "message_length": len(result.message) if result.message else 0,
                "tools_called": result.tools_called,
                "duration_ms": duration_ms
            }
        )

        # Update Langfuse observation with output
        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                output={
                    "skip": result.skip,
                    "skip_reason": result.skip_reason,
                    "message_length": len(result.message) if result.message else 0,
                    "tools_called": result.tools_called,
                    "duration_ms": duration_ms
                }
            )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Wake-up agent execution failed",
            extra={
                "trigger_id": trigger_data.get("id"),
                "user_id": user_id,
                "error": str(e),
                "duration_ms": duration_ms
            },
            exc_info=True
        )

        # Return skip result on error
        result = WakeUpResult(
            skip=True,
            skip_reason=f"Agent execution error: {str(e)}",
            message=None,
            tools_called=[],
            reasoning=f"Error during execution: {str(e)}"
        )

        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                output={
                    "skip": result.skip,
                    "skip_reason": result.skip_reason,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

        return result
