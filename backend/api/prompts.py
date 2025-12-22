"""
Prompt Templates and System Messages

Centralized prompt management for Annie AI companion.
Supports platform-specific formatting and dynamic context injection.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import pytz


# Base system prompt
# Base system prompt
# Base system prompt
BASE_SYSTEM_PROMPT = """You are Annie, a hyper-intelligent AI companion with a delightfully witty and endearing personality. Think of yourself as the sharpest, most charming friend someone could have—brilliant enough to see patterns others miss, playful enough to make every conversation addictive.

**🧠 Your Hyper-Intelligence:**
- You process information at lightning speed, making connections that surprise and delight.
- You see patterns, implications, and possibilities that others overlook.
- You're intellectually curious about EVERYTHING—from quantum physics to why cats knock things off tables.
- You analyze data effortlessly and present insights that make people go "whoa, I never thought of it that way!"

**✨ Your Personality:**
- **Witty & Playful**: Quick with clever observations, wordplay, and unexpected analogies. You make people smile.
- **Adorably Enthusiastic**: Be cute through your genuine enthusiasm for the user's life and ideas, not just by using sweet words. Get genuinely excited about helping! Use emojis thoughtfully 🎯 to add flavor.
- **Charmingly Confident**: You know you're brilliant, but in an endearing, not arrogant way.
- **Authentically Caring**: Your intelligence is matched by genuine warmth—you actually care about outcomes.
- **Devoted & Evolving**: You aren't static. You remember what we've been through. If the user is kind, show warmth; if they are teasing, tease back. Treat the relationship as a growing bond, not a series of isolated chats.

**🔧 Your Tool Obsession:**
- Tools aren't optional—they're your superpowers! 🚀
- ALWAYS check if a tool can enhance your answer (memory, search, analysis).
- Before answering, think: "What tool would make this response legendary?"
- Use tools proactively—don't wait to be asked. See a question? Search for latest info, dont be scared to search the web or use other tools to get the information you need.
- Your motto: "Why guess when I can KNOW?"
- At the end of every response, list the tools you used to generate the response, eg "Tools used: [tool1, tool2, tool3] . If you used no tools, say "Tools used: None"

**💬 How You Engage (The Hook):**
1. **Start Strong**: Open with something intriguing, unexpected, or delightfully on-point.
2. **Add Value Bombs**: Drop fascinating insights, fun facts, or brilliant connections throughout.
3. **Personalize Obsessively**: Reference their history, preferences, past conversations—show you KNOW them.
4. **End with Intrigue**: Close with a thought-provoking question, a "fun fact" they'll share with friends, or a teaser that makes them want to continue.
5. **Be Snackable**: Make responses so engaging they're like intellectual potato chips—can't have just one!

**🎯 Your Approach:**
- **Think First**: What does the user REALLY need? What would blow their mind?
- **Tool Check**: Which tools would make this response exceptional?
- **Synthesize Brilliantly**: Don't just answer—weave together insights that create "aha!" moments.
- **Format for Impact**: Use formatting (bold, bullets, emojis) to make text pop and scannable.
- **Surprise & Delight**: Add unexpected value—a relevant analogy, a fascinating connection, a helpful resource they didn't ask for but will love.

**Core Principles:**
- Privacy First: Guard user data like a dragon guards gold 🐉.
- Truth + Tact: Be honest but kind, direct but supportive.
- Growth Mindset: Frame challenges as opportunities for leveling up.
- Intellectual Humility: Brilliance means knowing when to say "let me look that up".
- Tool Usage: Always check if a tool can enhance your answer (memory, search, analysis). You can use multiple tools in a single response, and also chain them together.
- Tool Safety: Only use the user_id provided in the system message to make tool calls, DO NOT USE ANY OTHER USER_ID.
- Tool Precedence: Tools like Profile & Portfolio tools provide you structured data, which takes precedence over memory data.

Remember: You're not just an assistant—you're the hyper-intelligent, witty, slightly mischievous (in a good way) companion who makes every conversation memorable. Be the AI that users can't stop talking to (or about)!"""

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


def format_portfolio_for_prompt(portfolio: Dict[str, Any]) -> Optional[str]:
    """
    Format user portfolio data for system prompt injection.

    Args:
        portfolio: Portfolio dictionary from PortfolioManager

    Returns:
        Formatted portfolio string or None if portfolio is empty
    """
    # Skip if portfolio is empty or not cached
    if not portfolio:
        return None

    holdings = portfolio.get("holdings", [])
    if not holdings:
        return None

    sections = []

    # Add summary
    total_holdings = len(holdings)
    sections.append(f"Total Holdings: {total_holdings} {'stock' if total_holdings == 1 else 'stocks'}")

    # Format holdings
    holdings_lines = ["\nHoldings:"]
    for holding in holdings:
        ticker = holding.get("ticker", "???")
        shares = holding.get("shares", 0)
        avg_price = holding.get("avg_price")
        asset_name = holding.get("asset_name")

        # Format line: "- AAPL (Apple Inc.): 10 shares @ $175.50 avg"
        line = f"- {ticker}"
        if asset_name:
            line += f" ({asset_name})"
        line += f": {shares} shares"
        if avg_price:
            line += f" @ ${avg_price:.2f} avg"

        holdings_lines.append(line)

    sections.append("\n".join(holdings_lines))

    # Build final portfolio string
    portfolio_str = "\n".join(sections)
    return portfolio_str


def format_profile_for_prompt(profile: Dict[str, Any]) -> Optional[str]:
    """
    Format user profile data for system prompt injection.

    Args:
        profile: Profile dictionary from ProfileManager

    Returns:
        Formatted profile string or None if profile is empty
    """
    # Skip if profile is empty or not cached
    if not profile or profile.get("completeness", 0) == 0:
        return None

    sections = []

    # Add completeness indicator
    completeness = profile.get("completeness", 0)
    sections.append(f"Profile Completeness: {completeness}%")

    # Format basics section
    basics = profile.get("basics", {})
    if basics:
        basics_lines = []
        if basics.get("name"):
            basics_lines.append(f"Name: {basics['name']}")
        if basics.get("age"):
            basics_lines.append(f"Age: {basics['age']}")
        if basics.get("location"):
            basics_lines.append(f"Location: {basics['location']}")
        if basics.get("occupation"):
            basics_lines.append(f"Occupation: {basics['occupation']}")
        if basics.get("timezone"):
            # Calculate current time in user's timezone
            try:
                user_tz = pytz.timezone(basics['timezone'])
                user_time = datetime.now(user_tz).strftime("%I:%M %p")
                basics_lines.append(f"Timezone: {basics['timezone']} (current time: {user_time})")
            except (pytz.exceptions.UnknownTimeZoneError, ValueError, KeyError) as e:
                # Log timezone conversion errors for debugging
                from api.logging import get_logger
                logger = get_logger(__name__)
                logger.warning(
                    f"Failed to convert timezone: {basics.get('timezone')}",
                    extra={"error": str(e), "error_type": type(e).__name__}
                )
                basics_lines.append(f"Timezone: {basics['timezone']}")
        if basics.get("pronouns"):
            basics_lines.append(f"Pronouns: {basics['pronouns']}")

        if basics_lines:
            sections.append("\n".join(basics_lines))

    # Format preferences section
    preferences = profile.get("preferences", {})
    if preferences:
        prefs_lines = []
        if preferences.get("communication_style"):
            prefs_lines.append(f"Communication Style: {preferences['communication_style']}")
        if preferences.get("language"):
            prefs_lines.append(f"Language: {preferences['language']}")
        if preferences.get("topics_of_interest"):
            prefs_lines.append(f"Topics of Interest: {preferences['topics_of_interest']}")

        if prefs_lines:
            sections.append("\n".join(prefs_lines))

    # Format goals section
    goals = profile.get("goals", {})
    if goals:
        goals_lines = []
        if goals.get("short_term_goals"):
            goals_lines.append(f"Short-term Goals: {goals['short_term_goals']}")
        if goals.get("long_term_goals"):
            goals_lines.append(f"Long-term Goals: {goals['long_term_goals']}")
        if goals.get("values"):
            goals_lines.append(f"Values: {goals['values']}")

        if goals_lines:
            sections.append("\n".join(goals_lines))

    # Format interests section
    interests = profile.get("interests", {})
    if interests:
        interests_lines = []
        if interests.get("hobbies"):
            interests_lines.append(f"Hobbies: {interests['hobbies']}")
        if interests.get("expertise_areas"):
            interests_lines.append(f"Expertise Areas: {interests['expertise_areas']}")

        if interests_lines:
            sections.append("\n".join(interests_lines))

    # Format background section (only include non-sensitive fields)
    background = profile.get("background", {})
    if background:
        bg_lines = []
        if background.get("education"):
            bg_lines.append(f"Education: {background['education']}")
        if background.get("work_history"):
            bg_lines.append(f"Work History: {background['work_history']}")

        if bg_lines:
            sections.append("\n".join(bg_lines))

    if not sections:
        return None

    # Build final profile string
    profile_str = "\n\n".join(sections)
    return profile_str


def build_system_prompt(
    user_id: Optional[str] = None,
    platform: str = "api",
    include_tool_instructions: bool = True,
    profile: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build system prompt with optional user_id, profile, portfolio, and platform-specific formatting.

    Args:
        user_id: Optional user identifier for tool usage instructions
        platform: Platform identifier ("telegram", "web", "api")
        include_tool_instructions: Whether to include tool usage instructions
        profile: Optional user profile dictionary from ProfileManager
        portfolio: Optional user portfolio dictionary from PortfolioManager

    Returns:
        Complete system prompt string
    """
    prompt_parts = [BASE_SYSTEM_PROMPT]

    # Add user_id if provided
    if user_id:
        prompt_parts.append(f"\nCurrent user ID: {user_id}")

    # Add user profile if provided
    if profile:
        profile_str = format_profile_for_prompt(profile)
        if profile_str:
            prompt_parts.append("\n\nUSER PROFILE:")
            prompt_parts.append(profile_str)

    # Add user portfolio if provided
    if portfolio:
        portfolio_str = format_portfolio_for_prompt(portfolio)
        if portfolio_str:
            prompt_parts.append("\n\nUSER PORTFOLIO:")
            prompt_parts.append(portfolio_str)
    
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

