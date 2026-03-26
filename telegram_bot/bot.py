"""
Telegram Bot Main Entry Point

This module initializes and runs the Telegram bot with long polling.
"""

import asyncio
import signal
import sys
from telegram.ext import Application, ApplicationBuilder

from telegram_bot.config import get_config, mask_sensitive_value
from telegram_bot.logger import get_logger
from telegram_bot.handlers.message import setup_message_handlers
from telegram_bot.backend_client import close_backend_client

logger = get_logger(__name__)

# Global application instance for graceful shutdown
app_instance = None


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(
            "Received shutdown signal",
            extra={
                "signal": signal.Signals(signum).name,
                "event": "shutdown_initiated"
            }
        )
        if app_instance:
            asyncio.create_task(app_instance.stop())
            asyncio.create_task(app_instance.shutdown())
            asyncio.create_task(close_backend_client())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def initialize_bot_with_retry(bot_token: str, max_retries: int = 3) -> Application:
    """
    Initialize Telegram bot with connection retry logic.

    Args:
        bot_token: Telegram bot token
        max_retries: Maximum number of retry attempts

    Returns:
        Initialized Application instance

    Raises:
        Exception: If all retry attempts fail
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Initializing Telegram bot",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "event": "bot_initialization"
                }
            )

            # Build application
            app = ApplicationBuilder().token(bot_token).build()

            # Test connection by getting bot info
            bot_info = await app.bot.get_me()

            logger.info(
                "Telegram bot initialized successfully",
                extra={
                    "bot_username": bot_info.username,
                    "bot_id": bot_info.id,
                    "bot_name": bot_info.first_name,
                    "event": "bot_initialized"
                }
            )

            return app

        except Exception as e:
            wait_time = 2 ** (attempt - 1)  # Exponential backoff: 1s, 2s, 4s

            logger.error(
                "Failed to initialize Telegram bot",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "retry_after_seconds": wait_time if attempt < max_retries else None,
                    "event": "bot_initialization_failed"
                },
                exc_info=True
            )

            if attempt < max_retries:
                logger.info(
                    f"Retrying in {wait_time} seconds...",
                    extra={
                        "wait_time_seconds": wait_time,
                        "event": "retry_scheduled"
                    }
                )
                await asyncio.sleep(wait_time)
            else:
                logger.critical(
                    "Failed to initialize bot after all retries",
                    extra={
                        "total_attempts": max_retries,
                        "event": "bot_initialization_exhausted"
                    }
                )
                raise


async def main():
    """Main entry point for Telegram bot."""
    global app_instance

    try:
        # Load and validate configuration
        logger.info(
            "Loading Telegram bot configuration",
            extra={"event": "config_loading"}
        )

        config = get_config()
        bot_token = config["TELEGRAM_BOT_TOKEN"]
        polling_timeout = int(config.get("POLLING_TIMEOUT", "30"))
        max_retries = int(config.get("MAX_RETRIES", "3"))
        environment = config.get("ENVIRONMENT", "dev")

        logger.info(
            "Configuration loaded successfully",
            extra={
                "environment": environment,
                "polling_timeout": polling_timeout,
                "max_retries": max_retries,
                "bot_token": mask_sensitive_value(bot_token),
                "event": "config_loaded"
            }
        )

        # Setup signal handlers for graceful shutdown
        setup_signal_handlers()

        # Initialize bot with retry logic
        app = await initialize_bot_with_retry(bot_token, max_retries)
        app_instance = app

        # Setup message handlers
        setup_message_handlers(app)
        logger.info(
            "Message handlers setup complete",
            extra={"event": "handlers_configured"}
        )

        # Start polling
        logger.info(
            "Starting Telegram bot polling",
            extra={
                "polling_timeout": polling_timeout,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
                "event": "polling_start"
            }
        )

        # Initialize and start polling manually
        await app.initialize()
        await app.start()

        # Start polling updates
        await app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,
            timeout=polling_timeout
        )

        # Keep running until stopped
        try:
            # Run forever
            stop_signal = asyncio.Event()
            await stop_signal.wait()
        finally:
            # Cleanup
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    except ValueError as e:
        # Configuration validation error
        logger.critical(
            "Configuration validation failed",
            extra={
                "error": str(e),
                "event": "config_validation_failed"
            }
        )
        sys.exit(1)

    except Exception as e:
        # Unexpected error
        logger.critical(
            "Telegram bot crashed with unexpected error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "bot_crashed"
            },
            exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    logger.info(
        "Telegram bot service starting",
        extra={
            "service": "telegram-bot",
            "version": "1.0.0",
            "event": "service_start"
        }
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(
            "Telegram bot service stopped by user",
            extra={"event": "service_stopped"}
        )
    except Exception as e:
        logger.critical(
            "Telegram bot service failed to start",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "service_failed"
            },
            exc_info=True
        )
        sys.exit(1)
