"""
Unit tests for Cloudflare Access Authentication Middleware

Tests authentication scenarios for web users via Cloudflare Access JWT tokens.
"""

import pytest
import jwt
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from api.middleware.cloudflare_auth import (
    cloudflare_auth_middleware,
    should_bypass_auth,
    extract_email_from_jwt,
    USER_MAPPING,
    BYPASS_PATHS,
)


# Test JWT creation helper
def create_test_jwt(email: str, extra_claims: dict = None) -> str:
    """Create a test JWT token with the given email."""
    payload = {"email": email}
    if extra_claims:
        payload.update(extra_claims)
    # Note: We don't sign with a real key because middleware doesn't verify signature
    return jwt.encode(payload, "test-secret", algorithm="HS256")


def create_malformed_jwt() -> str:
    """Create a malformed JWT token that will fail decoding."""
    return "not.a.valid.jwt.token"


# Create test app with middleware
def create_test_app():
    """Create a FastAPI app with Cloudflare auth middleware for testing."""
    app = FastAPI()

    @app.middleware("http")
    async def cf_auth(request: Request, call_next):
        return await cloudflare_auth_middleware(request, call_next)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/health/full")
    async def health_full():
        return {"status": "ok", "components": {}}

    @app.get("/")
    async def root():
        return {"name": "Annie Backend API"}

    @app.get("/assets/style.css")
    async def static_asset():
        return {"content": "css content"}

    @app.get("/api/chat")
    async def chat_endpoint(request: Request):
        # Return user info from request state if authenticated
        user_id = getattr(request.state, "user_id", None)
        email = getattr(request.state, "email", None)
        return {"user_id": user_id, "email": email}

    @app.get("/api/conversations")
    async def conversations_endpoint(request: Request):
        user_id = getattr(request.state, "user_id", None)
        email = getattr(request.state, "email", None)
        return {"user_id": user_id, "email": email}

    return app


@pytest.fixture
def client():
    """Test client with Cloudflare auth middleware."""
    app = create_test_app()
    return TestClient(app)


# ============================================================================
# Test: should_bypass_auth function
# ============================================================================

class TestShouldBypassAuth:
    """Tests for the should_bypass_auth helper function."""

    def test_health_endpoint_bypassed(self):
        """Test /health bypasses auth."""
        assert should_bypass_auth("/health") is True

    def test_health_full_endpoint_bypassed(self):
        """Test /health/full bypasses auth."""
        assert should_bypass_auth("/health/full") is True

    def test_root_endpoint_bypassed(self):
        """Test / bypasses auth."""
        assert should_bypass_auth("/") is True

    def test_assets_endpoint_bypassed(self):
        """Test /assets bypasses auth."""
        assert should_bypass_auth("/assets") is True

    def test_assets_subpath_bypassed(self):
        """Test /assets/* paths bypass auth."""
        assert should_bypass_auth("/assets/style.css") is True
        assert should_bypass_auth("/assets/js/app.js") is True

    def test_api_endpoints_not_bypassed(self):
        """Test API endpoints are NOT bypassed."""
        assert should_bypass_auth("/api/chat") is False
        assert should_bypass_auth("/api/conversations") is False
        assert should_bypass_auth("/api/stream/123") is False

    def test_similar_paths_not_bypassed(self):
        """Test paths that look similar but shouldn't be bypassed."""
        assert should_bypass_auth("/healthcare") is False
        assert should_bypass_auth("/assets-manager") is False


# ============================================================================
# Test: extract_email_from_jwt function
# ============================================================================

class TestExtractEmailFromJWT:
    """Tests for JWT email extraction."""

    def test_valid_jwt_with_email(self):
        """Test extracting email from valid JWT."""
        token = create_test_jwt("test@example.com")
        email = extract_email_from_jwt(token)
        assert email == "test@example.com"

    def test_valid_jwt_without_email(self):
        """Test JWT without email claim returns None."""
        payload = {"sub": "user123"}
        token = jwt.encode(payload, "secret", algorithm="HS256")
        email = extract_email_from_jwt(token)
        assert email is None

    def test_malformed_jwt_returns_none(self):
        """Test malformed JWT returns None (doesn't raise)."""
        email = extract_email_from_jwt("not.valid.jwt")
        assert email is None

    def test_empty_string_returns_none(self):
        """Test empty string returns None."""
        email = extract_email_from_jwt("")
        assert email is None

    def test_jwt_with_extra_claims(self):
        """Test JWT with extra claims still extracts email."""
        token = create_test_jwt("test@example.com", {
            "sub": "user123",
            "aud": "annie-app",
            "iss": "cloudflare"
        })
        email = extract_email_from_jwt(token)
        assert email == "test@example.com"


# ============================================================================
# Test: Valid CF JWT authentication (AC: 1, 2, 3)
# ============================================================================

class TestValidJWTAuth:
    """Tests for successful authentication with valid CF JWT."""

    def test_valid_jwt_known_email_succeeds(self, client):
        """Test valid CF JWT with known email -> successful auth (AC: 1, 2)."""
        token = create_test_jwt("user@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "YOUR_USER_ID"  # Mapped user_id (AC: 2)
        assert data["email"] == "user@example.com"

    def test_user_id_matches_telegram(self, client):
        """Test user_id matches Telegram user_id (AC: 3)."""
        token = create_test_jwt("user@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        # YOUR_USER_ID is the Telegram user_id for Ankit
        assert response.json()["user_id"] == "YOUR_USER_ID"

    def test_user_id_attached_to_request_state(self, client):
        """Test user_id is attached to request.state for route handlers (AC: 1)."""
        token = create_test_jwt("user@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/chat", headers=headers)

        assert response.status_code == 200
        # Route handler can access request.state.user_id
        assert response.json()["user_id"] == "YOUR_USER_ID"


# ============================================================================
# Test: Email header fallback (AC: 4, 5 fallback)
# ============================================================================

class TestEmailHeaderFallback:
    """Tests for fallback to CF-Access-Authenticated-User-Email header."""

    def test_email_header_fallback_succeeds(self, client):
        """Test successful auth via email header when JWT fails (AC: 2.1)."""
        headers = {"CF-Access-Authenticated-User-Email": "user@example.com"}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "YOUR_USER_ID"
        assert data["email"] == "user@example.com"

    def test_jwt_preferred_over_email_header(self, client):
        """Test JWT is preferred when both headers present."""
        jwt_token = create_test_jwt("user@example.com")
        headers = {
            "CF-Access-JWT-Assertion": jwt_token,
            "CF-Access-Authenticated-User-Email": "different@example.com"
        }

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        # Email from JWT is used, not the header
        assert response.json()["email"] == "user@example.com"


# ============================================================================
# Test: Unknown email rejection (AC: 4)
# ============================================================================

class TestUnknownEmailRejection:
    """Tests for rejection of unknown emails."""

    def test_unknown_email_in_jwt_rejected(self, client):
        """Test unknown email returns 401 (AC: 4)."""
        token = create_test_jwt("unknown@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "not registered" in response.json()["detail"].lower()

    def test_unknown_email_in_header_rejected(self, client):
        """Test unknown email via header returns 401 (AC: 4)."""
        headers = {"CF-Access-Authenticated-User-Email": "unknown@example.com"}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "not registered" in response.json()["detail"].lower()


# ============================================================================
# Test: Missing headers handling (AC: 5)
# ============================================================================

class TestMissingHeaders:
    """Tests for handling missing CF headers."""

    def test_no_cf_headers_passes_through(self, client):
        """Test requests without CF headers pass through (Telegram compatibility)."""
        # No CF headers - this is a Telegram bot request
        response = client.get("/api/chat")

        assert response.status_code == 200
        # No user_id attached (Telegram flow provides it in request body)
        assert response.json()["user_id"] is None

    def test_cf_jwt_without_email_rejected(self, client):
        """Test CF JWT present but no email extractable returns 401."""
        # JWT without email claim
        payload = {"sub": "user123"}
        token = jwt.encode(payload, "secret", algorithm="HS256")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "unable to extract email" in response.json()["detail"].lower()


# ============================================================================
# Test: Malformed JWT handling (AC: 2.4, 10)
# ============================================================================

class TestMalformedJWT:
    """Tests for malformed JWT handling."""

    def test_malformed_jwt_returns_401(self, client):
        """Test malformed JWT returns 401 (AC: 7.5)."""
        headers = {"CF-Access-JWT-Assertion": "not.a.valid.jwt.token"}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401

    def test_malformed_jwt_with_email_header_fallback(self, client):
        """Test malformed JWT falls back to email header."""
        headers = {
            "CF-Access-JWT-Assertion": "not.valid.jwt",
            "CF-Access-Authenticated-User-Email": "user@example.com"
        }

        response = client.get("/api/conversations", headers=headers)

        # Falls back to email header
        assert response.status_code == 200
        assert response.json()["user_id"] == "YOUR_USER_ID"


# ============================================================================
# Test: Bypass paths (AC: 6, 7)
# ============================================================================

class TestBypassPaths:
    """Tests for authentication bypass paths."""

    def test_health_endpoint_no_auth_required(self, client):
        """Test /health bypasses auth - no headers needed (AC: 6)."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_full_endpoint_no_auth_required(self, client):
        """Test /health/full bypasses auth (AC: 6)."""
        response = client.get("/health/full")

        assert response.status_code == 200

    def test_root_endpoint_no_auth_required(self, client):
        """Test / bypasses auth (AC: 7)."""
        response = client.get("/")

        assert response.status_code == 200

    def test_static_assets_no_auth_required(self, client):
        """Test /assets/* bypasses auth (AC: 7)."""
        response = client.get("/assets/style.css")

        assert response.status_code == 200


# ============================================================================
# Test: Telegram flow compatibility
# ============================================================================

class TestTelegramCompatibility:
    """Tests for backward compatibility with Telegram bot flow."""

    def test_telegram_requests_pass_through(self, client):
        """Test Telegram bot requests (no CF headers) pass through unchanged."""
        # Telegram bot calls /api/chat without CF headers
        response = client.get("/api/chat")

        # Request passes through - route handler works
        assert response.status_code == 200
        # No user_id from middleware (Telegram provides via request body)
        assert response.json()["user_id"] is None

    def test_mixed_environment_works(self, client):
        """Test both web (with CF) and Telegram (without CF) flows work."""
        # Web flow with CF headers
        token = create_test_jwt("user@example.com")
        web_response = client.get(
            "/api/conversations",
            headers={"CF-Access-JWT-Assertion": token}
        )
        assert web_response.status_code == 200
        assert web_response.json()["user_id"] == "YOUR_USER_ID"

        # Telegram flow without CF headers
        telegram_response = client.get("/api/chat")
        assert telegram_response.status_code == 200
        assert telegram_response.json()["user_id"] is None


# ============================================================================
# Test: User mapping configuration
# ============================================================================

class TestUserMapping:
    """Tests for USER_MAPPING configuration."""

    def test_user_mapping_contains_expected_user(self):
        """Test USER_MAPPING has the expected user."""
        assert "user@example.com" in USER_MAPPING
        assert USER_MAPPING["user@example.com"] == "YOUR_USER_ID"

    def test_bypass_paths_includes_expected_paths(self):
        """Test BYPASS_PATHS contains expected paths."""
        assert "/health" in BYPASS_PATHS
        assert "/health/full" in BYPASS_PATHS
        assert "/" in BYPASS_PATHS
        assert "/assets" in BYPASS_PATHS


# ============================================================================
# Test: Audit logging (AC: 8)
# ============================================================================

class TestAuditLogging:
    """Tests for authentication audit logging."""

    @patch("api.middleware.cloudflare_auth.logger")
    def test_successful_auth_logged(self, mock_logger, client):
        """Test successful auth logs email, user_id, path (AC: 8, 4.1)."""
        token = create_test_jwt("user@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        # Check logger.info was called with success event
        info_calls = [call for call in mock_logger.info.call_args_list]
        assert len(info_calls) > 0

        # Find the CF auth success log
        success_log = None
        for call in info_calls:
            if "CF auth success" in str(call):
                success_log = call
                break

        assert success_log is not None
        extra = success_log.kwargs.get("extra", {})
        assert extra.get("event") == "cf_auth_success"
        assert extra.get("email") == "user@example.com"
        assert extra.get("user_id") == "YOUR_USER_ID"
        assert "/api/conversations" in extra.get("path", "")

    @patch("api.middleware.cloudflare_auth.logger")
    def test_failed_auth_logged(self, mock_logger, client):
        """Test failed auth logs reason (AC: 8, 4.2)."""
        token = create_test_jwt("unknown@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        # Check logger.warning was called
        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert len(warning_calls) > 0

        # Find the unknown email warning
        unknown_email_log = None
        for call in warning_calls:
            extra = call.kwargs.get("extra", {})
            if extra.get("event") == "cf_auth_unknown_email":
                unknown_email_log = call
                break

        assert unknown_email_log is not None
        extra = unknown_email_log.kwargs.get("extra", {})
        assert extra.get("email") == "unknown@example.com"

    @patch("api.middleware.cloudflare_auth.logger")
    def test_unknown_email_security_logged(self, mock_logger, client):
        """Test unknown email attempts logged for security monitoring (AC: 8, 4.3)."""
        token = create_test_jwt("attacker@malicious.com")
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        warning_calls = mock_logger.warning.call_args_list
        # Should have a warning for unknown email
        unknown_email_logged = any(
            "cf_auth_unknown_email" in str(call.kwargs.get("extra", {}))
            for call in warning_calls
        )
        assert unknown_email_logged


