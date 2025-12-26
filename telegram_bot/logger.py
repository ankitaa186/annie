"""
Telegram Bot Logging Configuration

This module provides structured logging for the Telegram Bot service.
Reuses logging patterns from backend/api/logging.py.
"""

import sys
import logging

try:
    from backend.api.logging import (
        JSONFormatter,
        HumanReadableFormatter,
        get_logger as _get_logger,
        log_performance,
    )
except ImportError:
    # Standalone version if backend.api.logging is not available
    import json
    import traceback
    from datetime import datetime
    from typing import Any, Dict
    import pytz

    _PACIFIC_TZ = pytz.timezone("America/Los_Angeles")

    try:
        from config import get_config, mask_sensitive_value
    except ImportError:
        import os

        def get_config():
            return {
                "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
                "ENVIRONMENT": os.getenv("ENVIRONMENT", "dev"),
            }

        def mask_sensitive_value(value: str, show_first: int = 4, show_last: int = 4) -> str:
            if not value or len(value) <= show_first + show_last:
                return "***"
            return f"{value[:show_first]}...{value[-show_last:]}"

    SENSITIVE_FIELDS = [
        "api_key", "token", "password", "secret", "authorization",
        "telegram_bot_token",
    ]

    class JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_data: Dict[str, Any] = {
                "timestamp": datetime.now(_PACIFIC_TZ).isoformat(),
                "level": record.levelname,
                "service": getattr(record, "service", "telegram-bot"),
                "message": str(record.getMessage()),
            }
            if record.exc_info:
                log_data["stack_trace"] = "".join(traceback.format_exception(*record.exc_info))
            return json.dumps(log_data)
    
    class HumanReadableFormatter(logging.Formatter):
        def __init__(self):
            super().__init__(
                fmt="[%(asctime)s] [%(levelname)-8s] [%(service)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S"
            )

        def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
            ct = datetime.fromtimestamp(record.created, tz=_PACIFIC_TZ)
            if datefmt:
                return ct.strftime(datefmt)
            return ct.isoformat()

        def format(self, record: logging.LogRecord) -> str:
            if not hasattr(record, "service"):
                record.service = "telegram-bot"
            formatted = super().format(record)
            if record.exc_info:
                formatted += "\n" + "".join(traceback.format_exception(*record.exc_info))
            return formatted
    
    def _get_logger(name: str = "telegram_bot", service_name: str = "telegram-bot") -> logging.Logger:
        logger = logging.getLogger(name)
        if logger.handlers:
            return logger
        
        try:
            config = get_config()
            log_level = config.get("LOG_LEVEL", "INFO")
            environment = config.get("ENVIRONMENT", "dev")
        except Exception:
            import os
            log_level = os.getenv("LOG_LEVEL", "INFO")
            environment = os.getenv("ENVIRONMENT", "dev")
        
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logger.level)
        
        if environment.lower() == "prod":
            formatter = HumanReadableFormatter()
        else:
            formatter = HumanReadableFormatter()
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        old_factory = logging.getLogRecordFactory()
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.service = service_name
            return record
        logging.setLogRecordFactory(record_factory)
        
        return logger
    
    def log_performance(operation_name=None):
        def decorator(func):
            return func
        return decorator


def get_logger(name: str = "telegram_bot") -> logging.Logger:
    """
    Get configured logger instance for Telegram Bot.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    return _get_logger(name, service_name="telegram-bot")


# Default logger instance
logger = get_logger(__name__)
