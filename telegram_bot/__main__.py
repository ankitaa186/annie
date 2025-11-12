"""
Telegram Bot Module Entry Point

Allows running telegram bot as a module: python -m telegram_bot
"""

import asyncio
import sys

from telegram_bot.bot import main
from telegram_bot.logger import get_logger

logger = get_logger(__name__)

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
