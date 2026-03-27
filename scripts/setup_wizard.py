#!/usr/bin/env python3
"""
Annie First-Boot Setup Wizard

Interactive setup that guides new users through the minimum configuration
needed to get Annie running. Handles:
  1. Prerequisites check (Docker, ports, disk)
  2. Interactive .env creation (only essential vars)
  3. agentic-memories detection and auto-deploy
  4. Optional enhancements (Langfuse, Brave Search, Home Assistant, etc.)
  5. Service launch and health verification
"""

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import questionary
from questionary import Style

# ── Paths ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / "env.example"

# ── Styles ─────────────────────────────────────────────────────────────

STYLE = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:green bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
        ("separator", "fg:yellow"),
        ("instruction", "fg:yellow"),
    ]
)

# ── Helpers ────────────────────────────────────────────────────────────

C_RED = "\033[0;31m"
C_GREEN = "\033[0;32m"
C_YELLOW = "\033[1;33m"
C_CYAN = "\033[0;36m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


def ok(msg: str):
    print(f"  {C_GREEN}✓{C_RESET} {msg}")


def warn(msg: str):
    print(f"  {C_YELLOW}⚠{C_RESET} {msg}")


def err(msg: str):
    print(f"  {C_RED}✗{C_RESET} {msg}")


def info(msg: str):
    print(f"  {C_DIM}{msg}{C_RESET}")


def header(title: str):
    print()
    print(f"{C_CYAN}{C_BOLD}── {title} ──{C_RESET}")
    print()


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def mask_key(key: str) -> str:
    if not key or key == "REPLACE_ME" or len(key) < 10:
        return "****"
    return key[:4] + "..." + key[-4:]


# ── Parse env.example to get all default values ───────────────────────

def parse_env_example() -> dict[str, str]:
    """Parse env.example into {KEY: default_value} preserving all keys."""
    result = {}
    if not ENV_EXAMPLE.exists():
        return result
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def parse_existing_env() -> dict[str, str]:
    """Parse existing .env file."""
    result = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def write_env(values: dict[str, str]):
    """Write .env using env.example as a template, substituting values."""
    if not ENV_EXAMPLE.exists():
        # Fallback: just dump key=value
        lines = [f"{k}={v}" for k, v in values.items()]
        ENV_FILE.write_text("\n".join(lines) + "\n")
        return

    template = ENV_EXAMPLE.read_text()
    output_lines = []
    for line in template.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                output_lines.append(f"{key}={values[key]}")
                continue
        output_lines.append(line)
    ENV_FILE.write_text("\n".join(output_lines) + "\n")


def is_placeholder(val: str | None) -> bool:
    return not val or val == "REPLACE_ME"


# ══════════════════════════════════════════════════════════════════════
# Phase 1: Prerequisites
# ══════════════════════════════════════════════════════════════════════

def check_prerequisites() -> dict:
    """Check system prerequisites, return status dict."""
    header("Phase 1: Checking Prerequisites")

    status = {"docker": False, "compose": False, "daemon": False, "git": False}
    warnings = []

    # Docker
    if shutil.which("docker"):
        r = run_cmd(["docker", "--version"])
        if r.returncode == 0:
            ver = re.search(r"(\d+\.\d+)", r.stdout)
            ver_str = ver.group(1) if ver else "unknown"
            ok(f"Docker {ver_str}")
            status["docker"] = True

            # Daemon running?
            r2 = run_cmd(["docker", "info"])
            if r2.returncode == 0:
                status["daemon"] = True
                ok("Docker daemon is running")
            else:
                warn("Docker daemon is NOT running — start Docker Desktop or the Docker service")
        else:
            warn("Docker found but version check failed")
    else:
        warn("Docker is not installed")
        info("Install from: https://docs.docker.com/get-docker/")
        info("Annie needs Docker to run its services (backend, MCP server, Redis, etc.)")

    # Docker Compose
    if status["docker"]:
        r = run_cmd(["docker", "compose", "version"])
        if r.returncode == 0:
            ver = re.search(r"v?(\d+\.\d+)", r.stdout)
            ok(f"Docker Compose {ver.group(1) if ver else 'v2'}")
            status["compose"] = True
        elif shutil.which("docker-compose"):
            ok("Docker Compose v1")
            status["compose"] = True
        else:
            warn("Docker Compose not found — included in Docker Desktop, or install separately")

    # Git
    if shutil.which("git"):
        ok("Git available")
        status["git"] = True
    else:
        warn("Git not found — needed only if auto-deploying agentic-memories")

    # Port conflicts (common ones)
    print()
    ports = {"Backend API": 8001, "MCP Server": 8002, "Redis": 6380}
    for name, port in ports.items():
        if port_in_use(port):
            warn(f"Port {port} ({name}) is already in use — may conflict")
        else:
            ok(f"Port {port} ({name}) is free")

    # Disk space
    usage = shutil.disk_usage(PROJECT_ROOT)
    free_gb = usage.free / (1024**3)
    if free_gb < 2:
        warn(f"Low disk space: {free_gb:.1f} GB free (Docker images need ~2 GB)")
    else:
        ok(f"{free_gb:.0f} GB free disk space")

    return status


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Essential .env Configuration
# ══════════════════════════════════════════════════════════════════════

def configure_essentials(existing: dict[str, str], defaults: dict[str, str]) -> dict[str, str]:
    """Interactive prompts for the minimum required variables."""
    header("Phase 2: Essential Configuration")

    values = {**defaults, **existing}  # existing overrides defaults

    print("  Only 4-5 values are needed to get Annie running.")
    print("  Everything else uses sensible defaults.")
    print()

    # ── 1. Telegram Bot Token ──
    current = values.get("TELEGRAM_BOT_TOKEN", "")
    if not is_placeholder(current):
        ok(f"Telegram Bot Token: {mask_key(current)}")
        if not questionary.confirm(
            "  Keep this token?", default=True, style=STYLE
        ).ask():
            current = ""

    if is_placeholder(current):
        print()
        info("Create a bot via https://t.me/BotFather and paste the token below.")
        token = questionary.text(
            "Telegram Bot Token:",
            style=STYLE,
            validate=lambda t: len(t) > 20 or "Token looks too short — check your BotFather message",
        ).ask()
        if token is None:
            sys.exit(1)
        values["TELEGRAM_BOT_TOKEN"] = token.strip()

    # ── 2. Authorized User IDs ──
    current = values.get("AUTHORIZED_USER_IDS", "")
    if not is_placeholder(current):
        ok(f"Authorized User IDs: {current}")
        if not questionary.confirm(
            "  Keep these IDs?", default=True, style=STYLE
        ).ask():
            current = ""

    if is_placeholder(current):
        print()
        info("Get your Telegram user ID from https://t.me/userinfobot")
        info("Comma-separate multiple IDs (e.g. 12345,67890)")
        user_ids = questionary.text(
            "Authorized Telegram User ID(s):",
            style=STYLE,
            validate=lambda v: bool(re.match(r"^\d+(,\d+)*$", v.strip())) or "Enter numeric IDs separated by commas",
        ).ask()
        if user_ids is None:
            sys.exit(1)
        values["AUTHORIZED_USER_IDS"] = user_ids.strip()

    # ── 3. LLM Model ──
    print()
    models = [
        {"name": "Grok-4 Fast (xAI) — recommended, fast + capable", "value": "grok-4-fast"},
        {"name": "GPT-5.2 (OpenAI) — large output capacity", "value": "gpt-5.2"},
        {"name": "Gemini 3.1 Pro (Google) — multimodal, context caching", "value": "gemini-3.1-pro-preview"},
    ]

    current_model = values.get("LLM_MODEL", "grok-4-fast")
    current_display = next((m["name"] for m in models if m["value"] == current_model), current_model)
    info(f"Current LLM model: {current_display}")

    model = questionary.select(
        "Primary LLM model:",
        choices=[questionary.Choice(m["name"], value=m["value"]) for m in models],
        default=current_model,
        style=STYLE,
    ).ask()
    if model is None:
        sys.exit(1)
    values["LLM_MODEL"] = model

    # ── 4. API key for chosen model ──
    key_map = {
        "grok-4-fast": ("XAI_API_KEY", "xAI", "https://x.ai/api"),
        "gpt-5.2": ("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys"),
        "gemini-3.1-pro-preview": ("GOOGLE_API_KEY", "Google AI", "https://aistudio.google.com/app/apikey"),
    }
    key_var, provider_name, key_url = key_map[model]
    current_key = values.get(key_var, "")

    if not is_placeholder(current_key):
        ok(f"{key_var}: {mask_key(current_key)}")
        if not questionary.confirm(
            f"  Keep this {provider_name} key?", default=True, style=STYLE
        ).ask():
            current_key = ""

    if is_placeholder(current_key):
        print()
        info(f"Get your API key from: {key_url}")
        api_key = questionary.text(
            f"{provider_name} API Key:",
            style=STYLE,
            validate=lambda k: len(k) > 10 or "Key looks too short",
        ).ask()
        if api_key is None:
            sys.exit(1)
        values[key_var] = api_key.strip()

    # ── 5. Admin User IDs (optional, quick prompt) ──
    current_admin = values.get("ADMIN_USER_IDS", "")
    if is_placeholder(current_admin):
        # Default admin = same as authorized user
        values["ADMIN_USER_IDS"] = values["AUTHORIZED_USER_IDS"]
        info(f"Admin User IDs defaulted to your authorized IDs: {values['ADMIN_USER_IDS']}")

    return values


# ══════════════════════════════════════════════════════════════════════
# Phase 3: agentic-memories Detection & Auto-Deploy
# ══════════════════════════════════════════════════════════════════════

def check_agentic_memories(values: dict[str, str], prereqs: dict) -> dict[str, str]:
    """Check if agentic-memories is reachable. Offer to deploy if not."""
    header("Phase 3: agentic-memories Service")

    am_url = values.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    # For local checks, translate host.docker.internal to localhost
    check_url = am_url.replace("host.docker.internal", "localhost")

    info(f"Checking {check_url}/health ...")
    print()

    try:
        resp = httpx.get(f"{check_url}/health", timeout=5)
        if resp.status_code == 200:
            ok(f"agentic-memories is running at {check_url}")
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            status = data.get("status", "ok")
            ok(f"Status: {status}")
            values["AGENTIC_MEMORIES_URL"] = am_url
            return values
    except Exception:
        pass

    warn("agentic-memories is NOT reachable")
    print()

    # Offer options
    action = questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("Auto-deploy agentic-memories (clone + docker compose up)", value="deploy"),
            questionary.Choice("I'll set it up myself later — skip for now", value="skip"),
            questionary.Choice("Enter a custom URL (it's running elsewhere)", value="custom"),
        ],
        style=STYLE,
    ).ask()

    if action is None:
        sys.exit(1)

    if action == "custom":
        custom_url = questionary.text(
            "agentic-memories URL:",
            default=am_url,
            style=STYLE,
        ).ask()
        if custom_url:
            values["AGENTIC_MEMORIES_URL"] = custom_url.strip()
        return values

    if action == "skip":
        warn("Skipping agentic-memories. Annie will start but memory features will be degraded.")
        info("You can set it up later and restart Annie.")
        return values

    # ── Auto-deploy ──
    if not prereqs.get("git"):
        err("Git is required to clone agentic-memories. Please install git and retry.")
        return values

    if not prereqs.get("docker") or not prereqs.get("daemon"):
        err("Docker must be installed and running to deploy agentic-memories.")
        return values

    # Determine install location
    default_path = str(Path.home() / "agentic-memories")
    am_path = questionary.text(
        "Install location for agentic-memories:",
        default=default_path,
        style=STYLE,
    ).ask()
    if am_path is None:
        sys.exit(1)
    am_path = Path(am_path).expanduser().resolve()

    # Clone if not present
    if not am_path.exists():
        print()
        info(f"Cloning agentic-memories to {am_path} ...")
        r = run_cmd(["git", "clone", "https://github.com/agentic-memories/agentic-memories.git", str(am_path)])
        if r.returncode != 0:
            err(f"Git clone failed: {r.stderr.strip()}")
            warn("You can clone it manually and run `make setup` again.")
            return values
        ok("Repository cloned")
    else:
        ok(f"agentic-memories repo exists at {am_path}")

    # Check for docker-compose / run_docker.sh
    compose_file = am_path / "docker-compose.yml"
    run_script = am_path / "run_docker.sh"

    if run_script.exists():
        info(f"Starting agentic-memories via {run_script} ...")
        print()
        info("This may take a few minutes on first run (building images)...")
        print()

        # Run in foreground so user sees output
        result = subprocess.run(
            ["bash", str(run_script)],
            cwd=str(am_path),
        )
        if result.returncode != 0:
            warn("agentic-memories startup may have had issues. Check its logs.")
    elif compose_file.exists():
        info("Starting agentic-memories via docker compose ...")
        print()

        # Check for .env in agentic-memories
        am_env = am_path / ".env"
        am_env_example = am_path / "env.example"
        if not am_env.exists() and am_env_example.exists():
            shutil.copy2(am_env_example, am_env)
            info("Created .env from env.example in agentic-memories")

        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=str(am_path),
        )
        if result.returncode != 0:
            warn("agentic-memories startup may have had issues.")
    else:
        warn(f"No docker-compose.yml or run_docker.sh found in {am_path}")
        info("You may need to set it up manually. Check the repo's README.")
        return values

    # Wait for health
    print()
    info("Waiting for agentic-memories to become healthy...")
    healthy = False
    for i in range(30):
        try:
            resp = httpx.get("http://localhost:8080/health", timeout=3)
            if resp.status_code == 200:
                healthy = True
                break
        except Exception:
            pass
        time.sleep(2)
        if (i + 1) % 5 == 0:
            info(f"  Still waiting... ({(i+1)*2}s)")

    if healthy:
        ok("agentic-memories is healthy!")
        values["AGENTIC_MEMORIES_URL"] = am_url
    else:
        warn("agentic-memories didn't become healthy within 60s")
        info("It may still be starting. Check with: curl http://localhost:8080/health")

    return values


# ══════════════════════════════════════════════════════════════════════
# Phase 4: Optional Enhancements
# ══════════════════════════════════════════════════════════════════════

def configure_optional(values: dict[str, str]) -> dict[str, str]:
    """Offer to configure optional services — each is skippable."""
    header("Phase 4: Optional Enhancements")

    print("  These are all optional. Press Enter to skip any of them.")
    print()

    # ── Langfuse (LLM Observability) ──
    if questionary.confirm(
        "Configure Langfuse (LLM tracing & observability)?",
        default=False,
        style=STYLE,
    ).ask():
        info("Get keys from: https://cloud.langfuse.com → Settings → API Keys")
        pub = questionary.text("Langfuse Public Key:", style=STYLE).ask()
        if pub and pub.strip():
            values["LANGFUSE_PUBLIC_KEY"] = pub.strip()
        sec = questionary.text("Langfuse Secret Key:", style=STYLE).ask()
        if sec and sec.strip():
            values["LANGFUSE_SECRET_KEY"] = sec.strip()
        ok("Langfuse configured")
    else:
        info("Skipped — Annie will run fine without tracing.")

    print()

    # ── Brave Search ──
    if questionary.confirm(
        "Configure Brave Search API (internet access tool)?",
        default=False,
        style=STYLE,
    ).ask():
        info("Get your key from: https://brave.com/search/api/")
        key = questionary.text("Brave Search API Key:", style=STYLE).ask()
        if key and key.strip():
            values["BRAVE_SEARCH_API_KEY"] = key.strip()
            ok("Brave Search configured")
    else:
        info("Skipped — web search will fall back to DuckDuckGo (free, no key).")

    print()

    # ── Tavily (Web Search) ──
    if questionary.confirm(
        "Configure Tavily (premium web search, 1000 free/month)?",
        default=False,
        style=STYLE,
    ).ask():
        info("Get your key from: https://tavily.com")
        key = questionary.text("Tavily API Key:", style=STYLE).ask()
        if key and key.strip():
            values["TAVILY_API_KEY"] = key.strip()
            ok("Tavily configured")
    else:
        info("Skipped — DuckDuckGo will be used as fallback.")

    print()

    # ── Home Assistant ──
    if questionary.confirm(
        "Configure Home Assistant integration (smart home)?",
        default=False,
        style=STYLE,
    ).ask():
        info("You need your HA URL and a Long-Lived Access Token")
        info("Generate token in HA: Profile → Security → Long-Lived Access Tokens")
        url = questionary.text(
            "Home Assistant URL:",
            default="http://homeassistant.local:8123",
            style=STYLE,
        ).ask()
        if url and url.strip():
            values["HA_URL"] = url.strip()
        token = questionary.text("HA Access Token:", style=STYLE).ask()
        if token and token.strip():
            values["HA_ACCESS_TOKEN"] = token.strip()
            ok("Home Assistant configured")
    else:
        info("Skipped — smart home features will be disabled.")

    # ── Additional LLM keys (fallback) ──
    print()
    primary_model = values.get("LLM_MODEL", "grok-4-fast")
    other_keys = {
        "grok-4-fast": [("OPENAI_API_KEY", "OpenAI"), ("GOOGLE_API_KEY", "Google AI")],
        "gpt-5.2": [("XAI_API_KEY", "xAI"), ("GOOGLE_API_KEY", "Google AI")],
        "gemini-3.1-pro-preview": [("XAI_API_KEY", "xAI"), ("OPENAI_API_KEY", "OpenAI")],
    }
    fallbacks = other_keys.get(primary_model, [])
    if fallbacks:
        if questionary.confirm(
            "Add fallback LLM API keys (for automatic failover)?",
            default=False,
            style=STYLE,
        ).ask():
            for key_var, provider in fallbacks:
                current = values.get(key_var, "")
                if not is_placeholder(current):
                    ok(f"{key_var}: {mask_key(current)} (already set)")
                    continue
                k = questionary.text(f"{provider} API Key (Enter to skip):", style=STYLE).ask()
                if k and k.strip():
                    values[key_var] = k.strip()
        else:
            info("Skipped — single-provider mode.")

    return values


# ══════════════════════════════════════════════════════════════════════
# Phase 5: Write .env and Launch
# ══════════════════════════════════════════════════════════════════════

def write_and_launch(values: dict[str, str], prereqs: dict):
    """Write .env, then optionally start services."""
    header("Phase 5: Writing Configuration")

    # Backup existing .env if present
    if ENV_FILE.exists():
        backup = ENV_FILE.with_suffix(".env.backup")
        shutil.copy2(ENV_FILE, backup)
        info(f"Backed up existing .env to {backup.name}")

    write_env(values)
    ok(f".env written ({ENV_FILE})")

    # Secure permissions
    ENV_FILE.chmod(0o600)
    ok("File permissions set to 600 (owner-only)")

    # Summary of what was configured
    print()
    print(f"  {C_BOLD}Configuration Summary:{C_RESET}")
    summary_keys = [
        "LLM_MODEL", "TELEGRAM_BOT_TOKEN", "AUTHORIZED_USER_IDS",
        "AGENTIC_MEMORIES_URL", "ENVIRONMENT",
    ]
    for key in summary_keys:
        val = values.get(key, "")
        if key in ("TELEGRAM_BOT_TOKEN",):
            val = mask_key(val)
        print(f"    {key} = {val}")

    # Count configured optional features
    optional_configured = []
    if not is_placeholder(values.get("LANGFUSE_PUBLIC_KEY", "")):
        optional_configured.append("Langfuse")
    if not is_placeholder(values.get("BRAVE_SEARCH_API_KEY", "")):
        optional_configured.append("Brave Search")
    if not is_placeholder(values.get("TAVILY_API_KEY", "")):
        optional_configured.append("Tavily")
    if not is_placeholder(values.get("HA_ACCESS_TOKEN", "")):
        optional_configured.append("Home Assistant")
    if optional_configured:
        print(f"    Optional: {', '.join(optional_configured)}")

    if not prereqs.get("docker") or not prereqs.get("daemon") or not prereqs.get("compose"):
        print()
        warn("Docker is not ready — cannot start services now.")
        info("Once Docker is installed and running:")
        info("  make start")
        return

    # Offer to start
    print()
    launch = questionary.confirm(
        "Start Annie now?",
        default=True,
        style=STYLE,
    ).ask()

    if not launch:
        print()
        ok("Setup complete! Start Annie anytime with:")
        info("  make start")
        return

    header("Phase 6: Launching Annie")

    run_script = PROJECT_ROOT / "scripts" / "run_docker.sh"
    result = subprocess.run(
        ["bash", str(run_script)],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        err("Annie startup had issues. Check the output above.")
        info("Try: make logs  — to see service logs")
        info("Try: make health — to check service status")
        return

    # Wait for health
    print()
    info("Waiting for services to become healthy...")
    backend_port = values.get("BACKEND_PORT", "8001")
    healthy = False
    for i in range(20):
        try:
            resp = httpx.get(f"http://localhost:{backend_port}/health", timeout=3)
            if resp.status_code == 200:
                healthy = True
                break
        except Exception:
            pass
        time.sleep(3)
        if (i + 1) % 3 == 0:
            info(f"  Still starting... ({(i+1)*3}s)")

    print()
    if healthy:
        print(f"{C_GREEN}{C_BOLD}╔══════════════════════════════════════════╗{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}║     Annie is running! 🎉                ║{C_RESET}")
        print(f"{C_GREEN}{C_BOLD}╚══════════════════════════════════════════╝{C_RESET}")
        print()
        print(f"  Open Telegram and message your bot to start chatting.")
        print()
        print(f"  {C_DIM}Useful commands:{C_RESET}")
        print(f"    make logs       — View live logs")
        print(f"    make health     — Check service status")
        print(f"    make stop       — Stop all services")
        print(f"    make restart    — Restart services")
    else:
        warn("Services may still be starting up.")
        info("Check status with: make health")
        info("View logs with:    make logs")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def handle_interrupt(sig, frame):
    print(f"\n\n{C_YELLOW}Setup cancelled.{C_RESET}")
    print(f"Run {C_BOLD}make setup{C_RESET} anytime to resume.\n")
    sys.exit(130)


def main():
    signal.signal(signal.SIGINT, handle_interrupt)

    # Phase 1: Prerequisites
    prereqs = check_prerequisites()

    # Load existing / default values
    defaults = parse_env_example()
    existing = parse_existing_env()

    if existing:
        print()
        ok(f"Found existing .env with {len(existing)} values")
        reuse = questionary.confirm(
            "Use existing .env as starting point (you can change individual values)?",
            default=True,
            style=STYLE,
        ).ask()
        if reuse:
            defaults.update(existing)
        else:
            info("Starting fresh from env.example defaults")

    # Phase 2: Essential configuration
    values = configure_essentials(existing if existing else {}, defaults)

    # Merge: defaults ← values (so all env.example keys are present)
    full_values = {**defaults, **values}

    # Phase 3: agentic-memories
    full_values = check_agentic_memories(full_values, prereqs)

    # Phase 4: Optional enhancements
    full_values = configure_optional(full_values)

    # Phase 5 & 6: Write .env and launch
    write_and_launch(full_values, prereqs)


if __name__ == "__main__":
    main()
