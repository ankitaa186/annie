"""
Unit tests for Cloudflare Access Authentication Middleware

Tests authentication scenarios for web users via Cloudflare Access JWT tokens.
"""

import pytest
import jwt
from unittest.mock import patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Test constants - no real user data
TEST_EMAIL = "testuser@example.com"
TEST_USER_ID = "test-user-123"
TEST_DEV_USER_ID = "dev-user-456"


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Set test environment variables before middleware module is loaded."""
    monkeypatch.setenv("CF_USER_MAPPING", f"{TEST_EMAIL}:{TEST_USER_ID}")
    monkeypatch.setenv("DEV_MODE_USER_ID", TEST_DEV_USER_ID)
    monkeypatch.setenv("ENVIRONMENT", "dev")


# We need to reload the module after setting env vars
@pytest.fixture
def auth_module(_set_test_env):
    """Reload the cloudflare_auth module with test env vars."""
    import importlib
    import api.middleware.cloudflare_auth as mod
    importlib.reload(mod)
    return mod


@pytest.fixture
def client(auth_module):
    """Test client with Cloudflare auth middleware."""
    app = FastAPI()

    @app.middleware("http")
    async def cf_auth(request: Request, call_next):
        return await auth_module.cloudflare_auth_middleware(request, call_next)

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
        user_id = getattr(request.state, "user_id", None)
        email = getattr(request.state, "email", None)
        return {"user_id": user_id, "email": email}

    @app.get("/api/conversations")
    async def conversations_endpoint(request: Request):
        user_id = getattr(request.state, "user_id", None)
        email = getattr(request.state, "email", None)
        return {"user_id": user_id, "email": email}

    return TestClient(app)


# Test JWT creation helper
def create_test_jwt(email: str, extra_claims: dict = None) -> str:
    """Create a test JWT token with the given email."""
    payload = {"email": email}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, "test-secret", algorithm="HS256")


# ============================================================================
# Test: should_bypass_auth function
# ============================================================================

class TestShouldBypassAuth:
    """Tests for the should_bypass_auth helper function."""

    def test_health_endpoint_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/health") is True

    def test_health_full_endpoint_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/health/full") is True

    def test_root_endpoint_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/") is True

    def test_assets_endpoint_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/assets") is True

    def test_assets_subpath_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/assets/style.css") is True
        assert auth_module.should_bypass_auth("/assets/js/app.js") is True

    def test_api_endpoints_not_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/api/chat") is False
        assert auth_module.should_bypass_auth("/api/conversations") is False
        assert auth_module.should_bypass_auth("/api/stream/123") is False

    def test_similar_paths_not_bypassed(self, auth_module):
        assert auth_module.should_bypass_auth("/healthcare") is False
        assert auth_module.should_bypass_auth("/assets-manager") is False


# ============================================================================
# Test: extract_email_from_jwt function
# ============================================================================

class TestExtractEmailFromJWT:
    """Tests for JWT email extraction."""

    def test_valid_jwt_with_email(self, auth_module):
        token = create_test_jwt("test@example.com")
        email = auth_module.extract_email_from_jwt(token)
        assert email == "test@example.com"

    def test_valid_jwt_without_email(self, auth_module):
        payload = {"sub": "user123"}
        token = jwt.encode(payload, "secret", algorithm="HS256")
        email = auth_module.extract_email_from_jwt(token)
        assert email is None

    def test_malformed_jwt_returns_none(self, auth_module):
        email = auth_module.extract_email_from_jwt("not.valid.jwt")
        assert email is None

    def test_empty_string_returns_none(self, auth_module):
        email = auth_module.extract_email_from_jwt("")
        assert email is None

    def test_jwt_with_extra_claims(self, auth_module):
        token = create_test_jwt("test@example.com", {
            "sub": "user123",
            "aud": "annie-app",
            "iss": "cloudflare"
        })
        email = auth_module.extract_email_from_jwt(token)
        assert email == "test@example.com"


# ============================================================================
# Test: Valid CF JWT authentication
# ============================================================================

class TestValidJWTAuth:
    """Tests for successful authentication with valid CF JWT."""

    def test_valid_jwt_known_email_succeeds(self, client):
        """Test valid CF JWT with known email -> successful auth."""
        token = create_test_jwt(TEST_EMAIL)
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["email"] == TEST_EMAIL

    def test_user_id_matches_mapping(self, client):
        """Test user_id matches configured mapping."""
        token = create_test_jwt(TEST_EMAIL)
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        assert response.json()["user_id"] == TEST_USER_ID

    def test_user_id_attached_to_request_state(self, client):
        """Test user_id is attached to request.state for route handlers."""
        token = create_test_jwt(TEST_EMAIL)
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/chat", headers=headers)

        assert response.status_code == 200
        assert response.json()["user_id"] == TEST_USER_ID


# ============================================================================
# Test: Email header fallback
# ============================================================================

class TestEmailHeaderFallback:
    """Tests for fallback to CF-Access-Authenticated-User-Email header."""

    def test_email_header_fallback_succeeds(self, client):
        """Test successful auth via email header when JWT fails."""
        headers = {"CF-Access-Authenticated-User-Email": TEST_EMAIL}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["email"] == TEST_EMAIL

    def test_jwt_preferred_over_email_header(self, client):
        """Test JWT is preferred when both headers present."""
        jwt_token = create_test_jwt(TEST_EMAIL)
        headers = {
            "CF-Access-JWT-Assertion": jwt_token,
            "CF-Access-Authenticated-User-Email": "different@example.com"
        }

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        assert response.json()["email"] == TEST_EMAIL


# ============================================================================
# Test: Unknown email rejection
# ============================================================================

class TestUnknownEmailRejection:
    """Tests for rejection of unknown emails."""

    def test_unknown_email_in_jwt_rejected(self, client):
        """Test unknown email returns 401."""
        token = create_test_jwt("unknown@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "not registered" in response.json()["detail"].lower()

    def test_unknown_email_in_header_rejected(self, client):
        """Test unknown email via header returns 401."""
        headers = {"CF-Access-Authenticated-User-Email": "unknown@example.com"}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "not registered" in response.json()["detail"].lower()


# ============================================================================
# Test: Missing headers handling
# ============================================================================

class TestMissingHeaders:
    """Tests for handling missing CF headers."""

    def test_no_cf_headers_passes_through(self, client):
        """Test requests without CF headers pass through (Telegram compatibility)."""
        response = client.get("/api/chat")

        assert response.status_code == 200
        assert response.json()["user_id"] is None

    def test_dev_mode_web_request_gets_dev_user_id(self, client):
        """Test web requests in dev mode get DEV_MODE_USER_ID auto-assigned."""
        headers = {"Origin": "http://localhost:3000"}

        response = client.get("/api/chat", headers=headers)

        assert response.status_code == 200
        assert response.json()["user_id"] == TEST_DEV_USER_ID

    def test_cf_jwt_without_email_rejected(self, client):
        """Test CF JWT present but no email extractable returns 401."""
        payload = {"sub": "user123"}
        token = jwt.encode(payload, "secret", algorithm="HS256")
        headers = {"CF-Access-JWT-Assertion": token}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401
        assert "unable to extract email" in response.json()["detail"].lower()


# ============================================================================
# Test: Malformed JWT handling
# ============================================================================

class TestMalformedJWT:
    """Tests for malformed JWT handling."""

    def test_malformed_jwt_returns_401(self, client):
        """Test malformed JWT returns 401."""
        headers = {"CF-Access-JWT-Assertion": "not.a.valid.jwt.token"}

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 401

    def test_malformed_jwt_with_email_header_fallback(self, client):
        """Test malformed JWT falls back to email header."""
        headers = {
            "CF-Access-JWT-Assertion": "not.valid.jwt",
            "CF-Access-Authenticated-User-Email": TEST_EMAIL
        }

        response = client.get("/api/conversations", headers=headers)

        assert response.status_code == 200
        assert response.json()["user_id"] == TEST_USER_ID


# ============================================================================
# Test: Bypass paths
# ============================================================================

class TestBypassPaths:
    """Tests for authentication bypass paths."""

    def test_health_endpoint_no_auth_required(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_full_endpoint_no_auth_required(self, client):
        response = client.get("/health/full")
        assert response.status_code == 200

    def test_root_endpoint_no_auth_required(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_static_assets_no_auth_required(self, client):
        response = client.get("/assets/style.css")
        assert response.status_code == 200


# ============================================================================
# Test: Telegram flow compatibility
# ============================================================================

class TestTelegramCompatibility:
    """Tests for backward compatibility with Telegram bot flow."""

    def test_telegram_requests_pass_through(self, client):
        """Test Telegram bot requests (no CF headers) pass through unchanged."""
        response = client.get("/api/chat")
        assert response.status_code == 200
        assert response.json()["user_id"] is None

    def test_mixed_environment_works(self, client):
        """Test both web (with CF) and Telegram (without CF) flows work."""
        token = create_test_jwt(TEST_EMAIL)
        web_response = client.get(
            "/api/conversations",
            headers={"CF-Access-JWT-Assertion": token}
        )
        assert web_response.status_code == 200
        assert web_response.json()["user_id"] == TEST_USER_ID

        telegram_response = client.get("/api/chat")
        assert telegram_response.status_code == 200
        assert telegram_response.json()["user_id"] is None


# ============================================================================
# Test: User mapping configuration
# ============================================================================

class TestUserMapping:
    """Tests for USER_MAPPING configuration."""

    def test_user_mapping_contains_expected_user(self, auth_module):
        """Test USER_MAPPING has the configured test user."""
        assert TEST_EMAIL in auth_module.USER_MAPPING
        assert auth_module.USER_MAPPING[TEST_EMAIL] == TEST_USER_ID

    def test_bypass_paths_includes_expected_paths(self, auth_module):
        assert "/health" in auth_module.BYPASS_PATHS
        assert "/health/full" in auth_module.BYPASS_PATHS
        assert "/" in auth_module.BYPASS_PATHS
        assert "/assets" in auth_module.BYPASS_PATHS


# ============================================================================
# Test: Audit logging
# ============================================================================

class TestAuditLogging:
    """Tests for authentication audit logging."""

    @patch("api.middleware.cloudflare_auth.logger")
    def test_successful_auth_logged(self, mock_logger, client):
        """Test successful auth logs email, user_id, path."""
        token = create_test_jwt(TEST_EMAIL)
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        info_calls = [call for call in mock_logger.info.call_args_list]
        assert len(info_calls) > 0

        success_log = None
        for call in info_calls:
            if "CF auth success" in str(call):
                success_log = call
                break

        assert success_log is not None
        extra = success_log.kwargs.get("extra", {})
        assert extra.get("event") == "cf_auth_success"
        assert extra.get("email") == TEST_EMAIL
        assert extra.get("user_id") == TEST_USER_ID
        assert "/api/conversations" in extra.get("path", "")

    @patch("api.middleware.cloudflare_auth.logger")
    def test_failed_auth_logged(self, mock_logger, client):
        """Test failed auth logs reason."""
        token = create_test_jwt("unknown@example.com")
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        warning_calls = [call for call in mock_logger.warning.call_args_list]
        assert len(warning_calls) > 0

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
        """Test unknown email attempts logged for security monitoring."""
        token = create_test_jwt("attacker@malicious.com")
        headers = {"CF-Access-JWT-Assertion": token}

        client.get("/api/conversations", headers=headers)

        warning_calls = mock_logger.warning.call_args_list
        unknown_email_logged = any(
            "cf_auth_unknown_email" in str(call.kwargs.get("extra", {}))
            for call in warning_calls
        )
        assert unknown_email_logged
