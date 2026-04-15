"""
Browser Automation Service

FastAPI wrapper around patchright (anti-detect Playwright fork) driving
headful Chromium inside Xvfb.  Each user profile gets its own persistent
user-data-dir (cookies, localStorage, IndexedDB, service workers — the whole
browser profile) so authenticated sessions survive restarts and can be
bootstrapped by a human via the noVNC sidecar.
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
from patchright.async_api import async_playwright, BrowserContext, Page

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
BROWSER_ALLOWED_DOMAINS = os.getenv("BROWSER_ALLOWED_DOMAINS", "")
PROFILES_DIR = "/data/profiles"
MAX_SESSIONS = 10
SESSION_TIMEOUT_SECONDS = int(os.getenv("BROWSER_SESSION_TIMEOUT", "86400"))  # 24h
CLEANUP_INTERVAL_SECONDS = 60

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
    raw = BROWSER_ALLOWED_DOMAINS.strip()
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _is_url_allowed(url: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    from urllib.parse import urlparse

    hostname = (urlparse(url).hostname or "").lower()
    for domain in allowed:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class SessionInfo:
    """One tab inside a per-profile persistent context."""

    def __init__(self, session_id: str, page: Page, context: BrowserContext, profile: str):
        self.session_id = session_id
        self.page = page
        self.context = context
        self.profile = profile
        self.last_activity = time.time()
        self.primary_domain: Optional[str] = None

    def touch(self):
        self.last_activity = time.time()


class BrowserManager:
    """Manages one persistent Chromium context per user profile.

    Hierarchy (patchright / Playwright persistent mode):
        BrowserContext  (1 per profile — IS the browser instance; owns cookies,
                         localStorage, IndexedDB, service workers, extensions,
                         everything persisted on disk under user-data-dir)
         └─ Page        (1 per session; a tab inside that context)

    Unlike the old `launch() + new_context()` flow, persistent_context has no
    separate Browser object — the context itself owns the Chromium process.
    Closing the context closes Chromium for that profile; closing a page
    just closes the tab.
    """

    def __init__(self):
        self._playwright = None
        self._contexts: Dict[str, BrowserContext] = {}  # profile -> persistent context
        self._sessions: Dict[str, SessionInfo] = {}
        self._allowed_domains = _parse_allowed_domains()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ctx_lock = asyncio.Lock()

    # -- lifecycle -----------------------------------------------------------

    async def start(self):
        self._playwright = await async_playwright().start()
        logger.info("Patchright started (contexts launched lazily per profile)")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all pages first (best-effort), then contexts. Persistence is
        # automatic — everything's already on disk in the user-data-dir.
        for sid in list(self._sessions):
            info = self._sessions.pop(sid, None)
            if info:
                try:
                    await info.page.close()
                except Exception:
                    pass

        for profile, ctx in list(self._contexts.items()):
            try:
                await ctx.close()
                logger.info(f"Closed persistent context for profile '{profile}'")
            except Exception as exc:
                logger.warning(f"Error closing context '{profile}': {exc}")

        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser manager stopped")

    # -- context (per profile) -----------------------------------------------

    async def _get_context(self, profile: str) -> BrowserContext:
        """Get or lazily launch the persistent context for a profile."""
        if profile in self._contexts:
            return self._contexts[profile]

        async with self._ctx_lock:
            # Re-check after acquiring the lock
            if profile in self._contexts:
                return self._contexts[profile]

            user_data_dir = os.path.join(PROFILES_DIR, profile, "udd")
            os.makedirs(user_data_dir, exist_ok=True)

            # Headful — required for patchright's fingerprint patches to be
            # effective against serious anti-bot and for noVNC to show the
            # actual page to the user. Xvfb provides DISPLAY=:99.
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    # Keep the window big enough to look natural on VNC
                    "--window-size=1280,800",
                ],
            )

            self._contexts[profile] = context
            logger.info(f"Launched persistent context for profile '{profile}' (udd={user_data_dir})")
            return context

    # -- sessions ------------------------------------------------------------

    async def create_session(self, profile: str = "default") -> str:
        """Open a new tab inside the profile's persistent context.

        LRU-evicts an older session if MAX_SESSIONS is reached.
        """
        if len(self._sessions) >= MAX_SESSIONS:
            lru_sid = min(self._sessions, key=lambda s: self._sessions[s].last_activity)
            lru_info = self._sessions[lru_sid]
            logger.info(
                f"LRU eviction: closing session {lru_sid} "
                f"(profile={lru_info.profile}, idle {int(time.time() - lru_info.last_activity)}s)"
            )
            await self.close_session(lru_sid)

        ctx = await self._get_context(profile)
        page = await ctx.new_page()
        session_id = str(uuid.uuid4())[:12]
        self._sessions[session_id] = SessionInfo(session_id, page, ctx, profile)
        logger.info(f"Session created: {session_id} (profile={profile})")
        return session_id

    def get_session(self, session_id: str) -> SessionInfo:
        info = self._sessions.get(session_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        info.touch()
        return info

    async def close_session(self, session_id: str):
        """Close a tab. Persistent context (and its data) remains on disk."""
        info = self._sessions.pop(session_id, None)
        if not info:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        try:
            await info.page.close()
        except Exception:
            pass
        logger.info(f"Session closed: {session_id} (context for '{info.profile}' kept alive)")

    @staticmethod
    def _normalize_domain(hostname: Optional[str]) -> Optional[str]:
        if hostname:
            return hostname.removeprefix("www.")
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        from urllib.parse import urlparse

        result = []
        now = time.time()
        for sid, info in self._sessions.items():
            page_url = info.page.url if info.page else None
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
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            now = time.time()
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
        if not _is_url_allowed(url, self._allowed_domains):
            raise HTTPException(
                status_code=403,
                detail=f"Domain not allowed. Allowed domains: {', '.join(self._allowed_domains)}",
            )


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Annie Browser Service", version="2.0.0")
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
            "active_profiles": list(manager._contexts.keys()),
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
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


@app.post("/sessions/{session_id}/go_back")
async def go_back(session_id: str):
    info = manager.get_session(session_id)
    try:
        await info.page.go_back(wait_until="commit", timeout=10000)
        title = await info.page.title()
        return JSONResponse(
            content={
                "status": "success",
                "data": {"url": info.page.url, "title": title},
            }
        )
    except Exception as exc:
        logger.error(f"Go back error (session={session_id}): {exc}")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


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
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


@app.post("/sessions/{session_id}/type")
async def type_text(session_id: str, req: TypeRequest):
    info = manager.get_session(session_id)
    try:
        # press_sequentially dispatches real keydown/keyup events so forms
        # that enable their submit button on input listeners actually see
        # the typing — unlike page.fill() which just sets .value.
        await info.page.locator(req.selector).press_sequentially(
            req.text, delay=60, timeout=req.timeout_ms
        )
        return JSONResponse(
            content={
                "status": "success",
                "data": {"selector": req.selector, "text_length": len(req.text)},
            }
        )
    except Exception as exc:
        logger.error(f"Type error (session={session_id}): {exc}")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


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
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


@app.post("/sessions/{session_id}/content")
async def content(session_id: str):
    info = manager.get_session(session_id)
    try:
        title = await info.page.title()
        text = await info.page.evaluate(
            """() => {
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
                    "text": text[:50000],
                },
            }
        )
    except Exception as exc:
        logger.error(f"Content error (session={session_id}): {exc}")
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})


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
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc)})
