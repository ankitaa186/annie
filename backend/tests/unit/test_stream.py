"""
Unit tests for streaming functionality.

Tests SSE streaming handler, client disconnection handling,
error handling, and concurrent stream management.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes.stream import active_streams, MAX_CONCURRENT_STREAMS


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_active_streams():
    """Reset active streams before each test."""
    active_streams.clear()
    yield
    active_streams.clear()


class TestStreamEndpoint:
    """Tests for /api/stream/{conversation_id} endpoint."""

    @pytest.mark.asyncio
    async def test_stream_concurrent_limit(self, client):
        """Test concurrent stream limit enforcement."""
        # Fill up to limit
        for i in range(MAX_CONCURRENT_STREAMS):
            active_streams[f"conv_{i}"] = 1234567890.0

        # Try to exceed limit
        conversation_id = "test_conv_overflow"

        with patch('api.routes.stream.LLMClient'):
            response = client.get(f"/api/stream/{conversation_id}")
            assert response.status_code == 503
            assert "concurrent streams" in response.json()["detail"].lower()

    def test_stream_cleanup_on_completion(self, client):
        """Test that stream is cleaned up from active streams after completion."""
        conversation_id = "test_conv_cleanup"

        with patch('api.routes.stream.LLMClient') as MockLLMClient, \
             patch('api.routes.stream.MCPClient') as MockMCPClient:

            # Mock LLM client
            mock_llm_instance = Mock()
            MockLLMClient.return_value.__aenter__.return_value = mock_llm_instance
            mock_llm_instance.convert_mcp_tools_to_functions = Mock(return_value=[])

            # Mock MCP client
            mock_mcp_instance = AsyncMock()
            MockMCPClient.return_value.__aenter__.return_value = mock_mcp_instance
            mock_mcp_instance.list_tools = AsyncMock(return_value=[])

            # Mock non-streaming call (returns no tool calls)
            mock_llm_instance.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "test"}}]
            })

            # Mock streaming response
            async def mock_stream(messages, tools=None):
                yield {"type": "token", "content": "Test"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            mock_llm_instance.chat_completion_stream = mock_stream

            # Make streaming request
            with client.stream("GET", f"/api/stream/{conversation_id}") as response:
                assert response.status_code == 200

                # Stream should be active during request
                # (Note: This is checked internally)

            # After streaming completes, verify cleanup
            # (active_streams should be empty after connection closes)
            assert conversation_id not in active_streams


class TestStreamHealth:
    """Tests for /api/stream/health endpoint."""

    def test_stream_health_ok(self, client):
        """Test stream health endpoint returns correct status."""
        response = client.get("/api/stream/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "active_streams" in data
        assert "max_concurrent_streams" in data
        assert data["max_concurrent_streams"] == MAX_CONCURRENT_STREAMS
        assert "capacity_remaining" in data
        assert "timestamp" in data

    def test_stream_health_with_active_streams(self, client):
        """Test stream health endpoint with active streams."""
        # Add some active streams
        active_streams["conv_1"] = 1234567890.0
        active_streams["conv_2"] = 1234567891.0

        response = client.get("/api/stream/health")
        assert response.status_code == 200

        data = response.json()
        assert data["active_streams"] == 2
        assert data["capacity_remaining"] == MAX_CONCURRENT_STREAMS - 2


class TestMediaFrameFunctions:
    """Tests for media frame formatting and extraction functions."""

    def test_format_media_frame_photo_url(self):
        """Test formatting a photo media frame with URL source."""
        from api.routes.stream import format_media_frame

        frame = format_media_frame(
            media_type="photo",
            source="https://example.com/image.jpg",
            source_type="url",
            caption="A beautiful sunset"
        )

        assert frame["event"] == "message"
        data = json.loads(frame["data"])
        assert data["type"] == "media"
        assert data["media_type"] == "photo"
        assert data["source"] == "https://example.com/image.jpg"
        assert data["source_type"] == "url"
        assert data["caption"] == "A beautiful sunset"

    def test_format_media_frame_video_base64(self):
        """Test formatting a video media frame with base64 source."""
        from api.routes.stream import format_media_frame

        frame = format_media_frame(
            media_type="video",
            source="base64encodeddata==",
            source_type="base64",
            caption="Video clip",
            duration=30,
            width=1920,
            height=1080
        )

        assert frame["event"] == "message"
        data = json.loads(frame["data"])
        assert data["type"] == "media"
        assert data["media_type"] == "video"
        assert data["source_type"] == "base64"
        assert data["duration"] == 30
        assert data["width"] == 1920
        assert data["height"] == 1080

    def test_format_media_frame_minimal(self):
        """Test formatting media frame with minimal required fields."""
        from api.routes.stream import format_media_frame

        frame = format_media_frame(
            media_type="photo",
            source="https://example.com/image.jpg"
        )

        data = json.loads(frame["data"])
        assert data["type"] == "media"
        assert data["media_type"] == "photo"
        assert data["source"] == "https://example.com/image.jpg"
        assert data["source_type"] == "url"  # default
        assert "caption" not in data  # not included when None
        assert "duration" not in data

    def test_format_media_group_frame(self):
        """Test formatting a media group (album) frame."""
        from api.routes.stream import format_media_group_frame

        items = [
            {"media_type": "photo", "source": "https://example.com/1.jpg", "source_type": "url"},
            {"media_type": "photo", "source": "https://example.com/2.jpg", "source_type": "url", "caption": "Photos from today"},
            {"media_type": "video", "source": "https://example.com/video.mp4", "source_type": "url"}
        ]

        frame = format_media_group_frame(items)

        assert frame["event"] == "message"
        data = json.loads(frame["data"])
        assert data["type"] == "media_group"
        assert len(data["items"]) == 3
        assert data["items"][0]["media_type"] == "photo"
        assert data["items"][1]["caption"] == "Photos from today"
        assert data["items"][2]["media_type"] == "video"

    def test_extract_media_from_tool_result_direct_media(self):
        """Test extracting media from direct media object in tool result."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "media": {
                "type": "photo",
                "url": "https://example.com/generated.jpg",
                "caption": "Generated image"
            }
        }

        media_data = extract_media_from_tool_result(tool_result, "some_tool")

        assert media_data is not None
        assert media_data["single"] is True
        assert media_data["media_type"] == "photo"
        assert media_data["source"] == "https://example.com/generated.jpg"
        assert media_data["caption"] == "Generated image"

    def test_extract_media_from_tool_result_image_generation(self):
        """Test extracting media from image generation tool result."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "image_url": "https://api.dalle.com/generated-image.png",
            "prompt": "A cat wearing a hat"
        }

        media_data = extract_media_from_tool_result(tool_result, "generate_image")

        assert media_data is not None
        assert media_data["single"] is True
        assert media_data["media_type"] == "photo"
        assert media_data["source"] == "https://api.dalle.com/generated-image.png"
        assert media_data["source_type"] == "url"
        assert media_data["caption"] == "A cat wearing a hat"

    def test_extract_media_from_tool_result_base64_image(self):
        """Test extracting base64 image from image generation tool result."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "image_data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "prompt": "A simple pixel"
        }

        media_data = extract_media_from_tool_result(tool_result, "dalle")

        assert media_data is not None
        assert media_data["single"] is True
        assert media_data["source_type"] == "base64"
        assert "iVBORw" in media_data["source"]

    def test_extract_media_from_tool_result_multiple_images(self):
        """Test extracting multiple images from tool result."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "images": [
                {"url": "https://example.com/1.jpg"},
                {"url": "https://example.com/2.jpg"},
                {"url": "https://example.com/3.jpg"}
            ],
            "prompt": "Mountain landscape"
        }

        media_data = extract_media_from_tool_result(tool_result, "stable_diffusion")

        assert media_data is not None
        assert media_data["single"] is False
        assert len(media_data["items"]) == 3
        # Caption only on first item
        assert media_data["items"][0]["caption"] == "Mountain landscape"
        assert media_data["items"][1]["caption"] is None

    def test_extract_media_from_tool_result_media_items_list(self):
        """Test extracting media from media_items list in tool result."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "media_items": [
                {"type": "photo", "url": "https://example.com/photo.jpg"},
                {"type": "video", "url": "https://example.com/video.mp4", "caption": "My video"}
            ]
        }

        media_data = extract_media_from_tool_result(tool_result, "fetch_media")

        assert media_data is not None
        assert media_data["single"] is False
        assert len(media_data["items"]) == 2
        assert media_data["items"][0]["media_type"] == "photo"
        assert media_data["items"][1]["media_type"] == "video"

    def test_extract_media_from_tool_result_single_media_item(self):
        """Test that single item in media_items returns single=True."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "media_items": [
                {"type": "photo", "url": "https://example.com/single.jpg", "caption": "Single photo"}
            ]
        }

        media_data = extract_media_from_tool_result(tool_result, "fetch_media")

        assert media_data is not None
        assert media_data["single"] is True
        assert media_data["media_type"] == "photo"

    def test_extract_media_from_tool_result_no_media(self):
        """Test that non-media tool results return None."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "status": "success",
            "data": {"name": "John", "age": 30}
        }

        media_data = extract_media_from_tool_result(tool_result, "get_user_profile")

        assert media_data is None

    def test_extract_media_from_tool_result_non_dict(self):
        """Test that non-dict tool results return None."""
        from api.routes.stream import extract_media_from_tool_result

        assert extract_media_from_tool_result("string result", "tool") is None
        assert extract_media_from_tool_result(123, "tool") is None
        assert extract_media_from_tool_result(None, "tool") is None
        assert extract_media_from_tool_result(["list", "result"], "tool") is None

    def test_extract_media_from_tool_result_browser_screenshot(self):
        """Test extraction of browser_action screenshot results."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "status": "success",
            "session_id": "abc123",
            "results": [
                {"action": "navigate", "status": "success"},
                {"action": "screenshot", "status": "success", "data": {
                    "base64": "iVBORw0KGgoAAAANSUhEUg==",
                    "width": 1280,
                    "height": 720
                }}
            ],
            "duration_ms": 3500
        }

        media_data = extract_media_from_tool_result(tool_result, "browser_action")

        assert media_data is not None
        assert media_data["single"] is True
        assert media_data["media_type"] == "photo"
        assert media_data["source"] == "iVBORw0KGgoAAAANSUhEUg=="
        assert media_data["source_type"] == "base64"
        assert media_data["width"] == 1280
        assert media_data["height"] == 720

    def test_extract_media_from_tool_result_browser_multiple_screenshots(self):
        """Test extraction of multiple browser screenshots as media group."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "status": "success",
            "session_id": "abc123",
            "results": [
                {"action": "screenshot", "status": "success", "data": {
                    "base64": "img1data", "width": 1280, "height": 720
                }},
                {"action": "screenshot", "status": "success", "data": {
                    "base64": "img2data", "width": 800, "height": 600
                }}
            ]
        }

        media_data = extract_media_from_tool_result(tool_result, "browser_action")

        assert media_data is not None
        assert media_data["single"] is False
        assert len(media_data["items"]) == 2
        assert media_data["items"][0]["source"] == "img1data"
        assert media_data["items"][1]["source"] == "img2data"

    def test_extract_media_from_tool_result_browser_no_screenshot(self):
        """Test that browser results without screenshots return None."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "status": "success",
            "session_id": "abc123",
            "results": [
                {"action": "navigate", "status": "success"},
                {"action": "content", "status": "success", "data": {"text": "page content"}}
            ]
        }

        media_data = extract_media_from_tool_result(tool_result, "browser_action")
        assert media_data is None

    def test_extract_media_from_tool_result_browser_failed_screenshot(self):
        """Test that failed browser screenshots are not extracted."""
        from api.routes.stream import extract_media_from_tool_result

        tool_result = {
            "status": "success",
            "session_id": "abc123",
            "results": [
                {"action": "screenshot", "status": "error", "error": "Timeout"}
            ]
        }

        media_data = extract_media_from_tool_result(tool_result, "browser_action")
        assert media_data is None


class TestBuildMediaSseFrames:
    """Tests for build_media_sse_frames helper function."""

    def test_single_media_returns_one_frame(self):
        """Test single media item returns one SSE frame."""
        from api.routes.stream import build_media_sse_frames

        media_data = {
            "single": True,
            "media_type": "photo",
            "source": "https://example.com/image.jpg",
            "source_type": "url",
            "caption": "Test caption"
        }

        frames = build_media_sse_frames(media_data)
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["type"] == "media"
        assert data["media_type"] == "photo"
        assert data["caption"] == "Test caption"

    def test_multiple_media_returns_media_group_frame(self):
        """Test multiple media items return a media_group frame."""
        from api.routes.stream import build_media_sse_frames

        media_data = {
            "single": False,
            "items": [
                {"media_type": "photo", "source": "url1", "source_type": "url"},
                {"media_type": "photo", "source": "url2", "source_type": "url"}
            ]
        }

        frames = build_media_sse_frames(media_data)
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["type"] == "media_group"
        assert len(data["items"]) == 2

    def test_single_media_with_optional_fields(self):
        """Test single media with all optional fields."""
        from api.routes.stream import build_media_sse_frames

        media_data = {
            "single": True,
            "media_type": "video",
            "source": "base64data",
            "source_type": "base64",
            "caption": "Video",
            "filename": "clip.mp4",
            "duration": 30,
            "width": 1920,
            "height": 1080
        }

        frames = build_media_sse_frames(media_data)
        data = json.loads(frames[0]["data"])
        assert data["duration"] == 30
        assert data["width"] == 1920
        assert data["height"] == 1080
        assert data["filename"] == "clip.mp4"


class TestOffloadBase64ToRedis:
    """Tests for offload_base64_to_redis helper function."""

    @pytest.mark.asyncio
    async def test_offload_single_large_base64(self):
        """Verify large base64 source is stored in Redis and replaced with redis_ref."""
        from api.routes.stream import offload_base64_to_redis, MEDIA_OFFLOAD_TTL

        large_data = "A" * (65 * 1024)  # > 64 KB threshold
        media_data = {
            "single": True,
            "media_type": "photo",
            "source": large_data,
            "source_type": "base64",
        }

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        result = await offload_base64_to_redis(media_data, mock_redis, "conv_123")

        assert result["source_type"] == "redis_ref"
        assert result["source"].startswith("media:conv_123:")
        mock_redis.set.assert_called_once()
        # Verify TTL is passed
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == MEDIA_OFFLOAD_TTL or call_args[1].get("ex") == MEDIA_OFFLOAD_TTL

    @pytest.mark.asyncio
    async def test_offload_single_small_base64(self):
        """Verify small base64 is NOT offloaded."""
        from api.routes.stream import offload_base64_to_redis

        small_data = "A" * 100  # well under 64 KB
        media_data = {
            "single": True,
            "media_type": "photo",
            "source": small_data,
            "source_type": "base64",
        }

        mock_redis = AsyncMock()

        result = await offload_base64_to_redis(media_data, mock_redis, "conv_123")

        assert result["source_type"] == "base64"
        assert result["source"] == small_data
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_offload_media_group(self):
        """Verify per-item offloading in a media group."""
        from api.routes.stream import offload_base64_to_redis

        large_data = "B" * (65 * 1024)
        small_data = "C" * 100
        media_data = {
            "single": False,
            "items": [
                {"media_type": "photo", "source": large_data, "source_type": "base64"},
                {"media_type": "photo", "source": small_data, "source_type": "base64"},
                {"media_type": "photo", "source": "https://example.com/img.jpg", "source_type": "url"},
            ]
        }

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        result = await offload_base64_to_redis(media_data, mock_redis, "conv_456")

        # First item (large) should be offloaded
        assert result["items"][0]["source_type"] == "redis_ref"
        assert result["items"][0]["source"].startswith("media:conv_456:")
        # Second item (small) should stay inline
        assert result["items"][1]["source_type"] == "base64"
        assert result["items"][1]["source"] == small_data
        # Third item (url) should be untouched
        assert result["items"][2]["source_type"] == "url"
        # Only one SET call (for the large item)
        assert mock_redis.set.call_count == 1

    @pytest.mark.asyncio
    async def test_offload_redis_failure(self):
        """Verify graceful fallback when Redis SET fails."""
        from api.routes.stream import offload_base64_to_redis

        large_data = "D" * (65 * 1024)
        media_data = {
            "single": True,
            "media_type": "photo",
            "source": large_data,
            "source_type": "base64",
        }

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis connection lost"))

        result = await offload_base64_to_redis(media_data, mock_redis, "conv_789")

        # Should fall back to inline (unchanged)
        assert result["source_type"] == "base64"
        assert result["source"] == large_data

    @pytest.mark.asyncio
    async def test_offload_non_base64(self):
        """Verify URL and file_id source types are skipped."""
        from api.routes.stream import offload_base64_to_redis

        media_data = {
            "single": True,
            "media_type": "photo",
            "source": "https://example.com/image.jpg",
            "source_type": "url",
        }

        mock_redis = AsyncMock()

        result = await offload_base64_to_redis(media_data, mock_redis, "conv_abc")

        assert result["source_type"] == "url"
        assert result["source"] == "https://example.com/image.jpg"
        mock_redis.set.assert_not_called()


# Note: LLM client streaming is tested through integration tests
# and the stream endpoint tests above. Direct LLM client streaming tests
# are complex to mock properly and are better covered by higher-level tests.
