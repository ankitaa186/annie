"""
Unit tests for backend.api.utils helpers.
"""

import logging
import pytest
from unittest.mock import AsyncMock

from api.utils import invalidate_profile_cache_if_needed


@pytest.fixture
def redis_mock():
    """Mock async Redis client."""
    mock = AsyncMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def logger():
    return logging.getLogger("test_utils")


@pytest.mark.asyncio
async def test_invalidate_profile_cache_if_needed_deletes_on_success(redis_mock, logger):
    """Happy path: update_user_profile + status=success → cache deleted."""
    await invalidate_profile_cache_if_needed(
        tool_name="update_user_profile",
        tool_result={"status": "success", "field": "name"},
        user_id="user123",
        redis_client=redis_mock,
        logger=logger,
    )
    redis_mock.delete.assert_awaited_once_with("profile:user123")


@pytest.mark.asyncio
async def test_invalidate_no_op_for_other_tools(redis_mock, logger):
    """Non-profile tools must not invalidate the cache."""
    await invalidate_profile_cache_if_needed(
        tool_name="retrieve_memories",
        tool_result={"status": "success"},
        user_id="user123",
        redis_client=redis_mock,
        logger=logger,
    )
    redis_mock.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_no_op_on_error_status(redis_mock, logger):
    """Failed update_user_profile must not invalidate cache."""
    await invalidate_profile_cache_if_needed(
        tool_name="update_user_profile",
        tool_result={"status": "error", "message": "boom"},
        user_id="user123",
        redis_client=redis_mock,
        logger=logger,
    )
    redis_mock.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_no_op_on_non_dict_result(redis_mock, logger):
    """Non-dict results (e.g., None or strings) must not raise or invalidate."""
    await invalidate_profile_cache_if_needed(
        tool_name="update_user_profile",
        tool_result=None,
        user_id="user123",
        redis_client=redis_mock,
        logger=logger,
    )
    redis_mock.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_no_op_when_redis_missing(logger):
    """Missing redis client must not raise."""
    await invalidate_profile_cache_if_needed(
        tool_name="update_user_profile",
        tool_result={"status": "success"},
        user_id="user123",
        redis_client=None,
        logger=logger,
    )


@pytest.mark.asyncio
async def test_invalidate_no_op_when_user_id_missing(redis_mock, logger):
    """Missing user_id must not invalidate (nothing to invalidate)."""
    await invalidate_profile_cache_if_needed(
        tool_name="update_user_profile",
        tool_result={"status": "success"},
        user_id=None,
        redis_client=redis_mock,
        logger=logger,
    )
    redis_mock.delete.assert_not_called()


@pytest.mark.asyncio
async def test_invalidate_swallows_redis_errors(redis_mock, logger, caplog):
    """Redis errors during delete must never propagate."""
    redis_mock.delete.side_effect = RuntimeError("redis down")

    with caplog.at_level(logging.WARNING, logger="test_utils"):
        # Must not raise
        await invalidate_profile_cache_if_needed(
            tool_name="update_user_profile",
            tool_result={"status": "success"},
            user_id="user123",
            redis_client=redis_mock,
            logger=logger,
        )

    redis_mock.delete.assert_awaited_once_with("profile:user123")
    # A warning should have been logged
    assert any(
        "Failed to invalidate profile cache" in record.message
        for record in caplog.records
    )
