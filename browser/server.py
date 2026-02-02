"""
Browser Automation Service

A FastAPI service wrapping Playwright + Chromium for headless browser automation.
Provides session-based browser control with persistent cookie profiles.
"""

import asyncio
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
BROWSER_ALLOWED_DOMAINS = os.getenv("BROWSER_ALLOWED_DOMAINS", "")
PROFILES_DIR = "/data/profiles"
MAX_SESSIONS = 10
SESSION_TIMEOUT_SECONDS = int(os.getenv("BROWSER_SESSION_TIMEOUT", "86400"))  # 24 hours
CLEANUP_INTERVAL_SECONDS = 60
CONTEXT_SAVE_INTERVAL_SECONDS = 300  # save all context state to disk every 5 minutes

_PACIFIC_TZ = pytz.timezone("America/Los_Angeles")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)-8s] [browser] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("browser")

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    profile: str = Field(default="default", description="Chrome profile name")


class NavigateRequest(BaseModel):
    url: str
    timeout_ms: int = Field(default=30000, ge=1000, le=60000)


class ClickRequest(BaseModel):
    selector: str
    timeout_ms: int = Field(default=5000, ge=500, le=30000)


class TypeRequest(BaseModel):
    selector: str
    text: str
    timeout_ms: int = Field(default=5000, ge=500, le=30000)


class ScreenshotRequest(BaseModel):
    full_page: bool = False


class EvaluateRequest(BaseModel):
    expression: str
    timeout_ms: int = Field(default=5000, ge=500, le=30000)


# ---------------------------------------------------------------------------
# Domain Allowlist
# ---------------------------------------------------------------------------


def _parse_allowed_domains() -> List[str]:
    """Parse BROWSER_ALLOWED_DOMAINS env var into list."""
    raw = BROWSER_ALLOWED_DOMAINS.strip()
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _is_url_allowed(url: str, allowed: List[str]) -> bool:
    """Check whether a URL's domain is in the allowlist (empty = allow all)."""
    if not allowed:
        return True
    from urllib.parse import urlparse

    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()
    for domain in allowed:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class SessionInfo:
    """Tracks a single browser session (one page inside a shared context)."""

    def __init__(self, session_id: str, page: Page, context: BrowserContext, profile: str):
        self.session_id = session_id
        self.page = page
        self.context = context
        self.profile = profile
        self.last_activity = time.time()
        self.primary_domain: Optional[str] = None  # set on explicit navigate

    def touch(self):
        self.last_activity = time.time()


class BrowserManager:
    """Manages Playwright browser lifecycle, contexts and sessions.

    Hierarchy:
        Browser  (1 Chromium process)
         └─ Context  (1 per user — holds cookies, localStorage, login state)
              └─ Session  (1 tab/page inside the user's context)

    Contexts are keyed by profile name (derived from user_id upstream).
    Each user gets exactly one context; sessions (tabs) are created inside it.
    Closing a session saves cookies to disk but keeps the context alive.
    """

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._sessions: Dict[str, SessionInfo] = {}
        self._contexts: Dict[str, BrowserContext] = {}  # user profile -> context (1:1)
        self._allowed_domains = _parse_allowed_domains()
        self._cleanup_task: Optional[asyncio.Task] = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self):
        """Launch Playwright and Chromium."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        logger.info("Playwright Chromium launched")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Shut down: save all context state to disk, then release resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Save every context to disk first (including ones with no active sessions)
        for profile in list(self._contexts):
            await self._save_context_state(profile)
            logger.info(f"Saved context state for profile '{profile}' before shutdown")

        for sid in list(self._sessions):
            try:
                info = self._sessions.pop(sid, None)
                if info:
                    await info.page.close()
            except Exception:
                pass

        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser manager stopped")

    # -- context (per profile) -----------------------------------------------

    async def _get_context(self, profile: str) -> BrowserContext:
        """Get or create a persistent browser context for a user profile.

        Contexts are never deleted during normal operation — only their state
        is periodically flushed to disk.  On restart the context is recreated
        from the stored ``storage_state.json``.
        """
        if profile in self._contexts:
            return self._contexts[profile]

        storage_path = os.path.join(PROFILES_DIR, profile, "storage_state.json")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        ctx_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        }

        # Restore cookies / local storage if a previous state exists
        if os.path.isfile(storage_path):
            ctx_kwargs["storage_state"] = storage_path

        context = await self._browser.new_context(**ctx_kwargs)

        # Mask automation signals so sites don't detect headless browser
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        self._contexts[profile] = context
        logger.info(f"Created browser context for profile '{profile}'")
        return context

    async def _save_context_state(self, profile: str):
        """Persist cookies / local storage for a profile."""
        ctx = self._contexts.get(profile)
        if not ctx:
            return
        storage_path = os.path.join(PROFILES_DIR, profile, "storage_state.json")
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        try:
            await ctx.storage_state(path=storage_path)
        except Exception as exc:
            logger.warning(f"Failed to save storage state for profile '{profile}': {exc}")

    # -- sessions ------------------------------------------------------------

    async def create_session(self, profile: str = "default") -> str:
        """Create a new browser session (page).

        If MAX_SESSIONS is reached, the least-recently-used session is evicted
        to make room (LRU eviction) instead of returning a 429 error.
        """
        if len(self._sessions) >= MAX_SESSIONS:
            # LRU eviction: close the session with the oldest last_activity
            lru_sid = min(self._sessions, key=lambda s: self._sessions[s].last_activity)
            lru_info = self._sessions[lru_sid]
            logger.info(
                f"LRU eviction: closing session {lru_sid} "
                f"(profile={lru_info.profile}, idle {int(time.time() - lru_info.last_activity)}s) "
                f"to make room for new session"
            )
            await self.close_session(lru_sid)

        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        session_id = str(uuid.uuid4())[:12]
        self._sessions[session_id] = SessionInfo(session_id, page, ctx, profile)
        logger.info(f"Session created: {session_id} (profile={profile})")
        return session_id

    def get_session(self, session_id: str) -> SessionInfo:
        """Retrieve session or raise 404."""
        info = self._sessions.get(session_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        info.touch()
        return info

    async def close_session(self, session_id: str):
        """Close a session (tab) and persist context state.

        The context itself is *never* removed — only the page is closed.
        Cookies and localStorage remain in-memory and on disk for the next
        session created under the same profile.
        """
        info = self._sessions.pop(session_id, None)
        if not info:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        try:
            await info.page.close()
        except Exception:
            pass
        await self._save_context_state(info.profile)
        logger.info(f"Session closed: {session_id} (context for '{info.profile}' kept alive)")

    @staticmethod
    def _normalize_domain(hostname: Optional[str]) -> Optional[str]:
        """Strip 'www.' prefix so reddit.com and www.reddit.com match."""
        if hostname:
            return hostname.removeprefix("www.")
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List active sessions with domain information."""
        from urllib.parse import urlparse

        result = []
        now = time.time()
        for sid, info in self._sessions.items():
            page_url = info.page.url if info.page else None
            # Prefer tracked primary_domain (stable across click navigation).
            # Fall back to current page URL for sessions that haven't navigated yet.
            domain = info.primary_domain
            if domain is None and page_url:
                hostname = urlparse(page_url).hostname
                domain = self._normalize_domain(hostname)
            result.append(
                {
                    "session_id": sid,
                    "profile": info.profile,
                    "url": page_url,
                    "domain": domain,
                    "idle_seconds": int(now - info.last_activity),
                }
            )
        return result

    # -- cleanup -------------------------------------------------------------

    async def _cleanup_loop(self):
        """Background loop: periodic context saves + idle session expiry."""
        last_context_save = time.time()
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            now = time.time()

            # -- Periodic context save (every CONTEXT_SAVE_INTERVAL_SECONDS) --
            if now - last_context_save >= CONTEXT_SAVE_INTERVAL_SECONDS:
                for profile in list(self._contexts):
                    await self._save_context_state(profile)
                logger.debug(f"Periodic context save: {len(self._contexts)} profile(s)")
                last_context_save = now

            # -- Expire idle sessions (tabs only, context stays) --------------
            expired = [
                sid
                for sid, info in self._sessions.items()
                if now - info.last_activity > SESSION_TIMEOUT_SECONDS
            ]
            for sid in expired:
                logger.info(f"Auto-closing idle session: {sid}")
                try:
                    await self.close_session(sid)
                except Exception as exc:
                    logger.warning(f"Error closing idle session {sid}: {exc}")

    # -- domain check --------------------------------------------------------

    def check_url(self, url: str):
        """Raise 403 if URL is not in the allowlist."""
        if not _is_url_allowed(url, self._allowed_domains):
            raise HTTPException(
                status_code=403,
                detail=f"Domain not allowed. Allowed domains: {', '.join(self._allowed_domains)}",
            )


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Annie Browser Service", version="1.0.0")
manager = BrowserManager()


@app.on_event("startup")
async def on_startup():
    await manager.start()


@app.on_event("shutdown")
async def on_shutdown():
    await manager.stop()


# -- health ------------------------------------------------------------------


@app.get("/health")
async def health():
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(_PACIFIC_TZ).isoformat(),
            "active_sessions": len(manager._sessions),
        }
    )


# -- session CRUD ------------------------------------------------------------


@app.post("/sessions")
async def create_session(req: CreateSessionRequest = None):
    if req is None:
        req = CreateSessionRequest()
    session_id = await manager.create_session(profile=req.profile)
    return JSONResponse(
        content={
            "status": "success",
            "data": {"session_id": session_id, "profile": req.profile},
        }
    )


@app.get("/sessions")
async def list_sessions():
    return JSONResponse(
        content={"status": "success", "data": {"sessions": manager.list_sessions()}}
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    await manager.close_session(session_id)
    return JSONResponse(content={"status": "success", "data": {"session_id": session_id}})


# -- actions -----------------------------------------------------------------


@app.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, req: NavigateRequest):
    from urllib.parse import urlparse

    manager.check_url(req.url)
    info = manager.get_session(session_id)
    try:
        await info.page.goto(req.url, timeout=req.timeout_ms, wait_until="domcontentloaded")
        # Update primary_domain on every explicit navigate so domain matching
        # stays accurate, while click-driven navigations leave it unchanged.
        hostname = urlparse(info.page.url).hostname
        info.primary_domain = manager._normalize_domain(hostname)
        title = await info.page.title()
        return JSONResponse(
            content={
                "status": "success",
                "data": {"url": info.page.url, "title": title},
            }
        )
    except Exception as exc:
        logger.error(f"Navigate error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/go_back")
async def go_back(session_id: str):
    info = manager.get_session(session_id)
    try:
        await info.page.go_back(wait_until="domcontentloaded")
        title = await info.page.title()
        return JSONResponse(
            content={
                "status": "success",
                "data": {"url": info.page.url, "title": title},
            }
        )
    except Exception as exc:
        logger.error(f"Go back error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/click")
async def click(session_id: str, req: ClickRequest):
    info = manager.get_session(session_id)
    try:
        await info.page.click(req.selector, timeout=req.timeout_ms)
        return JSONResponse(
            content={"status": "success", "data": {"selector": req.selector}}
        )
    except Exception as exc:
        logger.error(f"Click error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/type")
async def type_text(session_id: str, req: TypeRequest):
    info = manager.get_session(session_id)
    try:
        await info.page.fill(req.selector, req.text, timeout=req.timeout_ms)
        return JSONResponse(
            content={
                "status": "success",
                "data": {"selector": req.selector, "text_length": len(req.text)},
            }
        )
    except Exception as exc:
        logger.error(f"Type error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/screenshot")
async def screenshot(session_id: str, req: ScreenshotRequest = None):
    if req is None:
        req = ScreenshotRequest()
    info = manager.get_session(session_id)
    try:
        import base64

        raw = await info.page.screenshot(full_page=req.full_page)
        b64 = base64.b64encode(raw).decode("utf-8")
        viewport = info.page.viewport_size or {"width": 1280, "height": 720}
        return JSONResponse(
            content={
                "status": "success",
                "data": {
                    "base64": b64,
                    "width": viewport["width"],
                    "height": viewport["height"],
                },
            }
        )
    except Exception as exc:
        logger.error(f"Screenshot error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/content")
async def content(session_id: str):
    info = manager.get_session(session_id)
    try:
        title = await info.page.title()
        # Extract visible text content as simplified markdown
        text = await info.page.evaluate(
            """() => {
                // Remove script, style, noscript elements
                const clone = document.body.cloneNode(true);
                for (const el of clone.querySelectorAll('script, style, noscript, svg')) {
                    el.remove();
                }
                return clone.innerText || '';
            }"""
        )
        return JSONResponse(
            content={
                "status": "success",
                "data": {
                    "title": title,
                    "url": info.page.url,
                    "text": text[:50000],  # cap at 50k chars
                },
            }
        )
    except Exception as exc:
        logger.error(f"Content error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )


@app.post("/sessions/{session_id}/evaluate")
async def evaluate(session_id: str, req: EvaluateRequest):
    info = manager.get_session(session_id)
    try:
        result = await info.page.evaluate(req.expression)
        return JSONResponse(
            content={"status": "success", "data": {"result": result}}
        )
    except Exception as exc:
        logger.error(f"Evaluate error (session={session_id}): {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )
