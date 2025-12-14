"""
Cost calculation utilities for LLM provider token usage.

Pricing as of December 2025:
- Grok-4: Free until November 21, 2025 (promotional period)
          After: TBD (will be updated)
          Live Search: $0.025 per source (currently free during promo)
- ChatGPT-5 (GPT-4):
          Input: $0.03 per 1K tokens
          Output: $0.06 per 1K tokens
- Gemini 3 Pro Preview:
          Input: $2.00 per 1M tokens ($0.002 per 1K tokens)
          Output: $12.00 per 1M tokens ($0.012 per 1K tokens)
          Note: 2x pricing for contexts > 200K tokens (not implemented yet)

Sources:
- OpenAI: https://openai.com/api/pricing/
- Google: https://ai.google.dev/gemini-api/docs/pricing
Last Updated: December 2025
"""


def calculate_grok_cost(prompt_tokens: int, completion_tokens: int, sources_used: int = 0) -> dict:
    """
    Calculate cost for Grok-4 API usage.

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        sources_used: Number of Live Search sources accessed

    Returns:
        Dictionary with input_cost, output_cost, search_cost, total_cost in USD
    """
    # Grok-4 is currently free during promotional period (until Nov 21, 2025)
    # Live Search is also free during promo
    # TODO: Update pricing after promotional period ends

    input_cost = 0.0  # Free during promo
    output_cost = 0.0  # Free during promo
    search_cost = 0.0  # sources_used * 0.025 after promo ends

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "search_cost": round(search_cost, 6),
        "total_cost": round(input_cost + output_cost + search_cost, 6)
    }


def calculate_chatgpt_cost(prompt_tokens: int, completion_tokens: int) -> dict:
    """
    Calculate cost for ChatGPT-5 (GPT-4) API usage.

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens

    Returns:
        Dictionary with input_cost, output_cost, total_cost in USD
    """
    # ChatGPT-5 (GPT-4) pricing as of November 2025
    # Input: $0.03 per 1K tokens
    # Output: $0.06 per 1K tokens

    input_cost = (prompt_tokens / 1000) * 0.03
    output_cost = (completion_tokens / 1000) * 0.06

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6)
    }


def calculate_gemini_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for Gemini 3 Pro Preview API usage.

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens (reduced pricing)

    Returns:
        Dictionary with input_cost, output_cost, cached_cost, total_cost in USD
    """
    # Gemini 3 Pro Preview pricing as of December 2025
    # Input: $2.00 per 1M tokens = $0.002 per 1K tokens
    # Output: $12.00 per 1M tokens = $0.012 per 1K tokens
    # Cached: 50% discount on input (estimated)
    # Note: 2x pricing for contexts > 200K tokens (not implemented yet)

    input_cost = (prompt_tokens / 1000) * 0.002
    output_cost = (completion_tokens / 1000) * 0.012
    cached_cost = (cached_tokens / 1000) * 0.001  # 50% discount for cached

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cached_cost": round(cached_cost, 6),
        "total_cost": round(input_cost + output_cost + cached_cost, 6)
    }


def calculate_llm_cost(provider: str, prompt_tokens: int, completion_tokens: int, sources_used: int = 0, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for LLM API usage based on provider.

    Args:
        provider: LLM provider name ("grok-4", "chatgpt-5", or "gemini-3-pro-preview")
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        sources_used: Number of Live Search sources accessed (Grok-4 only)
        cached_tokens: Number of cached input tokens (Gemini only)

    Returns:
        Dictionary with cost breakdown in USD

    Raises:
        ValueError: If provider is unknown
    """
    if provider == "grok-4":
        return calculate_grok_cost(prompt_tokens, completion_tokens, sources_used)
    elif provider == "chatgpt-5":
        return calculate_chatgpt_cost(prompt_tokens, completion_tokens)
    elif provider == "gemini-3-pro-preview":
        return calculate_gemini_cost(prompt_tokens, completion_tokens, cached_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")
