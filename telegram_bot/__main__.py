"""
Telegram Bot Module Entry Point

Allows running telegram bot as a module: python -m telegram_bot
"""

import asyncio
import os
import sys

from telegram_bot.bot import main
from telegram_bot.logger import get_logger

logger = get_logger(__name__)


def setup_debugger():
    """Initialize remote debugger automatically in dev environment."""
    environment = os.getenv("ENVIRONMENT", "dev")
    
    # Only enable debugging in dev environment
    if environment.lower() == "dev":
        try:
            import debugpy
            debug_port = int(os.getenv("DEBUGGER_PORT", "5680"))
            debugpy.listen(("0.0.0.0", debug_port))
            logger.info(
                f"🔧 Remote debugger listening on port {debug_port} (dev mode)",
                extra={"event": "debugger_setup"}
            )
        except ImportError:
            logger.debug("debugpy not available - remote debugging disabled")
        except Exception as e:
            logger.warning(f"Failed to setup debugger: {e}")


# Initialize debugger before starting bot (dev only)
setup_debugger()

if __name__ == "__main__":
    logger.info(
        "Starting Telegram bot module",
        extra={
            "version": "1.0.0",
            "event": "module_start"
        }
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(
            "Telegram bot stopped by user",
            extra={"event": "module_stopped"}
        )
        sys.exit(0)
    except Exception as e:
        logger.critical(
            "Telegram bot module failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "module_failed"
            },
            exc_info=True
        )
        sys.exit(1)
