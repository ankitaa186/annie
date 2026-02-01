"""
Cloudflare Access Authentication Middleware

Authenticates web users via Cloudflare Access JWT tokens.
Maps authenticated emails to Telegram user_ids for unified identity.

Authentication Flow:
1. Extract CF-Access-JWT-Assertion header
2. Decode JWT (without signature verification - Cloudflare already verified)
3. Extract email from JWT payload
4. Map email to user_id via USER_MAPPING
5. Attach user_id and email to request.state

Fallback: If JWT fails, try CF-Access-Authenticated-User-Email header.

Bypass paths: /health, /health/full, /, /assets/* skip authentication.

For Telegram bot requests (no CF headers), middleware passes through
to maintain backward compatibility.

DEV MODE: When ENVIRONMENT=dev, unauthenticated web requests get a default
user_id for local development. This is detected via missing CF headers AND
presence of typical web request headers (Accept, Origin, Referer).
"""

import os
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from api.logging import get_logger

logger = get_logger(__name__)

# Check if running in dev mode
IS_DEV_MODE = os.getenv("ENVIRONMENT", "dev").lower() == "dev"

# Default user_id for dev mode (same as the mapped user)
DEV_MODE_USER_ID = "YOUR_USER_ID"
DEV_MODE_EMAIL = "dev@localhost"

# Email to Telegram user_id mapping
# Format: "email1:user_id1,email2:user_id2"
_user_mapping_str = os.getenv("CF_USER_MAPPING", "user@example.com:YOUR_USER_ID")
USER_MAPPING = dict(
    pair.split(":", 1) for pair in _user_mapping_str.split(",") if ":" in pair
)

# Paths that bypass authentication (public endpoints)
BYPASS_PATHS = [
    "/health",
    "/health/full",
    "/",
    "/assets",
]


def should_bypass_auth(path: str) -> bool:
    """
    Check if path should bypass authentication.

    Args:
        path: Request URL path

    Returns:
        True if path is in bypass list or starts with a bypass prefix
    """
    # Exact match for specific paths
    if path in BYPASS_PATHS:
        return True

    # Prefix match for /health/* and /assets/*
    for bypass_path in BYPASS_PATHS:
        if path.startswith(f"{bypass_path}/"):
            return True

    return False


def extract_email_from_jwt(token: str) -> str | None:
    """
    Extract email from Cloudflare Access JWT token.

    Note: We do NOT verify the signature because Cloudflare has already
    verified it before forwarding the request to us.

    Args:
        token: JWT token string from CF-Access-JWT-Assertion header

    Returns:
        Email string if found, None otherwise
    """
    try:
        # Decode without signature verification
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        return payload.get("email")
    except jwt.DecodeError as e:
        logger.warning(
            "Failed to decode CF JWT",
            extra={
                "event": "cf_auth_jwt_decode_error",
                "error": str(e)
            }
        )
        return None
    except Exception as e:
        logger.warning(
            "Unexpected error decoding CF JWT",
            extra={
                "event": "cf_auth_jwt_error",
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return None


async def cloudflare_auth_middleware(request: Request, call_next):
    """
    Functional middleware for Cloudflare Access authentication.

    Used with @app.middleware("http") decorator.

    Args:
        request: FastAPI Request object
        call_next: Next middleware/handler in chain

    Returns:
        Response from next handler or 401 JSONResponse
    """
    path = request.url.path

    # Bypass authentication for public paths
    if should_bypass_auth(path):
        return await call_next(request)

    # Check for Cloudflare Access headers
    cf_jwt = request.headers.get("CF-Access-JWT-Assertion")
    cf_email_header = request.headers.get("CF-Access-Authenticated-User-Email")

    # If NO Cloudflare headers present, check if this is a web request in dev mode
    if not cf_jwt and not cf_email_header:
        # Check if this looks like a web browser request
        is_web_request = (
            request.headers.get("Accept", "").startswith("application/json") or
            request.headers.get("Origin") is not None or
            request.headers.get("Referer") is not None or
            "Mozilla" in request.headers.get("User-Agent", "")
        )

        # In dev mode, auto-authenticate web requests
        if IS_DEV_MODE and is_web_request:
            request.state.user_id = DEV_MODE_USER_ID
            request.state.email = DEV_MODE_EMAIL
            logger.debug(
                "Dev mode auth: auto-authenticated web request",
                extra={
                    "event": "dev_mode_auth",
                    "user_id": DEV_MODE_USER_ID,
                    "path": path
                }
            )
            return await call_next(request)

        # Otherwise, this is likely a Telegram bot request or internal service call
        # Pass through (backward compatibility)
        return await call_next(request)

    # Web flow: Cloudflare headers present, must authenticate
    email = None
    auth_method = None

    # Try JWT first (preferred)
    if cf_jwt:
        email = extract_email_from_jwt(cf_jwt)
        if email:
            auth_method = "jwt"

    # Fallback to email header
    if not email and cf_email_header:
        email = cf_email_header
        auth_method = "email_header"

    # No email extracted - reject
    if not email:
        logger.warning(
            "CF auth failed: no email extracted",
            extra={
                "event": "cf_auth_failed",
                "reason": "no_email",
                "path": path,
                "has_jwt": bool(cf_jwt),
                "has_email_header": bool(cf_email_header)
            }
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: Unable to extract email from Cloudflare headers"}
        )

    # Map email to user_id
    user_id = USER_MAPPING.get(email)

    if not user_id:
        # Unknown email - reject with security log
        logger.warning(
            "CF auth failed: unknown email",
            extra={
                "event": "cf_auth_unknown_email",
                "email": email,
                "path": path,
                "auth_method": auth_method
            }
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: Email not registered"}
        )

    # Successful authentication - attach to request state
    request.state.user_id = user_id
    request.state.email = email

    # Audit log for successful auth
    logger.info(
        "CF auth success",
        extra={
            "event": "cf_auth_success",
            "email": email,
            "user_id": user_id,
            "path": path,
            "auth_method": auth_method
        }
    )

    return await call_next(request)
