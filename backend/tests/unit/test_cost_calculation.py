"""
Unit tests for LLM cost calculation utilities.

Tests AC #3: Cost calculation for Grok-4, ChatGPT-5, and Gemini 3 Pro
"""
import pytest
from api.observability.cost import (
    calculate_grok_cost,
    calculate_chatgpt_cost,
    calculate_gemini_cost,
    calculate_llm_cost
)


class TestGrokCostCalculation:
    """Test cost calculation for Grok-4."""

    def test_grok_cost_during_promo_period(self):
        """Test that Grok-4 is free during promotional period."""
        result = calculate_grok_cost(prompt_tokens=1000, completion_tokens=500, sources_used=5)

        # During promo (until Nov 21, 2025), everything is free
        assert result["input_cost"] == 0.0
        assert result["output_cost"] == 0.0
        assert result["search_cost"] == 0.0
        assert result["total_cost"] == 0.0

    def test_grok_cost_with_no_search(self):
        """Test Grok-4 cost with no Live Search usage."""
        result = calculate_grok_cost(prompt_tokens=2000, completion_tokens=1000, sources_used=0)

        # All costs should be 0 during promo
        assert result["input_cost"] == 0.0
        assert result["output_cost"] == 0.0
        assert result["search_cost"] == 0.0
        assert result["total_cost"] == 0.0

    def test_grok_cost_structure(self):
        """Test that Grok cost result has correct structure."""
        result = calculate_grok_cost(prompt_tokens=100, completion_tokens=50)

        # Verify structure
        assert "input_cost" in result
        assert "output_cost" in result
        assert "search_cost" in result
        assert "total_cost" in result
        assert all(isinstance(v, float) for v in result.values())


class TestChatGPTCostCalculation:
    """Test cost calculation for ChatGPT-5 (GPT-5.2)."""

    def test_chatgpt_cost_calculation(self):
        """Test ChatGPT-5 cost calculation with known values."""
        # 1000 prompt tokens, 500 completion tokens
        # GPT-5.2 pricing: $1.75/1M input, $14.00/1M output
        # Input: 1000 / 1,000,000 * $1.75 = $0.00175
        # Output: 500 / 1,000,000 * $14.00 = $0.007
        # Total: $0.00875
        result = calculate_chatgpt_cost(prompt_tokens=1000, completion_tokens=500)

        assert result["input_cost"] == 0.00175
        assert result["output_cost"] == 0.007
        assert result["total_cost"] == 0.00875

    def test_chatgpt_cost_small_usage(self):
        """Test ChatGPT-5 cost with small token counts."""
        # 100 prompt tokens, 50 completion tokens
        # Input: 100 / 1,000,000 * $1.75 = $0.000175
        # Output: 50 / 1,000,000 * $14.00 = $0.0007
        # Total: $0.000875
        result = calculate_chatgpt_cost(prompt_tokens=100, completion_tokens=50)

        assert result["input_cost"] == 0.000175
        assert result["output_cost"] == 0.0007
        assert result["total_cost"] == 0.000875

    def test_chatgpt_cost_large_usage(self):
        """Test ChatGPT-5 cost with large token counts."""
        # 10000 prompt tokens, 5000 completion tokens
        # Input: 10000 / 1,000,000 * $1.75 = $0.0175
        # Output: 5000 / 1,000,000 * $14.00 = $0.07
        # Total: $0.0875
        result = calculate_chatgpt_cost(prompt_tokens=10000, completion_tokens=5000)

        assert result["input_cost"] == 0.0175
        assert result["output_cost"] == 0.07
        assert result["total_cost"] == 0.0875

    def test_chatgpt_cost_rounding(self):
        """Test that ChatGPT-5 costs are rounded to 6 decimal places."""
        result = calculate_chatgpt_cost(prompt_tokens=123, completion_tokens=456)

        # Verify rounding to 6 decimals
        assert len(str(result["input_cost"]).split(".")[-1]) <= 6
        assert len(str(result["output_cost"]).split(".")[-1]) <= 6
        assert len(str(result["total_cost"]).split(".")[-1]) <= 6


class TestGeminiCostCalculation:
    """Test cost calculation for Gemini 3 Pro Preview."""

    def test_gemini_cost_calculation(self):
        """Test Gemini 3 Pro cost calculation with known values."""
        # 1000 prompt tokens, 500 completion tokens
        # Input: 1000 / 1000 * $0.002 = $0.002
        # Output: 500 / 1000 * $0.012 = $0.006
        # Total: $0.008
        result = calculate_gemini_cost(prompt_tokens=1000, completion_tokens=500)

        assert result["input_cost"] == 0.002
        assert result["output_cost"] == 0.006
        assert result["cached_cost"] == 0.0
        assert result["total_cost"] == 0.008

    def test_gemini_cost_with_cached_tokens(self):
        """Test Gemini 3 Pro cost with cached tokens."""
        # 1000 prompt tokens, 500 completion tokens, 200 cached tokens
        # Input: 1000 / 1M * $2.00 = $0.002
        # Output: 500 / 1M * $12.00 = $0.006
        # Cached: 200 / 1M * $0.20 = $0.00004
        # Total: $0.00804
        result = calculate_gemini_cost(prompt_tokens=1000, completion_tokens=500, cached_tokens=200)

        assert result["input_cost"] == 0.002
        assert result["output_cost"] == 0.006
        assert result["cached_cost"] == 0.00004
        assert result["total_cost"] == 0.00804

    def test_gemini_cost_small_usage(self):
        """Test Gemini 3 Pro cost with small token counts."""
        # 100 prompt tokens, 50 completion tokens
        # Input: 100 / 1000 * $0.002 = $0.0002
        # Output: 50 / 1000 * $0.012 = $0.0006
        # Total: $0.0008
        result = calculate_gemini_cost(prompt_tokens=100, completion_tokens=50)

        assert result["input_cost"] == 0.0002
        assert result["output_cost"] == 0.0006
        assert result["total_cost"] == 0.0008

    def test_gemini_cost_large_usage(self):
        """Test Gemini 3 Pro cost with large token counts (1M tokens) - tiered pricing."""
        # 1,000,000 prompt tokens, 100,000 completion tokens
        # Input: First 200k at $2/1M + remaining 800k at $4/1M
        #   = (200k/1M * 2) + (800k/1M * 4) = 0.4 + 3.2 = $3.60
        # Output: 100k at $12/1M = $1.20 (under 200k threshold)
        # Total: $4.80
        result = calculate_gemini_cost(prompt_tokens=1000000, completion_tokens=100000)

        assert result["input_cost"] == 3.6
        assert result["output_cost"] == 1.2
        assert result["total_cost"] == 4.8
        assert result["tier"] == "high"  # Over 200k threshold

    def test_gemini_cost_structure(self):
        """Test that Gemini cost result has correct structure."""
        result = calculate_gemini_cost(prompt_tokens=100, completion_tokens=50)

        # Verify structure includes cached_cost and tier
        assert "input_cost" in result
        assert "output_cost" in result
        assert "cached_cost" in result
        assert "total_cost" in result
        assert "tier" in result
        # Verify cost values are floats
        assert isinstance(result["input_cost"], float)
        assert isinstance(result["output_cost"], float)
        assert isinstance(result["cached_cost"], float)
        assert isinstance(result["total_cost"], float)
        # Tier is a string
        assert isinstance(result["tier"], str)
        assert result["tier"] in ["low", "high"]

    def test_gemini_cost_rounding(self):
        """Test that Gemini costs are rounded to 6 decimal places."""
        result = calculate_gemini_cost(prompt_tokens=123, completion_tokens=456, cached_tokens=78)

        # Verify rounding to 6 decimals
        assert len(str(result["input_cost"]).split(".")[-1]) <= 6
        assert len(str(result["output_cost"]).split(".")[-1]) <= 6
        assert len(str(result["cached_cost"]).split(".")[-1]) <= 6
        assert len(str(result["total_cost"]).split(".")[-1]) <= 6


class TestUnifiedCostCalculation:
    """Test unified cost calculation function."""

    def test_calculate_llm_cost_grok(self):
        """Test unified function with Grok-4 provider."""
        result = calculate_llm_cost("grok-4", prompt_tokens=1000, completion_tokens=500, sources_used=3)

        # Should match Grok cost calculation
        assert result["input_cost"] == 0.0  # Promo period
        assert result["total_cost"] == 0.0

    def test_calculate_llm_cost_chatgpt(self):
        """Test unified function with ChatGPT-5 provider."""
        result = calculate_llm_cost("chatgpt-5", prompt_tokens=1000, completion_tokens=500)

        # Should match ChatGPT cost calculation (GPT-5.2 pricing)
        assert result["input_cost"] == 0.00175
        assert result["output_cost"] == 0.007
        assert result["total_cost"] == 0.00875

    def test_calculate_llm_cost_gemini(self):
        """Test unified function with Gemini 3 Pro Preview provider."""
        result = calculate_llm_cost("gemini-3.1-pro-preview", prompt_tokens=1000, completion_tokens=500)

        # Should match Gemini cost calculation
        assert result["input_cost"] == 0.002
        assert result["output_cost"] == 0.006
        assert result["total_cost"] == 0.008

    def test_calculate_llm_cost_gemini_with_cached(self):
        """Test unified function with Gemini 3 Pro and cached tokens."""
        result = calculate_llm_cost(
            "gemini-3.1-pro-preview",
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=200
        )

        # Should include cached token cost
        # Cached: 200 / 1M * $0.20 = $0.00004
        assert result["input_cost"] == 0.002
        assert result["output_cost"] == 0.006
        assert result["cached_cost"] == 0.00004
        assert result["total_cost"] == 0.00804

    def test_calculate_llm_cost_unknown_provider(self):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            calculate_llm_cost("unknown-provider", prompt_tokens=100, completion_tokens=50)

    def test_calculate_llm_cost_no_search_for_chatgpt(self):
        """Test that sources_used is ignored for ChatGPT-5."""
        # ChatGPT doesn't have Live Search, so sources_used should be ignored
        result = calculate_llm_cost("chatgpt-5", prompt_tokens=1000, completion_tokens=500, sources_used=10)

        # Result should not include search_cost
        assert "search_cost" not in result
        assert result["total_cost"] == 0.00875  # GPT-5.2 pricing
