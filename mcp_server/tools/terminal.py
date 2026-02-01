"""
Terminal Command Execution Tool

Thin HTTP proxy to host-terminal-mcp running on the host machine.
All permission/allowlist logic lives in host-terminal-mcp — this tool
simply forwards the request and returns the response.
"""

import os
from typing import Any, Dict, Optional

import httpx

from mcp_server.config import is_admin
from mcp_server.logging import get_logger

logger = get_logger(__name__)

HOST_TERMINAL_URL = os.getenv("HOST_TERMINAL_URL", "http://host.docker.internal:8099")

# Timeout slightly above host-terminal-mcp's 300s default
_HTTP_TIMEOUT = 135.0


async def execute_command_tool_handler(
    command: str,
    user_id: str,
    working_directory: Optional[str] = None,
) -> Dict[str, Any]:
    """Proxy execute_command to host-terminal-mcp HTTP server.

    Args:
        command: The command to execute on the host.
        user_id: The user ID of the requester (for audit/authorization).
        working_directory: Optional working directory for the command.

    Returns:
        Response dict from host-terminal-mcp (status, stdout, stderr, etc.).
    """
    # Check admin authorization
    if not is_admin(user_id):
        logger.warning(
            "Unauthorized terminal access attempt",
            extra={
                "user_id": user_id,
                "command": command,
            },
        )
        return {
            "status": "error",
            "error_code": "UNAUTHORIZED",
            "error": (
                "Terminal access is restricted to admin users only. "
                "Your user ID is not in the ADMIN_USER_IDS list."
            ),
        }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            payload: Dict[str, Any] = {"command": command}
            if working_directory:
                payload["working_directory"] = working_directory

            logger.info(
                "Proxying execute_command to host-terminal-mcp",
                extra={
                    "user_id": user_id,
                    "command": command,
                    "working_directory": working_directory,
                    "terminal_url": HOST_TERMINAL_URL,
                },
            )

            resp = await client.post(f"{HOST_TERMINAL_URL}/execute", json=payload)
            resp.raise_for_status()
            return resp.json()

    except httpx.TimeoutException:
        logger.error("host-terminal-mcp request timed out", extra={"command": command})
        return {"status": "error", "error": "Request to terminal server timed out"}

    except httpx.ConnectError:
        logger.error(
            "Cannot reach host-terminal-mcp",
            extra={"terminal_url": HOST_TERMINAL_URL},
        )
        return {
            "status": "error",
            "error": (
                "Cannot reach terminal server. "
                "Is host-terminal-mcp running? "
                f"(tried {HOST_TERMINAL_URL})"
            ),
        }

    except Exception as e:
        logger.error(
            "host-terminal-mcp proxy error",
            extra={"error": str(e), "command": command},
            exc_info=True,
        )
        return {"status": "error", "error": str(e)}


execute_command_tool = {
    "name": "execute_command",
    "description": (
        "Execute a terminal command on the host machine. "
        "Use this to check service logs (docker compose logs), "
        "inspect system state (ps, df, uptime), read files, or debug issues. "
        "Commands are subject to the host terminal server's permission controls. "
        "IMPORTANT: This tool is restricted to admin users only (configured via ADMIN_USER_IDS). "
        "Always tell the user which commands you are executing."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute",
            },
            "user_id": {
                "type": "string",
                "description": "The user ID of the requester (for audit/authorization)",
            },
            "working_directory": {
                "type": "string",
                "description": "Optional working directory for the command",
            },
        },
        "required": ["command", "user_id"],
    },
    "handler": execute_command_tool_handler,
}
