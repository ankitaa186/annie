"""
Unit tests for status summarizers (Story 11.4).

Tests all tool result summarizers to ensure they produce concise, user-friendly
status messages for real-time updates during tool execution.

Coverage:
- All 11 MCP tools (portfolio, stock, profile, memory, search, health)
- Success result formatting
- Error result handling
- Edge cases (missing fields, null values, empty results)
- Generic fallback behavior
"""
import pytest


class TestPortfolioSummarizers:
    """Test portfolio tool result summarizers."""

    def test_get_portfolio_with_prices(self):
        """Test get_portfolio summarizer with price data."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "success",
            "holdings": [{"ticker": "AAPL"}, {"ticker": "GOOGL"}, {"ticker": "MSFT"}],
            "total_holdings": 3,
            "total_value": 15420.50,
            "total_gain_loss_pct": 12.5
        }

        summary = summarize_portfolio_result(result)
        assert summary == "3 holdings, $15,420 value"

    def test_get_portfolio_without_prices(self):
        """Test get_portfolio summarizer without price data (fast query)."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "success",
            "holdings": [{"ticker": "AAPL"}, {"ticker": "GOOGL"}],
            "total_holdings": 2
        }

        summary = summarize_portfolio_result(result)
        assert summary == "2 holdings"

    def test_get_portfolio_empty(self):
        """Test get_portfolio summarizer with no holdings."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "success",
            "holdings": [],
            "total_holdings": 0
        }

        summary = summarize_portfolio_result(result)
        assert summary == "0 holdings"

    def test_get_portfolio_error(self):
        """Test get_portfolio summarizer with error result."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "error",
            "message": "Portfolio service unavailable. Please try again later."
        }

        summary = summarize_portfolio_result(result)
        # Messages under 500 chars are not truncated
        assert summary == "Portfolio service unavailable. Please try again later."
        assert len(summary) <= 500

    def test_add_holding_created(self):
        """Test add_holding summarizer for newly created holding."""
        from api.status_summarizers import summarize_add_holding_result

        result = {
            "status": "success",
            "holding": {"ticker": "AAPL", "shares": 10},
            "created": True,
            "message": "Added AAPL in your portfolio."
        }

        summary = summarize_add_holding_result(result)
        assert summary == "Added AAPL: 10 shares"

    def test_add_holding_updated(self):
        """Test add_holding summarizer for updated existing holding."""
        from api.status_summarizers import summarize_add_holding_result

        result = {
            "status": "success",
            "holding": {"ticker": "AAPL", "shares": 20},
            "created": False,
            "message": "Updated AAPL in your portfolio."
        }

        summary = summarize_add_holding_result(result)
        assert summary == "Updated AAPL: 20 shares"

    def test_update_holding(self):
        """Test update_holding summarizer."""
        from api.status_summarizers import summarize_update_holding_result

        result = {
            "status": "success",
            "ticker": "GOOGL",
            "shares": 15,
            "message": "Updated GOOGL in your portfolio."
        }

        summary = summarize_update_holding_result(result)
        assert summary == "Updated GOOGL"

    def test_remove_holding(self):
        """Test remove_holding summarizer."""
        from api.status_summarizers import summarize_remove_holding_result

        result = {
            "status": "success",
            "deleted": True,
            "ticker": "MSFT",
            "message": "Removed MSFT from your portfolio."
        }

        summary = summarize_remove_holding_result(result)
        assert summary == "Removed MSFT"

    def test_clear_portfolio(self):
        """Test clear_portfolio summarizer."""
        from api.status_summarizers import summarize_clear_portfolio_result

        result = {
            "status": "success",
            "deleted": True,
            "holdings_removed": 5,
            "message": "Cleared your entire portfolio. 5 holdings removed."
        }

        summary = summarize_clear_portfolio_result(result)
        assert summary == "Portfolio cleared (5 removed)"


class TestStockSummarizers:
    """Test stock analysis tool result summarizers."""

    def test_analyze_stock_positive_change(self):
        """Test analyze_stock summarizer with positive price change."""
        from api.status_summarizers import summarize_analyze_stock_result

        result = {
            "status": "success",
            "ticker": "AAPL",
            "current_price": 175.50,
            "change_1d_pct": 2.3,
            "name": "Apple Inc."
        }

        summary = summarize_analyze_stock_result(result)
        assert summary == "AAPL $175.50 (+2.3%)"

    def test_analyze_stock_negative_change(self):
        """Test analyze_stock summarizer with negative price change."""
        from api.status_summarizers import summarize_analyze_stock_result

        result = {
            "status": "success",
            "ticker": "GOOGL",
            "current_price": 142.25,
            "change_1d_pct": -1.5,
            "name": "Alphabet Inc."
        }

        summary = summarize_analyze_stock_result(result)
        assert summary == "GOOGL $142.25 (-1.5%)"

    def test_analyze_stock_zero_change(self):
        """Test analyze_stock summarizer with zero price change."""
        from api.status_summarizers import summarize_analyze_stock_result

        result = {
            "status": "success",
            "ticker": "MSFT",
            "current_price": 380.00,
            "change_1d_pct": 0.0,
            "name": "Microsoft Corporation"
        }

        summary = summarize_analyze_stock_result(result)
        assert summary == "MSFT $380.00 (+0.0%)"

    def test_get_stock_history(self):
        """Test get_stock_history summarizer."""
        from api.status_summarizers import summarize_stock_history_result

        result = {
            "status": "success",
            "ticker": "AAPL",
            "period": "1mo",
            "data_points": 22
        }

        summary = summarize_stock_history_result(result)
        assert summary == "History loaded: 1mo (22 days)"

    def test_analyze_stock_error(self):
        """Test analyze_stock summarizer with error result."""
        from api.status_summarizers import summarize_analyze_stock_result

        result = {
            "status": "error",
            "message": "Invalid ticker format: 'xyz'. Ticker must be uppercase."
        }

        summary = summarize_analyze_stock_result(result)
        # Messages under 500 chars are not truncated
        assert summary == "Invalid ticker format: 'xyz'. Ticker must be uppercase."
        assert len(summary) <= 500


class TestProfileSummarizer:
    """Test profile tool result summarizer."""

    def test_get_user_profile(self):
        """Test get_user_profile summarizer."""
        from api.status_summarizers import summarize_profile_result

        result = {
            "status": "success",
            "user_id": "123456",
            "completeness": 67
        }

        summary = summarize_profile_result(result)
        assert summary == "Profile loaded (67% complete)"

    def test_get_user_profile_complete(self):
        """Test get_user_profile summarizer with 100% complete profile."""
        from api.status_summarizers import summarize_profile_result

        result = {
            "status": "success",
            "user_id": "123456",
            "completeness": 100
        }

        summary = summarize_profile_result(result)
        assert summary == "Profile loaded (100% complete)"

    def test_get_user_profile_empty(self):
        """Test get_user_profile summarizer with 0% complete profile."""
        from api.status_summarizers import summarize_profile_result

        result = {
            "status": "success",
            "user_id": "123456",
            "completeness": 0
        }

        summary = summarize_profile_result(result)
        assert summary == "Profile loaded (0% complete)"

    def test_get_user_profile_error(self):
        """Test get_user_profile summarizer with error result."""
        from api.status_summarizers import summarize_profile_result

        result = {
            "status": "error",
            "error": "Profile not found for user 123456"
        }

        summary = summarize_profile_result(result)
        assert summary == "Profile not found for user 123456"


class TestMemorySummarizers:
    """Test memory tool result summarizers."""

    def test_store_memory_single(self):
        """Test store_memory summarizer with single memory (legacy format)."""
        from api.status_summarizers import summarize_store_memory_result

        result = {
            "status": "success",
            "memories_created": 1,
            "memory_ids": ["mem_abc"]
        }

        summary = summarize_store_memory_result(result)
        assert summary == "Memory saved"

    def test_store_memory_multiple(self):
        """Test store_memory summarizer with multiple memories (legacy format)."""
        from api.status_summarizers import summarize_store_memory_result

        result = {
            "status": "success",
            "memories_created": 3,
            "memory_ids": ["mem_abc", "mem_def", "mem_ghi"]
        }

        summary = summarize_store_memory_result(result)
        assert summary == "Memory saved (3 items)"

    def test_store_memory_new_format_with_memory_id(self):
        """Test store_memory summarizer with new Story 14.5 format."""
        from api.status_summarizers import summarize_store_memory_result

        result = {
            "status": "success",
            "memory_id": "abc123def456ghi789",
            "message": "Memory stored successfully",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": False,
                "procedural": False
            }
        }

        summary = summarize_store_memory_result(result)
        # Should show truncated memory_id (first 12 chars)
        assert summary == "Memory saved (abc123def456...)"

    def test_store_memory_new_format_short_id(self):
        """Test store_memory summarizer with short memory_id."""
        from api.status_summarizers import summarize_store_memory_result

        result = {
            "status": "success",
            "memory_id": "short123",
            "message": "Memory stored successfully",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": False,
                "procedural": False
            }
        }

        summary = summarize_store_memory_result(result)
        assert summary == "Memory saved (short123...)"

    def test_retrieve_memories_multiple(self):
        """Test retrieve_memories summarizer with multiple memories found."""
        from api.status_summarizers import summarize_retrieve_memories_result

        result = {
            "status": "success",
            "memory_count": 5,
            "memories": [{}, {}, {}, {}, {}]
        }

        summary = summarize_retrieve_memories_result(result)
        assert summary == "Found 5 memories"

    def test_retrieve_memories_single(self):
        """Test retrieve_memories summarizer with single memory found."""
        from api.status_summarizers import summarize_retrieve_memories_result

        result = {
            "status": "success",
            "memory_count": 1,
            "memories": [{}]
        }

        summary = summarize_retrieve_memories_result(result)
        assert summary == "Found 1 memory"

    def test_retrieve_memories_empty(self):
        """Test retrieve_memories summarizer with no memories found."""
        from api.status_summarizers import summarize_retrieve_memories_result

        result = {
            "status": "success",
            "memory_count": 0,
            "memories": []
        }

        summary = summarize_retrieve_memories_result(result)
        assert summary == "No memories found"

    def test_store_memory_error(self):
        """Test store_memory summarizer with error result."""
        from api.status_summarizers import summarize_store_memory_result

        result = {
            "status": "error",
            "message": "Failed to store memory: Network error"
        }

        summary = summarize_store_memory_result(result)
        assert summary == "Failed to store memory: Network error"


class TestDeleteMemorySummarizer:
    """Test delete_memory tool result summarizer (Story 14.5)."""

    def test_delete_memory_success(self):
        """Test delete_memory summarizer with successful deletion."""
        from api.status_summarizers import summarize_delete_memory_result

        result = {
            "status": "success",
            "deleted": True,
            "memory_id": "xyz123",
            "message": "Memory deleted successfully",
            "storage": {
                "chromadb": True,
                "episodic": False,
                "emotional": False,
                "procedural": False
            }
        }

        summary = summarize_delete_memory_result(result)
        assert summary == "Memory deleted"

    def test_delete_memory_not_found(self):
        """Test delete_memory summarizer when memory not found."""
        from api.status_summarizers import summarize_delete_memory_result

        result = {
            "status": "error",
            "deleted": False,
            "memory_id": "xyz123",
            "message": "Memory not found"
        }

        summary = summarize_delete_memory_result(result)
        assert summary == "Delete failed: Memory not found"

    def test_delete_memory_unauthorized(self):
        """Test delete_memory summarizer when unauthorized."""
        from api.status_summarizers import summarize_delete_memory_result

        result = {
            "status": "error",
            "deleted": False,
            "memory_id": "xyz123",
            "message": "Unauthorized"
        }

        summary = summarize_delete_memory_result(result)
        assert summary == "Delete failed: Unauthorized"

    def test_delete_memory_deleted_false(self):
        """Test delete_memory summarizer when deleted is false but status is success."""
        from api.status_summarizers import summarize_delete_memory_result

        result = {
            "status": "success",
            "deleted": False,
            "memory_id": "xyz123",
            "message": "No matching memory found"
        }

        summary = summarize_delete_memory_result(result)
        assert summary == "Delete failed: No matching memory found"

    def test_delete_memory_error_truncation(self):
        """Test delete_memory summarizer truncates long error messages."""
        from api.status_summarizers import summarize_delete_memory_result

        long_message = "A" * 600  # Longer than 500 char limit
        result = {
            "status": "error",
            "deleted": False,
            "memory_id": "xyz123",
            "message": long_message
        }

        summary = summarize_delete_memory_result(result)
        # "Delete failed: " is 15 chars, so message should be truncated
        assert len(summary) <= 500
        assert summary.startswith("Delete failed: ")


class TestSearchSummarizer:
    """Test internet search tool result summarizer."""

    def test_internet_search_multiple_results(self):
        """Test internet_search summarizer with multiple results."""
        from api.status_summarizers import summarize_internet_search_result

        result = {
            "status": "success",
            "results": [{}, {}, {}, {}, {}]
        }

        summary = summarize_internet_search_result(result)
        assert summary == "Found 5 results"

    def test_internet_search_single_result(self):
        """Test internet_search summarizer with single result."""
        from api.status_summarizers import summarize_internet_search_result

        result = {
            "status": "success",
            "results": [{}]
        }

        summary = summarize_internet_search_result(result)
        assert summary == "Found 1 result"

    def test_internet_search_no_results(self):
        """Test internet_search summarizer with no results."""
        from api.status_summarizers import summarize_internet_search_result

        result = {
            "status": "success",
            "results": []
        }

        summary = summarize_internet_search_result(result)
        assert summary == "No results found"


class TestHealthCheckSummarizer:
    """Test health check tool result summarizer."""

    def test_health_check_ok(self):
        """Test health_check summarizer with OK status."""
        from api.status_summarizers import summarize_health_check_result

        result = {
            "status": "ok",
            "timestamp": "2025-12-16T12:00:00Z"
        }

        summary = summarize_health_check_result(result)
        assert summary == "Health check OK"

    def test_health_check_degraded(self):
        """Test health_check summarizer with non-OK status."""
        from api.status_summarizers import summarize_health_check_result

        result = {
            "status": "degraded",
            "timestamp": "2025-12-16T12:00:00Z"
        }

        summary = summarize_health_check_result(result)
        assert summary == "Health check: degraded"


class TestSummarizerRegistry:
    """Test the main summarize_tool_result function and registry."""

    def test_summarize_tool_result_known_tool(self):
        """Test summarize_tool_result with known tool."""
        from api.status_summarizers import summarize_tool_result

        result = {
            "status": "success",
            "ticker": "AAPL",
            "current_price": 175.50,
            "change_1d_pct": 2.3
        }

        summary = summarize_tool_result("analyze_stock", result)
        assert summary == "AAPL $175.50 (+2.3%)"

    def test_summarize_tool_result_unknown_tool_success(self):
        """Test summarize_tool_result with unknown tool (success)."""
        from api.status_summarizers import summarize_tool_result

        result = {
            "status": "success",
            "data": "some data"
        }

        summary = summarize_tool_result("unknown_tool", result)
        assert summary == "Complete"

    def test_summarize_tool_result_unknown_tool_error(self):
        """Test summarize_tool_result with unknown tool (error)."""
        from api.status_summarizers import summarize_tool_result

        result = {
            "status": "error",
            "message": "Something went wrong with this unknown tool"
        }

        summary = summarize_tool_result("unknown_tool", result)
        assert summary == "Something went wrong with this unknown tool"

    def test_summarize_tool_result_summarizer_exception(self):
        """Test summarize_tool_result with summarizer that raises exception."""
        from api.status_summarizers import summarize_tool_result
        from unittest.mock import patch

        result = {
            "status": "success",
            "ticker": "AAPL"
        }

        # Mock a summarizer that raises an exception
        with patch("api.status_summarizers.SUMMARIZERS") as mock_summarizers:
            def failing_summarizer(r):
                raise ValueError("Summarizer failed")

            mock_summarizers.get.return_value = failing_summarizer

            # Should fall back to generic "Complete"
            summary = summarize_tool_result("analyze_stock", result)
            assert summary == "Complete"

    def test_all_tools_registered(self):
        """Test that all MCP tools are registered in SUMMARIZERS."""
        from api.status_summarizers import SUMMARIZERS

        expected_tools = [
            "get_portfolio",
            "add_holding",
            "update_holding",
            "remove_holding",
            "clear_portfolio",
            "analyze_stock",
            "get_stock_history",
            "get_user_profile",
            "store_memory",
            "delete_memory",  # Story 14.5
            "retrieve_memories",
            "internet_search",
            "health_check"
        ]

        for tool in expected_tools:
            assert tool in SUMMARIZERS, f"Tool {tool} not registered in SUMMARIZERS"

    def test_delete_memory_in_registry(self):
        """Test that delete_memory summarizer is properly registered (Story 14.5)."""
        from api.status_summarizers import SUMMARIZERS, summarize_delete_memory_result

        assert "delete_memory" in SUMMARIZERS
        assert SUMMARIZERS["delete_memory"] == summarize_delete_memory_result


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_missing_fields_graceful_degradation(self):
        """Test that summarizers handle missing fields gracefully."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "success"
            # Missing holdings, total_holdings, total_value
        }

        # Should handle missing fields without crashing
        summary = summarize_portfolio_result(result)
        assert summary == "0 holdings"

    def test_null_values_handled(self):
        """Test that summarizers handle null values in result."""
        from api.status_summarizers import summarize_analyze_stock_result

        result = {
            "status": "success",
            "ticker": None,
            "current_price": None,
            "change_1d_pct": None
        }

        # Should handle None values without crashing
        summary = summarize_analyze_stock_result(result)
        assert "???" in summary  # Ticker defaults to ???

    def test_error_message_truncation(self):
        """Test that error messages are truncated to 500 chars."""
        from api.status_summarizers import summarize_portfolio_result

        long_error = "A" * 600  # Longer than 500 char limit
        result = {
            "status": "error",
            "message": long_error
        }

        summary = summarize_portfolio_result(result)
        assert len(summary) == 500
        assert summary == "A" * 500

    def test_error_message_short(self):
        """Test that short error messages are not truncated."""
        from api.status_summarizers import summarize_portfolio_result

        result = {
            "status": "error",
            "message": "Short error"
        }

        summary = summarize_portfolio_result(result)
        assert summary == "Short error"

    def test_generic_fallback_error_truncation(self):
        """Test that generic fallback truncates long error messages."""
        from api.status_summarizers import summarize_tool_result

        long_error = "B" * 600  # Longer than 500 char limit
        result = {
            "status": "error",
            "message": long_error
        }

        summary = summarize_tool_result("unknown_tool", result)
        assert len(summary) == 500
        assert summary == "B" * 500

    def test_summary_conciseness(self):
        """Test that summaries are concise (<50 chars when possible)."""
        from api.status_summarizers import (
            summarize_portfolio_result,
            summarize_analyze_stock_result,
            summarize_profile_result
        )

        # Test various results to ensure they're concise
        portfolio_result = {
            "status": "success",
            "total_holdings": 10,
            "total_value": 999999.99
        }
        assert len(summarize_portfolio_result(portfolio_result)) < 50

        stock_result = {
            "status": "success",
            "ticker": "AAPL",
            "current_price": 175.50,
            "change_1d_pct": 2.3
        }
        assert len(summarize_analyze_stock_result(stock_result)) < 50

        profile_result = {
            "status": "success",
            "completeness": 67
        }
        assert len(summarize_profile_result(profile_result)) < 50
