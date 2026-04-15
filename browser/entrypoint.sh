#!/usr/bin/env bash
# Browser service entrypoint.
#
# Starts a virtual display (Xvfb) so Chromium can run HEADFUL (required for
# patchright's anti-detect to work against hostile sites, and for the VNC
# sidecar to show anything). Exposes the display via x11vnc → websockify
# so a human can connect through noVNC and perform first-time logins / 2FA
# in the same browser profile Annie uses.
#
# Services:
#   Xvfb       :99           (virtual X display, 1280x800x24)
#   x11vnc     :5900         (VNC server bound to :99, localhost-only)
#   websockify 6080 → 5900   (noVNC HTTP/WS gateway)
#   uvicorn    :8003         (FastAPI browser control API)

set -euo pipefail

export DISPLAY=:99
DISPLAY_GEOMETRY="${BROWSER_DISPLAY_GEOMETRY:-1280x800x24}"
VNC_PASSWORD="${BROWSER_VNC_PASSWORD:-annie}"
NOVNC_DIR="/usr/share/novnc"

# --- Clean stale state -------------------------------------------------------
# If the previous container was SIGKILLed (common on docker restart), Xvfb's
# lock files survive and make Xvfb refuse to start with "Server is already
# active for display 99". Nothing else uses these files inside the container,
# so remove them unconditionally.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# Forward signals to children so a clean docker stop actually flushes state
# to the persistent user-data-dirs instead of hard-killing Chromium.
trap 'echo "[entrypoint] received SIGTERM, shutting down"; kill -TERM -$$; wait' TERM INT

# --- Xvfb --------------------------------------------------------------------
echo "[entrypoint] starting Xvfb on $DISPLAY ($DISPLAY_GEOMETRY)"
Xvfb "$DISPLAY" -screen 0 "$DISPLAY_GEOMETRY" -ac +extension GLX +render -noreset &
XVFB_PID=$!

# Wait for display to be ready
for i in $(seq 1 30); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

# --- x11vnc (bound to localhost; websockify bridges it outward) --------------
mkdir -p /root/.vnc
x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd >/dev/null

echo "[entrypoint] starting x11vnc on :5900 (localhost)"
x11vnc \
    -display "$DISPLAY" \
    -rfbport 5900 \
    -rfbauth /root/.vnc/passwd \
    -localhost \
    -forever \
    -shared \
    -quiet \
    -bg \
    -o /var/log/x11vnc.log

# --- websockify + noVNC ------------------------------------------------------
echo "[entrypoint] starting websockify 0.0.0.0:6080 → 127.0.0.1:5900 (noVNC at /)"
websockify --web="$NOVNC_DIR" 0.0.0.0:6080 127.0.0.1:5900 >/var/log/websockify.log 2>&1 &

# --- uvicorn (foreground; container lifecycle follows this) ------------------
echo "[entrypoint] starting uvicorn on :8003"
exec python -m uvicorn server:app --host 0.0.0.0 --port 8003
