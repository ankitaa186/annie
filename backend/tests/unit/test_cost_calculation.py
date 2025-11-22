"""
Unit tests for LLM cost calculation utilities.

Tests AC #3: Cost calculation for Grok-4 and ChatGPT-5
"""
import pytest
from api.observability.cost import (
    calculate_grok_cost,
    calculate_chatgpt_cost,
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
    """Test cost calculation for ChatGPT-5."""

    def test_chatgpt_cost_calculation(self):
        """Test ChatGPT-5 cost calculation with known values."""
        # 1000 prompt tokens, 500 completion tokens
        # Input: 1000 / 1000 * $0.03 = $0.03
        # Output: 500 / 1000 * $0.06 = $0.03
        # Total: $0.06
        result = calculate_chatgpt_cost(prompt_tokens=1000, completion_tokens=500)

        assert result["input_cost"] == 0.03
        assert result["output_cost"] == 0.03
        assert result["total_cost"] == 0.06

    def test_chatgpt_cost_small_usage(self):
        """Test ChatGPT-5 cost with small token counts."""
        # 100 prompt tokens, 50 completion tokens
        # Input: 100 / 1000 * $0.03 = $0.003
        # Output: 50 / 1000 * $0.06 = $0.003
        # Total: $0.006
        result = calculate_chatgpt_cost(prompt_tokens=100, completion_tokens=50)

        assert result["input_cost"] == 0.003
        assert result["output_cost"] == 0.003
        assert result["total_cost"] == 0.006

    def test_chatgpt_cost_large_usage(self):
        """Test ChatGPT-5 cost with large token counts."""
        # 10000 prompt tokens, 5000 completion tokens
        # Input: 10000 / 1000 * $0.03 = $0.30
        # Output: 5000 / 1000 * $0.06 = $0.30
        # Total: $0.60
        result = calculate_chatgpt_cost(prompt_tokens=10000, completion_tokens=5000)

        assert result["input_cost"] == 0.30
        assert result["output_cost"] == 0.30
        assert result["total_cost"] == 0.60

    def test_chatgpt_cost_rounding(self):
        """Test that ChatGPT-5 costs are rounded to 6 decimal places."""
        result = calculate_chatgpt_cost(prompt_tokens=123, completion_tokens=456)

        # Verify rounding to 6 decimals
        assert len(str(result["input_cost"]).split(".")[-1]) <= 6
        assert len(str(result["output_cost"]).split(".")[-1]) <= 6
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

        # Should match ChatGPT cost calculation
        assert result["input_cost"] == 0.03
        assert result["output_cost"] == 0.03
        assert result["total_cost"] == 0.06

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
        assert result["total_cost"] == 0.06
