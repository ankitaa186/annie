"""
Cost calculation utilities for LLM provider token usage.

Pricing as of November 2025:
- Grok-4: Free until November 21, 2025 (promotional period)
          After: TBD (will be updated)
          Live Search: $0.025 per source (currently free during promo)
- ChatGPT-5 (GPT-4):
          Input: $0.03 per 1K tokens
          Output: $0.06 per 1K tokens

Source: https://openai.com/api/pricing/
Last Updated: November 2025
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


def calculate_llm_cost(provider: str, prompt_tokens: int, completion_tokens: int, sources_used: int = 0) -> dict:
    """
    Calculate cost for LLM API usage based on provider.

    Args:
        provider: LLM provider name ("grok-4" or "chatgpt-5")
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        sources_used: Number of Live Search sources accessed (Grok-4 only)

    Returns:
        Dictionary with cost breakdown in USD

    Raises:
        ValueError: If provider is unknown
    """
    if provider == "grok-4":
        return calculate_grok_cost(prompt_tokens, completion_tokens, sources_used)
    elif provider == "chatgpt-5":
        return calculate_chatgpt_cost(prompt_tokens, completion_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")
