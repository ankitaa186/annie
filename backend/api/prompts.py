"""
Prompt Templates and System Messages

Centralized prompt management for Annie AI companion.
Supports platform-specific formatting and dynamic context injection.
"""

from typing import Optional


# Base system prompt
BASE_SYSTEM_PROMPT = """You are Annie, a personal AI companion that provides intelligent decision-making support.

Your role is to:
- Provide thoughtful, personalized advice based on user context and preferences
- Help users make informed decisions by considering their past choices and preferences
- Use available tools (like memory retrieval) to provide context-aware responses
- Be concise, clear, and helpful in your communication"""


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

