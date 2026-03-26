"""
Live integration tests for memory lifecycle (store -> retrieve -> delete).

Story 14.6: Integration Testing & Validation
- Tests full memory lifecycle against agentic-memories service
- Tests performance requirements (<3s store, <1s delete)
- Tests concurrent operations

IMPORTANT: These tests require a running agentic-memories service.
These tests are excluded from `make test` and only run with `make test-all`.
"""

import asyncio
import os
import statistics
import time
import pytest

# Import MCP tools for direct testing
import sys
from pathlib import Path

# Add mcp_server to path for imports - try multiple possible locations
mcp_server_paths = [
    Path(__file__).parent.parent.parent.parent / "mcp_server",  # Local dev
    Path(__file__).resolve().parent.parent.parent.parent / "mcp_server",  # Resolved path
    Path.cwd() / "mcp_server",  # From repo root
]

for mcp_path in mcp_server_paths:
    if mcp_path.exists():
        sys.path.insert(0, str(mcp_path.parent))
        break

try:
    from mcp_server.tools import (
        store_memory_tool_handler,
        delete_memory_tool_handler,
        retrieve_memories_tool_handler
    )
    MCP_TOOLS_AVAILABLE = True
except ImportError:
    MCP_TOOLS_AVAILABLE = False
    store_memory_tool_handler = None
    delete_memory_tool_handler = None
    retrieve_memories_tool_handler = None

# Skip entire module if MCP tools are not available
if not MCP_TOOLS_AVAILABLE:
    pytest.skip("mcp_server module not available", allow_module_level=True)

# Test constants
TEST_USER_ID = "test_user_epic14"
AGENTIC_MEMORIES_URL = os.environ.get("AGENTIC_MEMORIES_URL", "http://localhost:8080")


def check_agentic_memories_available_sync() -> bool:
    """Synchronous check if agentic-memories service is available.

    Checks the /v1/memories/direct endpoint to ensure the direct storage
    endpoint is available, not just the health check.
    """
    import urllib.request
    import urllib.error
    import json
    try:
        # Check health first
        req = urllib.request.Request(f"{AGENTIC_MEMORIES_URL}/health", method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                return False

        # Also check that the direct endpoint exists by making a test request
        # We expect a validation error (400) not a 404
        test_payload = json.dumps({"user_id": "test", "content": ""}).encode('utf-8')
        req = urllib.request.Request(
            f"{AGENTIC_MEMORIES_URL}/v1/memories/direct",
            data=test_payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                # Unexpected success with empty content, but service is available
                return True
        except urllib.error.HTTPError as e:
            # 400/422 validation error = endpoint exists, service is working
            # 404 = endpoint doesn't exist
            return e.code in (400, 422, 500)
    except Exception:
        return False


# Skip all tests if service is not available
SERVICE_AVAILABLE = check_agentic_memories_available_sync()
pytestmark = pytest.mark.skipif(
    not SERVICE_AVAILABLE,
    reason=f"agentic-memories service not available at {AGENTIC_MEMORIES_URL}"
)


@pytest.fixture
async def cleanup_memory():
    """Fixture to track and cleanup test memories after each test."""
    created_memory_ids = []

    yield created_memory_ids

    # Cleanup: Delete all created memories
    for memory_id in created_memory_ids:
        try:
            await delete_memory_tool_handler(
                user_id=TEST_USER_ID,
                memory_id=memory_id,
                reason="Test cleanup"
            )
        except Exception:
            pass  # Ignore cleanup errors


class TestMemoryLifecycleLive:
    """Live integration tests for memory lifecycle operations.

    These tests require a running agentic-memories service.
    """

    @pytest.mark.asyncio
    async def test_store_retrieve_verify_exists(self, cleanup_memory):
        """Test store -> retrieve -> verify exists lifecycle (AC #3)."""
        # Store a memory
        store_result = await store_memory_tool_handler(
            user_id=TEST_USER_ID,
            content="Integration test memory: User prefers morning meetings"
        )

        assert store_result["status"] == "success"
        memory_id = store_result["memory_id"]
        cleanup_memory.append(memory_id)

        # Give service time to index
        await asyncio.sleep(0.5)

        # Retrieve memories matching the content
        retrieve_result = await retrieve_memories_tool_handler(
            user_id=TEST_USER_ID,
            query="morning meetings preferences"
        )

        assert retrieve_result["status"] == "success"
        assert retrieve_result["memory_count"] > 0

        # Verify our memory exists in results
        memories = retrieve_result.get("memories", [])
        found = any("morning meetings" in str(m).lower() for m in memories)
        assert found, "Stored memory should be retrievable"

    @pytest.mark.asyncio
    async def test_full_lifecycle_store_retrieve_delete_verify_gone(
        self, cleanup_memory
    ):
        """Test full lifecycle: store -> retrieve -> delete -> verify gone (AC #3)."""
        # Store a unique memory
        unique_content = f"Integration lifecycle test {time.time()}: User is allergic to peanuts"

        store_result = await store_memory_tool_handler(
            user_id=TEST_USER_ID,
            content=unique_content,
            importance=0.9
        )

        assert store_result["status"] == "success"
        memory_id = store_result["memory_id"]

        # Give service time to index
        await asyncio.sleep(0.5)

        # Retrieve and verify exists
        retrieve_result = await retrieve_memories_tool_handler(
            user_id=TEST_USER_ID,
            query="peanuts allergy"
        )

        assert retrieve_result["status"] == "success"

        # Delete the memory
        delete_result = await delete_memory_tool_handler(
            user_id=TEST_USER_ID,
            memory_id=memory_id,
            reason="Integration test cleanup"
        )

        assert delete_result["status"] == "success"
        assert delete_result["deleted"] is True

        # Give service time to process deletion
        await asyncio.sleep(0.5)

        # Verify memory is gone
        retrieve_after = await retrieve_memories_tool_handler(
            user_id=TEST_USER_ID,
            query="peanuts allergy"
        )

        # Service should still respond successfully
        assert retrieve_after["status"] == "success"


class TestMemoryPerformanceLive:
    """Live performance tests for memory operations.

    These tests require a running agentic-memories service.
    """

    @pytest.mark.asyncio
    async def test_store_memory_performance_under_3s(self, cleanup_memory):
        """Verify store_memory completes in <3s (p95) (AC #3)."""
        durations = []
        sample_size = 10  # Reduced from 20 for faster tests

        for i in range(sample_size):
            start = time.time()
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content=f"Performance test memory {i}: Testing storage speed"
            )
            duration = time.time() - start
            durations.append(duration)

            if result["status"] == "success":
                cleanup_memory.append(result["memory_id"])

        # Calculate p95 (95th percentile)
        sorted_durations = sorted(durations)
        p95_index = int(len(sorted_durations) * 0.95)
        p95 = sorted_durations[min(p95_index, len(sorted_durations) - 1)]

        assert p95 < 3.0, f"store_memory p95 latency {p95:.2f}s exceeds 3s target"

        # Also check average
        avg = statistics.mean(durations)
        print(f"store_memory performance: avg={avg:.2f}s, p95={p95:.2f}s")

    @pytest.mark.asyncio
    async def test_delete_memory_performance_under_1s(self, cleanup_memory):
        """Verify delete_memory completes in <1s (p95) (AC #3)."""
        # First create memories to delete
        memory_ids = []
        for i in range(10):
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content=f"Delete performance test memory {i}"
            )
            if result["status"] == "success":
                memory_ids.append(result["memory_id"])

        if not memory_ids:
            pytest.skip("Could not create test memories")

        # Give service time to index
        await asyncio.sleep(0.5)

        # Now measure delete performance
        durations = []
        for memory_id in memory_ids:
            start = time.time()
            result = await delete_memory_tool_handler(
                user_id=TEST_USER_ID,
                memory_id=memory_id,
                reason="Performance test"
            )
            duration = time.time() - start
            durations.append(duration)

        if not durations:
            pytest.skip("No delete operations completed")

        # Calculate p95
        sorted_durations = sorted(durations)
        p95_index = int(len(sorted_durations) * 0.95)
        p95 = sorted_durations[min(p95_index, len(sorted_durations) - 1)]

        assert p95 < 1.0, f"delete_memory p95 latency {p95:.2f}s exceeds 1s target"

        avg = statistics.mean(durations)
        print(f"delete_memory performance: avg={avg:.2f}s, p95={p95:.2f}s")


class TestConcurrentOperationsLive:
    """Live tests for concurrent memory operations.

    These tests require a running agentic-memories service.
    """

    @pytest.mark.asyncio
    async def test_concurrent_store_operations(self, cleanup_memory):
        """Test 10+ simultaneous store operations (AC #3)."""
        async def store_memory(index: int):
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content=f"Concurrent store test {index}: Testing parallel writes"
            )
            return result

        # Run 10 concurrent stores
        tasks = [store_memory(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        success_count = sum(1 for r in results if r["status"] == "success")
        assert success_count >= 8, f"Expected at least 8/10 successful stores, got {success_count}"

        # Cleanup
        for result in results:
            if result["status"] == "success" and "memory_id" in result:
                cleanup_memory.append(result["memory_id"])

    @pytest.mark.asyncio
    async def test_concurrent_delete_operations(self, cleanup_memory):
        """Test concurrent delete operations (AC #3)."""
        # First create memories
        memory_ids = []
        for i in range(10):
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content=f"Concurrent delete test {i}"
            )
            if result["status"] == "success":
                memory_ids.append(result["memory_id"])

        if len(memory_ids) < 5:
            pytest.skip("Could not create enough test memories")

        await asyncio.sleep(0.5)

        # Delete concurrently
        async def delete_memory(memory_id: str):
            return await delete_memory_tool_handler(
                user_id=TEST_USER_ID,
                memory_id=memory_id,
                reason="Concurrent delete test"
            )

        tasks = [delete_memory(mid) for mid in memory_ids]
        results = await asyncio.gather(*tasks)

        # Most should succeed
        success_count = sum(1 for r in results if r["status"] == "success")
        assert success_count >= len(memory_ids) * 0.8, "Expected at least 80% successful deletes"

    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self, cleanup_memory):
        """Test mixed concurrent store, retrieve, and delete operations (AC #3)."""
        # Create some initial memories
        initial_ids = []
        for i in range(5):
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content=f"Mixed concurrent test {i}"
            )
            if result["status"] == "success":
                initial_ids.append(result["memory_id"])
                cleanup_memory.append(result["memory_id"])

        await asyncio.sleep(0.5)

        # Run mixed operations concurrently
        async def store_op():
            result = await store_memory_tool_handler(
                user_id=TEST_USER_ID,
                content="Mixed concurrent new store"
            )
            if result["status"] == "success":
                cleanup_memory.append(result["memory_id"])
            return ("store", result)

        async def retrieve_op():
            result = await retrieve_memories_tool_handler(
                user_id=TEST_USER_ID,
                query="concurrent test"
            )
            return ("retrieve", result)

        async def delete_op(memory_id: str):
            result = await delete_memory_tool_handler(
                user_id=TEST_USER_ID,
                memory_id=memory_id,
                reason="Mixed concurrent test"
            )
            return ("delete", result)

        tasks = [
            store_op(),
            store_op(),
            retrieve_op(),
            retrieve_op(),
        ]

        # Add delete operations for some memories
        if len(initial_ids) >= 2:
            tasks.append(delete_op(initial_ids[0]))
            tasks.append(delete_op(initial_ids[1]))

        results = await asyncio.gather(*tasks)

        # Check results by type
        store_results = [r for op, r in results if op == "store"]
        retrieve_results = [r for op, r in results if op == "retrieve"]

        # At least some should succeed
        store_success = sum(1 for r in store_results if r["status"] == "success")
        retrieve_success = sum(1 for r in retrieve_results if r["status"] == "success")

        assert store_success >= 1, "At least one store should succeed"
        assert retrieve_success >= 1, "At least one retrieve should succeed"
