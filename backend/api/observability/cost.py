"""
Cost calculation utilities for LLM provider token usage.

Pricing as of March 2026:
- Grok-4: Free until November 21, 2025 (promotional period)
          After: TBD (will be updated)
          Live Search: $0.025 per source (currently free during promo)
- ChatGPT-5 (GPT-5.4):
          Input: $2.50 per 1M tokens
          Output: $15.00 per 1M tokens
          Cached Input: $0.25 per 1M tokens (90% discount)
- Gemini 3.1 Pro Preview:
          Input: $2.00 per 1M tokens
          Output: $12.00 per 1M tokens
          Cached Input: $0.20 per 1M tokens
          Note: 2x pricing for contexts > 200K tokens ($4/$18/$0.40 per 1M)
- Gemini 3 Flash Preview:
          Input: $0.50 per 1M tokens
          Output: $3.00 per 1M tokens
          Note: 6x cheaper than Pro on input, 4x cheaper on output

Sources:
- OpenAI: https://openai.com/api/pricing/
- Google: https://ai.google.dev/gemini-api/docs/pricing
Last Updated: March 2026
"""

from api.constants import (
    MODEL_GROK_4, MODEL_GPT_5,
    MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH, MODEL_GEMINI_LEGACY,
)


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


def calculate_chatgpt_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for ChatGPT-5 (GPT-5.4) API usage.

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens (90% discount)

    Returns:
        Dictionary with input_cost, output_cost, cached_cost, total_cost in USD
    """
    # GPT-5.4 pricing as of March 2026
    # Input: $2.50 per 1M tokens
    # Output: $15.00 per 1M tokens
    # Cached Input: $0.25 per 1M tokens (90% discount)
    INPUT_COST = 2.50    # $2.50 per 1M tokens
    OUTPUT_COST = 15.00  # $15.00 per 1M tokens
    CACHED_COST = 0.25   # $0.25 per 1M tokens

    input_cost = (prompt_tokens / 1_000_000) * INPUT_COST
    output_cost = (completion_tokens / 1_000_000) * OUTPUT_COST
    cached_cost = (cached_tokens / 1_000_000) * CACHED_COST

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cached_cost": round(cached_cost, 6),
        "total_cost": round(input_cost + output_cost + cached_cost, 6)
    }


def calculate_gemini_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for Gemini 3 Pro Preview API usage with tiered pricing.

    Tiered pricing (as of December 2025):
    - Input tokens ≤200k: $2.00 per 1M tokens
    - Input tokens >200k: $4.00 per 1M tokens (for excess)
    - Output tokens ≤200k: $12.00 per 1M tokens
    - Output tokens >200k: $18.00 per 1M tokens (for excess)
    - Cached tokens ≤200k: $0.20 per 1M tokens
    - Cached tokens >200k: $0.40 per 1M tokens (for excess)

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens (reduced pricing)

    Returns:
        Dictionary with input_cost, output_cost, cached_cost, total_cost, tier in USD
    """
    # Tiered pricing threshold
    TIER_THRESHOLD = 200_000  # 200k tokens

    # Pricing per 1M tokens
    INPUT_COST_LOW = 2.00      # $2.00 per 1M tokens (≤200k)
    INPUT_COST_HIGH = 4.00     # $4.00 per 1M tokens (>200k)
    OUTPUT_COST_LOW = 12.00    # $12.00 per 1M tokens (≤200k)
    OUTPUT_COST_HIGH = 18.00   # $18.00 per 1M tokens (>200k)
    CACHED_COST_LOW = 0.20     # $0.20 per 1M tokens (≤200k)
    CACHED_COST_HIGH = 0.40    # $0.40 per 1M tokens (>200k)

    # Calculate input cost (tiered)
    if prompt_tokens <= TIER_THRESHOLD:
        input_cost = (prompt_tokens / 1_000_000) * INPUT_COST_LOW
    else:
        low_tier = (TIER_THRESHOLD / 1_000_000) * INPUT_COST_LOW
        high_tier = ((prompt_tokens - TIER_THRESHOLD) / 1_000_000) * INPUT_COST_HIGH
        input_cost = low_tier + high_tier

    # Calculate output cost (tiered)
    if completion_tokens <= TIER_THRESHOLD:
        output_cost = (completion_tokens / 1_000_000) * OUTPUT_COST_LOW
    else:
        low_tier = (TIER_THRESHOLD / 1_000_000) * OUTPUT_COST_LOW
        high_tier = ((completion_tokens - TIER_THRESHOLD) / 1_000_000) * OUTPUT_COST_HIGH
        output_cost = low_tier + high_tier

    # Calculate cached cost (tiered)
    if cached_tokens <= TIER_THRESHOLD:
        cached_cost = (cached_tokens / 1_000_000) * CACHED_COST_LOW
    else:
        low_tier = (TIER_THRESHOLD / 1_000_000) * CACHED_COST_LOW
        high_tier = ((cached_tokens - TIER_THRESHOLD) / 1_000_000) * CACHED_COST_HIGH
        cached_cost = low_tier + high_tier

    # Determine tier for metadata
    total_tokens = prompt_tokens + completion_tokens + cached_tokens
    tier = "low" if total_tokens <= TIER_THRESHOLD else "high"

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cached_cost": round(cached_cost, 6),
        "total_cost": round(input_cost + output_cost + cached_cost, 6),
        "tier": tier
    }


def calculate_gemini_flash_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for Gemini 3 Flash Preview API usage.

    Pricing (as of December 2025):
    - Input: $0.50 per 1M tokens
    - Output: $3.00 per 1M tokens
    - Cached: $0.125 per 1M tokens (1/4 of input cost)

    Args:
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cached_tokens: Number of cached input tokens (reduced pricing)

    Returns:
        Dictionary with input_cost, output_cost, cached_cost, total_cost in USD
    """
    # Gemini 3 Flash Preview pricing per 1M tokens
    INPUT_COST = 0.50      # $0.50 per 1M tokens
    OUTPUT_COST = 3.00     # $3.00 per 1M tokens
    CACHED_COST = 0.125    # $0.125 per 1M tokens (1/4 of input)

    input_cost = (prompt_tokens / 1_000_000) * INPUT_COST
    output_cost = (completion_tokens / 1_000_000) * OUTPUT_COST
    cached_cost = (cached_tokens / 1_000_000) * CACHED_COST

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "cached_cost": round(cached_cost, 6),
        "total_cost": round(input_cost + output_cost + cached_cost, 6),
        "tier": "flash"
    }


def calculate_llm_cost(provider: str, prompt_tokens: int, completion_tokens: int, sources_used: int = 0, cached_tokens: int = 0) -> dict:
    """
    Calculate cost for LLM API usage based on provider.

    Args:
        provider: LLM provider name ("grok-4", "chatgpt-5", "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro")
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        sources_used: Number of Live Search sources accessed (Grok-4 only)
        cached_tokens: Number of cached input tokens (Gemini only)

    Returns:
        Dictionary with cost breakdown in USD

    Raises:
        ValueError: If provider is unknown
    """
    if provider == MODEL_GROK_4:
        return calculate_grok_cost(prompt_tokens, completion_tokens, sources_used)
    elif provider == MODEL_GPT_5:
        return calculate_chatgpt_cost(prompt_tokens, completion_tokens, cached_tokens)
    elif provider == MODEL_GEMINI_FLASH:
        # Gemini 3 Flash has different (cheaper) pricing than Pro
        return calculate_gemini_flash_cost(prompt_tokens, completion_tokens, cached_tokens)
    elif provider in (MODEL_GEMINI_PRO, MODEL_GEMINI_LEGACY):
        # Pro models use tiered pricing
        return calculate_gemini_cost(prompt_tokens, completion_tokens, cached_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")
