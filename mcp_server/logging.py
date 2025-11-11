"""
MCP Server Logging Configuration

This module provides structured logging for the MCP Server service.
Reuses logging patterns from backend/api/logging.py.
"""

import sys
import importlib.util

# Import standard library logging module explicitly to avoid circular import
# when this file is named logging.py
_stdlib_logging_spec = importlib.util.find_spec("logging")
_stdlib_logging = importlib.util.module_from_spec(_stdlib_logging_spec)
_stdlib_logging_spec.loader.exec_module(_stdlib_logging)
std_logging = _stdlib_logging

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
        "brave_search_api_key", "stock_api_key",
    ]
    
    class JSONFormatter(std_logging.Formatter):
        def format(self, record: std_logging.LogRecord) -> str:
            log_data: Dict[str, Any] = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "service": getattr(record, "service", "mcp-server"),
                "message": str(record.getMessage()),
            }
            if record.exc_info:
                log_data["stack_trace"] = "".join(traceback.format_exception(*record.exc_info))
            return json.dumps(log_data)
    
    class HumanReadableFormatter(std_logging.Formatter):
        def __init__(self):
            super().__init__(
                fmt="[%(asctime)s] [%(levelname)-8s] [%(service)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ"
            )
        
        def format(self, record: std_logging.LogRecord) -> str:
            if not hasattr(record, "service"):
                record.service = "mcp-server"
            formatted = super().format(record)
            if record.exc_info:
                formatted += "\n" + "".join(traceback.format_exception(*record.exc_info))
            return formatted
    
    def _get_logger(name: str = "mcp_server", service_name: str = "mcp-server") -> std_logging.Logger:
        logger = std_logging.getLogger(name)
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
        
        logger.setLevel(getattr(std_logging, log_level.upper(), std_logging.INFO))
        handler = std_logging.StreamHandler(sys.stdout)
        handler.setLevel(logger.level)
        
        if environment.lower() == "prod":
            formatter = JSONFormatter()
        else:
            formatter = HumanReadableFormatter()
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        old_factory = std_logging.getLogRecordFactory()
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.service = service_name
            return record
        std_logging.setLogRecordFactory(record_factory)
        
        return logger
    
    def log_performance(operation_name=None):
        def decorator(func):
            return func
        return decorator


def get_logger(name: str = "mcp_server") -> std_logging.Logger:
    """
    Get configured logger instance for MCP Server.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    return _get_logger(name, service_name="mcp-server")


# Default logger instance
logger = get_logger(__name__)
