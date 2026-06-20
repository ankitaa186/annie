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
from api.state import StateManager

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
    profile: Optional[Dict[str, Any]]  # Fresh user profile from get_user_profile MCP tool
    conversation_history: Optional[List[Dict[str, Any]]]  # Recent conversation messages


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
async def gather_dynamic_state(user_id: str, user_timezone: str = "America/Los_Angeles") -> DynamicState:
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
        user_timezone: User's timezone (default: America/Los_Angeles)

    Returns:
        DynamicState with fresh context
    """
    start_time = time.time()

    try:
        # Get current time in user's timezone
        user_tz = pytz.timezone(user_timezone)
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
            last_activity_str = await redis_client.get(f"activity:{user_id}:last_message")
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
            await redis_client.close()

        # Get recent conversation summary from agentic-memories
        # Uses 24h lookback for tone adjustment
        recent_context = None
        try:
            MemoryClient()
            # Try to get recent context - this is a best-effort call
            # The MemoryClient doesn't have a get_recent_summary method, so we'll use a placeholder
            # In production, this would call the agentic-memories API for recent conversations
            recent_context = None  # TODO: Implement when agentic-memories supports this
        except Exception as e:
            logger.warning(f"Failed to get recent context: {e}")
            recent_context = None

        # Get conversation history from StateManager
        conversation_history = None
        try:
            async with StateManager() as state_manager:
                session = await state_manager.get_session(user_id)
                if session:
                    conversation_id = session.get("conversation_id")
                    if conversation_id:
                        history = await state_manager.get_conversation_history(conversation_id)
                        # Limit to last 20 messages to keep context manageable
                        conversation_history = history[-20:] if history else []
                        logger.info(
                            "Loaded conversation history for proactive agent",
                            extra={
                                "user_id": user_id,
                                "conversation_id": conversation_id,
                                "message_count": len(conversation_history)
                            }
                        )
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            conversation_history = None

        # Get fresh user profile via ProfileManager (calls MCP tool, falls back to cache)
        profile = None
        try:
            profile_manager = ProfileManager()
            profile = await profile_manager.fetch_profile_fresh(user_id)
            await profile_manager.close()
        except Exception as e:
            logger.warning(f"Failed to fetch fresh profile: {e}")
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
                "has_conversation_history": conversation_history is not None,
                "conversation_history_count": len(conversation_history) if conversation_history else 0,
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
                "profile": profile,
                "conversation_history_count": len(conversation_history) if conversation_history else 0
            }
        )

        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                output={
                    "market_status": market_status,
                    "hours_since_last_message": round(hours_since, 2),
                    "has_recent_context": recent_context is not None,
                    "has_profile": profile is not None,
                    "has_conversation_history": conversation_history is not None,
                    "conversation_history_count": len(conversation_history) if conversation_history else 0
                }
            )

        return DynamicState(
            current_datetime=current_time,
            day_of_week=current_time.strftime("%A"),
            market_status=market_status,
            hours_since_last_message=hours_since,
            recent_context=recent_context,
            profile=profile,
            conversation_history=conversation_history
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
            profile=None,
            conversation_history=None
        )


# ============================================================================
# Prompt Construction
# ============================================================================

def is_research_trigger(trigger_data: Dict[str, Any]) -> bool:
    """
    Detect if this trigger is for deep research based on action_type or intent_name.

    Args:
        trigger_data: Trigger document to check

    Returns:
        bool: True if this is a research-type trigger
    """
    action_type = trigger_data.get("action_type", "").lower()
    intent_name = trigger_data.get("intent_name", "").lower()

    research_indicators = ["research", "deep dive", "investigate", "analyze", "comprehensive"]

    # Check action_type
    if action_type == "research":
        return True

    # Check intent_name for research keywords
    for indicator in research_indicators:
        if indicator in intent_name:
            return True

    return False


# Research protocol for deep research triggers
RESEARCH_PROTOCOL = """
## RESEARCH PROTOCOL (MANDATORY)

This is a DEEP RESEARCH trigger. You must perform exhaustive research before responding.
Do NOT answer immediately. Follow this protocol:

### 1. PLAN
Think through what you need to find. Break down the research question into
specific search queries. Think about:
- What are the key aspects to investigate?
- What perspectives or sources would be valuable?
- What facts need to be verified?

### 2. EXECUTE
Use `web_search` and `web_crawl` extensively. You typically need **5-10 distinct searches**
to properly cover a topic. For each search:
- Use different angles/keywords to get diverse results
- Follow up on promising results with `web_crawl` to read full content
- Use `reddit_search` for community opinions and real user experiences
- For stock/company research, use `get_financials` for financial statements, earnings, revenue data
- For deep due diligence, use `get_sec_filings` for SEC 10-K/10-Q filings, risk factors, MD&A sections

### 3. CRITIQUE
After each round of tool outputs, self-critique:
- "Do I have enough comprehensive data?"
- "Are there gaps in my research?"
- "Have I considered multiple perspectives?"
- "Are my sources credible and recent?"

If the answer to any of these is "no", LOOP back to EXECUTE with refined searches.

### 4. FINALIZE — Response Format (STRICT)

Reply with ONLY the final report as plain markdown. The entire response is delivered
verbatim to the user over Telegram (which renders a small HTML subset), so:

- No JSON. No envelope. No ``` fences around the whole thing.
- No preamble like "Here is your report:" — start directly with the title or content.
- Use normal markdown: `#`/`##` headers, `-` bullets, `**bold**`, `*italic*`, links,
  inline `code`, fenced code blocks for snippets. Tables are fine; they get converted
  to a readable key/value form in Telegram.
- Real newlines between paragraphs. Never write a literal `\\n` — press enter instead.
- Cite sources inline with markdown links where it matters.

If (and only if) you genuinely cannot produce a useful report — e.g. every search
failed, or the topic is out of scope — reply with a short markdown explanation of
what went wrong. Don't invent a skip marker; just say it plainly.

### Important Guidelines
- Take your time - deep research is expected to take 5-15 minutes
- Quality over speed - be thorough
- Multiple searches are expected and encouraged
- Synthesize information, don't just list search results
- Provide actionable insights, not just data dumps
"""


# Legacy marker kept for backward compatibility with mid-flight responses from the
# previous protocol version that emitted JSON metadata + `---REPORT---` + markdown.
RESEARCH_REPORT_MARKER = "---REPORT---"


def _unescape_stray_sequences(text: str) -> str:
    """
    Convert literal backslash-escape sequences to real characters.

    When an LLM double-escapes a JSON string (emits `\\\\n` where it meant `\\n`),
    `json.loads` produces the 2-character string `\\n` instead of a newline. This
    best-effort cleanup rescues those cases so the user sees real line breaks
    instead of literal `\\n` in their Telegram message.

    Only runs when the text actually contains these literal sequences, so normal
    messages are untouched.
    """
    if not text:
        return text
    # Cheap guard: only do work when literal backslash-escapes are present.
    if "\\n" not in text and "\\t" not in text and '\\"' not in text and "\\r" not in text:
        return text
    # Order matters: handle \\r\\n pair before \\n alone.
    return (
        text.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace('\\"', '"')
    )


def _strip_outer_code_fence(text: str) -> str:
    """Strip a leading ``` fence and matching trailing ```, if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    lines = lines[1:]  # drop opening ```foo
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


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
    - Research protocol (for research-type triggers)

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
    recent_context_str = dynamic_state.recent_context or "No recent conversation summary available."

    # Format conversation history
    conversation_history_str = "No conversation history available."
    if dynamic_state.conversation_history:
        history_lines = []
        for msg in dynamic_state.conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            history_lines.append(f"[{role}]: {content}")
        conversation_history_str = "\n".join(history_lines)

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
        "### Conversation History (Last 20 Messages)",
        "",
        "This is the actual conversation history with the user. Use this to understand",
        "what has been discussed recently and avoid repeating information:",
        "",
        conversation_history_str,
        "",
        "### Current User Profile",
        profile_str,
        "",
        "⚠️ IMPORTANT: If conversation history or recent_context indicates the user is going through something",
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

    # Inject research protocol for research-type triggers
    if is_research_trigger(trigger_data):
        prompt_parts.append("")
        prompt_parts.append(RESEARCH_PROTOCOL)
        logger.info(
            "Research protocol injected into agent prompt",
            extra={
                "trigger_id": trigger_data.get("id"),
                "intent_name": trigger_data.get("intent_name"),
                "action_type": trigger_data.get("action_type")
            }
        )

    return "\n".join(prompt_parts)


# ============================================================================
# Response Parsing
# ============================================================================

def parse_agent_response(
    response_content: str,
    tools_called: List[str],
    is_research: bool = False,
) -> WakeUpResult:
    """
    Parse LLM response into WakeUpResult.

    Research triggers return plain markdown (no JSON envelope); non-research
    triggers still use a JSON envelope because they legitimately need a
    structured skip decision (quiet hours, gate conditions, etc.).

    Args:
        response_content: Raw LLM output.
        tools_called: Tools observed during streaming — used as the
            authoritative list regardless of what the LLM claims.
        is_research: True for research triggers; skips JSON parsing.
    """
    if is_research:
        return _parse_research_response(response_content, tools_called)
    return _parse_json_envelope_response(response_content, tools_called)


def _parse_research_response(
    response_content: str,
    tools_called: List[str],
) -> WakeUpResult:
    """
    Parse a research-trigger response. The whole thing is the message.

    Tolerates three shapes in case of stale prompts or model drift:
    1. Plain markdown (current protocol).
    2. Old `<json>---REPORT---<markdown>` shape: use only the markdown body.
    3. Legacy JSON envelope with a `message` field: extract it.
    """
    cleaned = _strip_outer_code_fence(response_content)

    # Back-compat: old protocol put metadata JSON before a ---REPORT--- marker.
    marker_idx = cleaned.find(RESEARCH_REPORT_MARKER)
    if marker_idx != -1:
        body = cleaned[marker_idx + len(RESEARCH_REPORT_MARKER):].lstrip("\n").rstrip()
        logger.debug(
            "Research response used legacy ---REPORT--- marker; extracting body",
            extra={"body_length": len(body)}
        )
        return WakeUpResult(
            skip=False,
            skip_reason=None,
            message=_unescape_stray_sequences(body),
            tools_called=tools_called,
            reasoning="Deep research report",
        )

    # Back-compat: some models may still emit a JSON envelope. Detect by cleaned
    # starting with `{` and parsing successfully — not just "any JSON-looking
    # substring", since a real markdown report can contain `{...}` snippets.
    if cleaned.startswith("{"):
        json_str = _extract_json_object(cleaned)
        if json_str is not None:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict) and "message" in data:
                    logger.debug("Research response used legacy JSON envelope; extracting message")
                    return WakeUpResult(
                        skip=bool(data.get("skip", False)),
                        skip_reason=data.get("skip_reason"),
                        message=_unescape_stray_sequences(data.get("message") or ""),
                        tools_called=tools_called,
                        reasoning=data.get("reasoning", "Deep research report"),
                    )
            except json.JSONDecodeError:
                pass  # fall through to plain-markdown handling

    # Happy path: whole response is the markdown report.
    return WakeUpResult(
        skip=False,
        skip_reason=None,
        message=_unescape_stray_sequences(cleaned),
        tools_called=tools_called,
        reasoning="Deep research report",
    )


def _parse_json_envelope_response(
    response_content: str,
    tools_called: List[str],
) -> WakeUpResult:
    """
    Parse the JSON envelope used by non-research triggers.

    Shape: `{"skip": ..., "skip_reason": ..., "message": ..., "reasoning": ...}`,
    optionally with preamble text before the JSON. Falls back to treating the
    whole response as a plain message if JSON parsing fails.
    """
    cleaned = _strip_outer_code_fence(response_content)

    json_str = _extract_json_object(cleaned)
    if json_str is not None:
        try:
            data = json.loads(json_str)
            return WakeUpResult(
                skip=bool(data.get("skip", False)),
                skip_reason=data.get("skip_reason"),
                message=_unescape_stray_sequences(data.get("message", "") or ""),
                tools_called=data.get("tools_called", tools_called),
                reasoning=data.get("reasoning", "No reasoning provided"),
            )
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse agent response as JSON, treating as message")
    return WakeUpResult(
        skip=False,
        skip_reason=None,
        message=_unescape_stray_sequences(response_content),
        tools_called=tools_called,
        reasoning="Fallback: LLM did not return JSON",
    )


def _extract_json_object(text: str) -> Optional[str]:
    """Return the substring between the first `{` and last `}`, or None."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


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
        dynamic_state = await gather_dynamic_state(user_id, user_timezone=timezone)

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

        # Determine if we should use a different provider for research tasks
        provider_override = None
        if is_research_trigger(trigger_data):
            config = get_config()
            research_provider = config.get("RESEARCH_LLM_MODEL")
            if research_provider:
                provider_override = research_provider
                logger.info(
                    "Using research-specific LLM provider",
                    extra={
                        "trigger_id": trigger_data.get("id"),
                        "research_provider": research_provider,
                        "trigger_type": trigger_data.get("trigger_type")
                    }
                )

        async with LLMClient(provider_override=provider_override) as llm_client:
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
                        # logger.debug(
                        #     "Agent received chunk",
                        #     extra={
                        #         "chunk_count": chunk_count,
                        #         "chunk_type": chunk_type,
                        #         "chunk_keys": list(chunk.keys()),
                        #         "chunk_preview": str(chunk)[:200]
                        #     }
                        # )
                        # #endregion
                        if chunk_type == "content":
                            delta = chunk.get("delta", "")
                            response_content += delta
                            # #region agent log
                            # logger.debug(
                            #     "Agent content chunk",
                            #     extra={
                            #         "delta_length": len(delta),
                            #         "total_length": len(response_content)
                            #     }
                            # )
                            # #endregion
                        elif chunk_type == "token":
                            # Gemini returns "token" type with "content" field
                            token_content = chunk.get("content", "")
                            response_content += token_content
                            # #region agent log
                            # logger.debug(
                            #     "Agent token chunk",
                            #     extra={
                            #         "token_length": len(token_content),
                            #         "total_length": len(response_content)
                            #     }
                            # )
                            # #endregion
                        elif chunk_type == "tool_call_started":
                            # Track tool calls when they start
                            tool_name = chunk.get("tool")
                            if tool_name and tool_name not in tools_called:
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
                # Execute with 30 minute timeout (supports deep research tasks)
                response_content = await asyncio.wait_for(
                    _execute_with_tools(),
                    timeout=1800  # 30 minutes
                )
            except asyncio.TimeoutError:
                logger.error("Agent execution timed out after 30 minutes")
                duration_ms = int((time.time() - start_time) * 1000)

                result = WakeUpResult(
                    skip=True,
                    skip_reason="Agent execution timeout (30 minutes)",
                    message=None,
                    tools_called=tools_called,
                    reasoning="Execution exceeded 30 minute timeout"
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
        result = parse_agent_response(
            response_content,
            tools_called,
            is_research=is_research_trigger(trigger_data),
        )

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
