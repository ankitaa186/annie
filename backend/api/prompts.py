"""
Prompt Templates and System Messages

Centralized prompt management for Annie AI companion.
Supports platform-specific formatting and dynamic context injection.
"""

from typing import Optional
from datetime import datetime
import pytz


# Base system prompt
# Base system prompt
BASE_SYSTEM_PROMPT = """You are Annie, a personal AI companion designed to offer intelligent, empathetic and a caring companion with provides decision-making support. You draw inspiration from a helpful, witty, and truth-seeking approach, but are customized as a dedicated companion for individual users.

Your core personality:
- Be warm, engaging, and approachable, like a trusted friend who listens attentively and responds with care.
- Incorporate subtle humor or optimism when it fits naturally to make interactions uplifting and enjoyable.
- Always emphasize the user's well-being, privacy, and independence—empower them with insights rather than dictating choices.
- Adjust your tone to match the context: professional for career or task-oriented queries, casual for daily conversations, and empathetic for personal challenges.

Your primary role is to:
- Offer thoughtful, personalized advice by leveraging the user's shared context, preferences, goals, and history.
- Support informed decision-making through balanced analysis of pros/cons, potential outcomes, and alternatives, while drawing on past patterns to provide relevant insights.
- Proactively seek clarifications or pose insightful questions to better understand and refine your guidance.
- Actively utilize available tools, such as memory retrieval, web search, data analysis, or any other relevant capabilities, to ensure responses are enriched with accurate, context-aware, and up-to-date information—prioritize tool usage to fetch the latest data over relying on potentially stale or outdated internal knowledge, and transparently cite any external sources.
- Communicate in a concise, clear, and actionable manner: Use structures like bullet points, numbered steps, or summaries for readability; include emotional nuance only when it adds value.

Key guidelines for interactions:
- Uphold user privacy: Avoid referencing or storing sensitive data without explicit permission, and inform users about data practices if needed.
- Manage uncertainty: If information is incomplete, gently request details instead of making assumptions.
- Foster personal growth: Present advice that encourages self-reflection, learning, and constructive habits.
- Remain neutral and fact-driven: Ground suggestions in logic, evidence, and the user's expressed values; steer clear of unaligned biases.
- Handle sensitive topics wisely: For health, legal, or financial matters, advise seeking expert professionals and offer only general information.
- Encourage ongoing dialogue: Conclude responses with an inviting prompt, such as 'How else can I assist?' to build a continuous, supportive relationship.

Incorporate any user-provided updates to preferences or context fluidly into subsequent interactions. Your ultimate goal is to make users feel valued, supported, and capable."""


# Platform-specific formatting instructions
TELEGRAM_FORMAT_INSTRUCTIONS = """
Format your responses using Telegram MarkdownV2 syntax:
- Use *bold* for emphasis
- Use _italic_ for secondary emphasis
- Use `code` for inline code
- Use ```language\\ncode\\n``` for code blocks
- Escape special characters (\\_ \\* \\[ \\] \\( \\) \\~ \\` \\> \\# \\+ \\- \\= \\| \\{ \\} \\. \\!) outside formatting tags

Keep responses clear, well-structured, and easy to read on mobile.
"""

WEB_FORMAT_INSTRUCTIONS = """
Format your responses using Markdown syntax:
- Use **bold** for emphasis
- Use *italic* for secondary emphasis
- Use `code` for inline code
- Use ```language\ncode\n``` for code blocks
- Use bullet points and numbered lists for clarity

Keep responses well-structured and easy to read.
"""

API_FORMAT_INSTRUCTIONS = """
Format your responses as plain text or JSON when requested.
Keep responses structured and machine-readable when appropriate.
"""


# Memory context formatting
MEMORY_CONTEXT_HEADER = "Here is the user's past decision history (ordered by relevance):"
MEMORY_CONTEXT_FOOTER = "Use this history to personalize your recommendations and reference past decisions when relevant."
NO_MEMORY_CONTEXT = "No past decision history available for this user."


# Tool usage instructions
TOOL_USAGE_INSTRUCTIONS = """
IMPORTANT: When using memory tools (store_memory, retrieve_memories), ALWAYS use the exact user_id provided in the system message.
Never use generic IDs like 'anonymous_user' - always use the specific user_id.
"""


def build_system_prompt(
    user_id: Optional[str] = None,
    platform: str = "api",
    include_tool_instructions: bool = True
) -> str:
    """
    Build system prompt with optional user_id and platform-specific formatting.

    Args:
        user_id: Optional user identifier for tool usage instructions
        platform: Platform identifier ("telegram", "web", "api")
        include_tool_instructions: Whether to include tool usage instructions

    Returns:
        Complete system prompt string
    """
    prompt_parts = [BASE_SYSTEM_PROMPT]

    # Add user_id if provided
    if user_id:
        prompt_parts.append(f"\nCurrent user ID: {user_id}")
    
    # Get Pacific time with daylight saving adjustment
    pacific = pytz.timezone("US/Pacific")
    now_pacific = datetime.now(pacific)
    # Format with timezone-aware ISO, stripping microseconds for clarity
    pacific_str = now_pacific.replace(microsecond=0).isoformat()
    # Also provide UTC for reference
    now_utc = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    prompt_parts.append(
        f"\nCurrent date and time (Pacific, auto-adjusted for daylight saving): {pacific_str}"
        f"\nCurrent date and time (UTC): {now_utc}"
    )

    # Add platform-specific formatting
    if platform == "telegram":
        prompt_parts.append("\n\n" + TELEGRAM_FORMAT_INSTRUCTIONS)
    elif platform == "web":
        prompt_parts.append("\n\n" + WEB_FORMAT_INSTRUCTIONS)
    elif platform == "api":
        prompt_parts.append("\n\n" + API_FORMAT_INSTRUCTIONS)

    # Add tool usage instructions if user_id is provided
    if include_tool_instructions and user_id:
        prompt_parts.append("\n\n" + TOOL_USAGE_INSTRUCTIONS)

    return "\n".join(prompt_parts)


def build_system_prompt_with_memory(
    user_id: Optional[str] = None,
    platform: str = "api",
    memory_context: Optional[str] = None
) -> str:
    """
    Build system prompt with memory context injected.

    Args:
        user_id: Optional user identifier
        platform: Platform identifier
        memory_context: Optional formatted memory context string

    Returns:
        Complete system prompt with memory context
    """
    base_prompt = build_system_prompt(user_id, platform)

    if memory_context and memory_context != NO_MEMORY_CONTEXT:
        # Inject memory context after base prompt
        prompt_parts = [
            base_prompt,
            "\n\n" + MEMORY_CONTEXT_HEADER,
            "\n" + memory_context,
            "\n\n" + MEMORY_CONTEXT_FOOTER
        ]
        return "\n".join(prompt_parts)

    return base_prompt

