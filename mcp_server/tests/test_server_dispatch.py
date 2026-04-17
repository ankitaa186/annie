"""
Tests for the MCP server's tools/call dispatch layer.

Regression tests for the malformed-tool-call hardening in
`MCPServer.handle_tool_call`: missing required arguments should surface as
a clear JSON-RPC -32602 error with the list of missing fields, not as a
stringified Python TypeError from `tool_handler(**arguments)`.
"""

from unittest.mock import AsyncMock

import pytest

from mcp_server.server import MCPServer


@pytest.fixture
def server():
    return MCPServer()


@pytest.mark.asyncio
async def test_missing_required_argument_returns_clear_jsonrpc_error(server):
    """store_memory missing `content` -> -32602 with explicit missing field list."""
    response = await server.handle_tool_call(
        request_id=1,
        params={
            "name": "store_memory",
            "arguments": {"user_id": "12345", "layer": "semantic"},
        },
    )

    assert "error" in response, response
    err = response["error"]
    assert err["code"] == -32602
    assert "store_memory" in err["message"]
    assert "content" in err["message"]
    # And explicit guidance for the LLM to retry correctly.
    assert "retry" in err["message"].lower()


@pytest.mark.asyncio
async def test_missing_multiple_required_arguments_listed(server):
    """All missing required args should be named in the error message."""
    response = await server.handle_tool_call(
        request_id=2,
        params={"name": "store_memory", "arguments": {}},
    )

    assert response["error"]["code"] == -32602
    msg = response["error"]["message"]
    assert "user_id" in msg
    assert "content" in msg


@pytest.mark.asyncio
async def test_unknown_keys_do_not_count_as_providing_required(server, monkeypatch):
    """
    LLM sending `{"text": "..."}` instead of `{"content": "..."}` should still
    trigger the missing-required error rather than silently dropping the text
    and then blowing up inside the handler.
    """
    # Handler must not be invoked when required args are missing.
    tool_info = server.tool_registry.get_tool("store_memory")
    mock_handler = AsyncMock(return_value={"status": "success"})
    monkeypatch.setitem(tool_info, "handler", mock_handler)

    response = await server.handle_tool_call(
        request_id=3,
        params={
            "name": "store_memory",
            "arguments": {"user_id": "12345", "text": "sleep apnea"},
        },
    )

    assert response["error"]["code"] == -32602
    assert "content" in response["error"]["message"]
    mock_handler.assert_not_called()


@pytest.mark.asyncio
async def test_valid_call_passes_through_to_handler(server, monkeypatch):
    """Sanity check: well-formed calls still dispatch to the handler."""
    tool_info = server.tool_registry.get_tool("store_memory")
    mock_handler = AsyncMock(return_value={"status": "success", "memory_id": "m1"})
    monkeypatch.setitem(tool_info, "handler", mock_handler)

    response = await server.handle_tool_call(
        request_id=4,
        params={
            "name": "store_memory",
            "arguments": {
                "user_id": "12345",
                "content": "User has sleep apnea",
                "layer": "semantic",
            },
        },
    )

    assert "error" not in response, response
    assert response["result"]["content"][0]["type"] == "text"
    mock_handler.assert_awaited_once()
    call_kwargs = mock_handler.await_args.kwargs
    assert call_kwargs["user_id"] == "12345"
    assert call_kwargs["content"] == "User has sleep apnea"
    assert call_kwargs["layer"] == "semantic"
