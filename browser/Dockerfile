# Browser Service Dockerfile
# Headful Chromium (via Xvfb) + patchright anti-detect + noVNC for attended logins.
# Base image ships all Chromium system deps; we layer Xvfb/x11vnc/novnc on top.

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# --- System deps for display + VNC sidecar ----------------------------------
# - xvfb:        virtual X display so Chromium can run headful in a container
# - x11vnc:      VNC server bound to the Xvfb display
# - novnc:       HTML5 VNC client (static files served by websockify)
# - websockify:  WebSocket↔TCP bridge so a browser can speak to x11vnc
# - x11-utils:   provides xdpyinfo for the entrypoint readiness probe
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        x11-utils \
    && rm -rf /var/lib/apt/lists/*

# novnc ships vnc.html but not index.html; symlink so / serves the client
RUN ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# --- Python deps ------------------------------------------------------------
COPY requirements.txt .
# --ignore-installed works around a debian-packaged typing_extensions that
# ships without a RECORD file, which pip otherwise refuses to upgrade.
RUN pip install --no-cache-dir --ignore-installed -r requirements.txt

# Patchright uses its own patched Chromium download path. Fetch it now so the
# container starts instantly. --with-deps is already satisfied by the base
# image but is a cheap no-op if something's missing.
RUN patchright install chromium

# --- App code ---------------------------------------------------------------
COPY server.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Persistent user-data-dirs live here (one per profile)
RUN mkdir -p /data/profiles

# 8003 = FastAPI control API, 6080 = noVNC web client
EXPOSE 8003 6080

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8003/health'); assert r.status_code == 200" || exit 1

CMD ["./entrypoint.sh"]
