"""
Browser Automation Tool

Provides an MCP tool for controlling a headless browser via the
Annie Browser Service (Playwright + Chromium).

Supports sequential actions: navigate, click, type, screenshot,
content extraction, JavaScript evaluation, and wait.
"""

import asyncio
import random
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from mcp_server.logging import get_logger

logger = get_logger(__name__)

# Default browser service URL (overridable via env)
_BROWSER_SERVICE_URL: Optional[str] = None


def _extract_domain(url: str) -> Optional[str]:
    """Extract the normalized hostname from a URL (strips www. prefix).

    'https://www.reddit.com/r/foo' → 'reddit.com'
    'https://mail.google.com'      → 'mail.google.com'
    """
    try:
        hostname = urlparse(url).hostname
        return hostname.removeprefix("www.") if hostname else None
    except Exception:
        return None


def _get_browser_url() -> str:
    """Resolve the browser service URL from config / env."""
    global _BROWSER_SERVICE_URL
    if _BROWSER_SERVICE_URL is None:
        import os
        _BROWSER_SERVICE_URL = os.getenv("BROWSER_SERVICE_URL", "http://browser:8003")
    return _BROWSER_SERVICE_URL


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

async def _execute_action(
    client: httpx.AsyncClient,
    session_id: str,
    action: Dict[str, Any],
    request_id: str,
) -> Dict[str, Any]:
    """Execute a single browser action and return the result dict."""
    base = _get_browser_url()
    action_type = action.get("type")
    timeout_ms = action.get("timeout_ms", 5000)

    try:
        if action_type == "navigate":
            url = action.get("url", "")
            resp = await client.post(
                f"{base}/sessions/{session_id}/navigate",
                json={"url": url, "timeout_ms": timeout_ms},
                timeout=max(timeout_ms / 1000 + 5, 15),
            )

        elif action_type == "click":
            selector = action.get("selector", "")
            resp = await client.post(
                f"{base}/sessions/{session_id}/click",
                json={"selector": selector, "timeout_ms": timeout_ms},
                timeout=max(timeout_ms / 1000 + 5, 10),
            )

        elif action_type == "type":
            selector = action.get("selector", "")
            text = action.get("text", "")
            resp = await client.post(
                f"{base}/sessions/{session_id}/type",
                json={"selector": selector, "text": text, "timeout_ms": timeout_ms},
                timeout=max(timeout_ms / 1000 + 5, 10),
            )

        elif action_type == "screenshot":
            resp = await client.post(
                f"{base}/sessions/{session_id}/screenshot",
                json={},
                timeout=15,
            )

        elif action_type == "content":
            resp = await client.post(
                f"{base}/sessions/{session_id}/content",
                timeout=15,
            )

        elif action_type == "evaluate":
            expression = action.get("expression", "")
            resp = await client.post(
                f"{base}/sessions/{session_id}/evaluate",
                json={"expression": expression, "timeout_ms": timeout_ms},
                timeout=max(timeout_ms / 1000 + 5, 10),
            )

        elif action_type == "go_back":
            resp = await client.post(
                f"{base}/sessions/{session_id}/go_back",
                timeout=15,
            )

        elif action_type == "wait":
            wait_ms = timeout_ms
            await asyncio.sleep(wait_ms / 1000)
            return {"action": "wait", "status": "success", "waited_ms": wait_ms}

        elif action_type == "close_session":
            resp = await client.delete(
                f"{base}/sessions/{session_id}",
                timeout=10,
            )
            return {"action": "close_session", "status": "success"}

        else:
            return {"action": action_type, "status": "error", "error": f"Unknown action type: {action_type}"}

        # Parse response
        data = resp.json()
        return {"action": action_type, **data}

    except httpx.TimeoutException:
        return {"action": action_type, "status": "error", "error": f"Timeout after {timeout_ms}ms"}
    except httpx.HTTPError as exc:
        return {"action": action_type, "status": "error", "error": f"HTTP error: {str(exc)}"}
    except Exception as exc:
        return {"action": action_type, "status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

async def browser_action_handler(
    actions: List[Dict[str, Any]],
    profile: str = "default",
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    keep_session: bool = True,
) -> Dict[str, Any]:
    """
    Execute a sequence of browser actions.

    If session_id is provided, reuses an existing browser session.
    Otherwise, creates a new session and closes it after all actions complete
    (unless keep_session=True, in which case the session stays alive for reuse).

    Args:
        actions: List of action dicts, each with at minimum a "type" key.
        profile: Chrome profile name for persistent sessions (default: "default").
        session_id: Optional existing session ID to reuse.
        user_id: Optional user ID for per-user profile isolation (auto-injected).
        keep_session: If True, session is kept alive after actions complete.

    Returns:
        Dict with status, session_id, and results array.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    base = _get_browser_url()
    created_session = False

    # Always derive profile from user_id — 1 context per user, no overrides
    if user_id:
        profile = f"user_{user_id}"

    logger.info(
        f"browser_action called with {len(actions)} action(s)",
        extra={
            "request_id": request_id,
            "profile": profile,
            "session_id": session_id,
            "action_count": len(actions),
        },
    )

    async with httpx.AsyncClient() as client:
        # ---- Create or reuse session (domain-aware) --------------------------
        if not session_id:
            # Determine the target domain from the first navigate action (if any)
            target_domain = None
            for act in actions:
                if act.get("type") == "navigate" and act.get("url"):
                    target_domain = _extract_domain(act["url"])
                    break

            try:
                list_resp = await client.get(f"{base}/sessions", timeout=5)
                if list_resp.status_code == 200:
                    list_data = list_resp.json()
                    existing = list_data.get("data", {}).get("sessions", [])
                    # Filter to this user's profile
                    profile_sessions = [s for s in existing if s.get("profile") == profile]

                    if target_domain and profile_sessions:
                        # Look for an existing tab on the same domain
                        for sess in profile_sessions:
                            if sess.get("domain") == target_domain:
                                session_id = sess["session_id"]
                                logger.info(
                                    f"Reusing session {session_id} (domain={target_domain})",
                                    extra={
                                        "request_id": request_id,
                                        "session_id": session_id,
                                        "idle_seconds": sess.get("idle_seconds"),
                                    },
                                )
                                break
                    elif not target_domain and profile_sessions:
                        # No navigate action (e.g. just screenshot/content) —
                        # pick the most recently used session (lowest idle_seconds)
                        mru = min(profile_sessions, key=lambda s: s.get("idle_seconds", 0))
                        session_id = mru["session_id"]
                        logger.info(
                            f"Reusing MRU session {session_id} (no navigate action)",
                            extra={
                                "request_id": request_id,
                                "session_id": session_id,
                                "idle_seconds": mru.get("idle_seconds"),
                            },
                        )
            except Exception as exc:
                logger.debug(
                    f"Could not list sessions for reuse check: {exc}",
                    extra={"request_id": request_id},
                )

        if not session_id:
            try:
                resp = await client.post(
                    f"{base}/sessions",
                    json={"profile": profile},
                    timeout=15,
                )
                resp_data = resp.json()
                if resp.status_code != 200 or resp_data.get("status") != "success":
                    error_msg = resp_data.get("error") or resp_data.get("detail") or "Failed to create session"
                    logger.error(
                        f"Failed to create browser session: {error_msg}",
                        extra={"request_id": request_id},
                    )
                    return {"status": "error", "error": error_msg, "results": []}
                session_id = resp_data["data"]["session_id"]
                created_session = True
                logger.info(
                    f"Created browser session {session_id}",
                    extra={"request_id": request_id, "session_id": session_id},
                )
            except Exception as exc:
                logger.error(
                    f"Browser service unreachable: {exc}",
                    extra={"request_id": request_id},
                )
                return {
                    "status": "error",
                    "error": f"Browser service unreachable: {str(exc)}",
                    "results": [],
                }

        # ---- Execute actions sequentially -----------------------------------
        results: List[Dict[str, Any]] = []
        for idx, action in enumerate(actions):
            # Human-like delay between actions to avoid "clicking too fast" detection.
            # Skip delay before the first action and before non-interactive actions.
            if idx > 0 and action.get("type") in ("navigate", "click", "type"):
                delay = random.uniform(0.4, 1.2)
                await asyncio.sleep(delay)

            action_result = await _execute_action(client, session_id, action, request_id)

            # Expired session retry: if session_id was provided (not created here)
            # and the first action fails with a "not found" error, create a new
            # session with the same profile and retry the failed action.
            # The browser service returns 404s as {"detail": "Session not found: ..."}
            error_text = (
                str(action_result.get("error", ""))
                + str(action_result.get("detail", ""))
            ).lower()
            if (
                not created_session
                and idx == 0
                and "not found" in error_text
            ):
                logger.info(
                    f"Session {session_id} expired, creating new session with profile {profile}",
                    extra={"request_id": request_id},
                )
                try:
                    resp = await client.post(
                        f"{base}/sessions",
                        json={"profile": profile},
                        timeout=15,
                    )
                    resp_data = resp.json()
                    if resp.status_code == 200 and resp_data.get("status") == "success":
                        session_id = resp_data["data"]["session_id"]
                        created_session = True
                        logger.info(
                            f"Recreated browser session {session_id} after expiry",
                            extra={"request_id": request_id, "session_id": session_id},
                        )
                        # Retry the failed action with new session
                        action_result = await _execute_action(client, session_id, action, request_id)
                except Exception as exc:
                    logger.error(
                        f"Failed to recreate session after expiry: {exc}",
                        extra={"request_id": request_id},
                    )

            results.append(action_result)

            # Stop on error unless it's a non-critical action
            if action_result.get("status") == "error":
                logger.warning(
                    f"Action {idx} ({action.get('type')}) failed: {action_result.get('error')}",
                    extra={"request_id": request_id, "session_id": session_id},
                )
                break

        # ---- Clean up -------------------------------------------------------
        if created_session and not keep_session:
            try:
                await client.delete(f"{base}/sessions/{session_id}", timeout=10)
                logger.info(
                    f"Closed browser session {session_id}",
                    extra={"request_id": request_id},
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to close session {session_id}: {exc}",
                    extra={"request_id": request_id},
                )
        elif created_session and keep_session:
            logger.info(
                f"Keeping browser session {session_id} alive (24-hour idle timeout)",
                extra={"request_id": request_id, "session_id": session_id},
            )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"browser_action completed in {duration_ms}ms",
        extra={
            "request_id": request_id,
            "session_id": session_id,
            "duration_ms": duration_ms,
            "action_count": len(actions),
            "results_count": len(results),
        },
    )

    return {
        "status": "success",
        "session_id": session_id,
        "results": results,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Tool definition (MCP registry format)
# ---------------------------------------------------------------------------

browser_action_tool = {
    "name": "browser_action",
    "description": (
        "Full browser control — navigate, read, click, type, screenshot, run JavaScript. "
        "Each site gets its own tab (domain-based): navigating to reddit.com reuses the Reddit tab, "
        "gmail.com reuses the Gmail tab, etc. Tabs auto-expire after 24 hours idle; at capacity the "
        "least recently used tab is evicted. "
        "IMPORTANT: If the user asks about a site that's already open, send a screenshot first to see "
        "the current state before navigating again. "
        "Use for anything the other web tools can't handle: interacting with pages, logging in, "
        "filling forms, sites that block scrapers, JavaScript-heavy apps, or when you're unsure which tool to use. "
        "Supports persistent login sessions via Chrome profiles so authenticated sites stay logged in. "
        "Prefer web_search to find URLs and web_crawl to read simple pages, but use this tool freely when in doubt."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "description": "List of browser actions to execute sequentially",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "navigate",
                                "click",
                                "type",
                                "screenshot",
                                "content",
                                "wait",
                                "evaluate",
                                "go_back",
                                "close_session",
                            ],
                            "description": "Action type",
                        },
                        "url": {
                            "type": "string",
                            "description": "URL for navigate action",
                        },
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for click/type actions",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text for type action",
                        },
                        "expression": {
                            "type": "string",
                            "description": "JavaScript for evaluate action",
                        },
                        "timeout_ms": {
                            "type": "integer",
                            "default": 5000,
                            "description": "Action timeout in ms",
                        },
                    },
                    "required": ["type"],
                },
            },
            "profile": {
                "type": "string",
                "default": "default",
                "description": "Chrome profile name for persistent sessions",
            },
            "session_id": {
                "type": "string",
                "description": "Reuse existing browser session (optional)",
            },
            "user_id": {
                "type": "string",
                "description": "User ID for per-user profile isolation (auto-injected by system)",
            },
            "keep_session": {
                "type": "boolean",
                "default": True,
                "description": "Keep session alive after actions complete (default: true). Set false to close immediately.",
            },
        },
        "required": ["actions"],
    },
    "handler": browser_action_handler,
}
