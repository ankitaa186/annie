"""
Backend API Logging Configuration

This module provides structured logging for the Backend API service.
Supports JSON format (production) and human-readable format (development).
Includes sensitive data masking and performance timing.
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

try:
    from .config import get_config, mask_sensitive_value
except ImportError:
    # Fallback for when config.py is not available
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


# Sensitive fields that should be masked in logs
SENSITIVE_FIELDS = [
    "api_key",
    "token",
    "password",
    "secret",
    "authorization",
    "grok_api_key",
    "chatgpt_api_key",
    "brave_search_api_key",
    "stock_api_key",
    "telegram_bot_token",
]


class JSONFormatter(logging.Formatter):
    """JSON formatter for production logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": getattr(record, "service", "backend"),
            "message": self._mask_sensitive_data(str(record.getMessage())),
        }
        
        # Add context fields if present
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "conversation_id"):
            log_data["conversation_id"] = record.conversation_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        
        # Add error details if present
        if record.exc_info:
            log_data["error_code"] = getattr(record, "error_code", "UNKNOWN_ERROR")
            log_data["stack_trace"] = self._mask_sensitive_data(
                "".join(traceback.format_exception(*record.exc_info))
            )
        
        # Add performance timing if present
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
            log_data["operation"] = getattr(record, "operation", "unknown")
        
        # Add any extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs", "message",
                "pathname", "process", "processName", "relativeCreated", "thread",
                "threadName", "exc_info", "exc_text", "stack_info", "service",
                "user_id", "conversation_id", "request_id", "error_code",
                "duration_ms", "operation"
            ]:
                # Mask sensitive fields
                if any(sensitive in key.lower() for sensitive in SENSITIVE_FIELDS):
                    log_data[key] = mask_sensitive_value(str(value))
                else:
                    log_data[key] = self._mask_sensitive_data(str(value))
        
        return json.dumps(log_data)
    
    def _mask_sensitive_data(self, text: str) -> str:
        """Mask sensitive data in log text."""
        if not text:
            return text
        
        # Simple approach: mask common patterns
        masked = text
        for field in SENSITIVE_FIELDS:
            # Mask patterns like "api_key": "value" or api_key=value
            import re
            pattern = rf'({field}["\s:=]+)([^\s"\'\),]+)'
            masked = re.sub(
                pattern,
                lambda m: m.group(1) + mask_sensitive_value(m.group(2)),
                masked,
                flags=re.IGNORECASE
            )
        
        return masked


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development logs."""
    
    def __init__(self):
        super().__init__(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(service)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ"
        )
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        # Ensure service name is set
        if not hasattr(record, "service"):
            record.service = "backend"
        
        # Add context to message if present
        context_parts = []
        if hasattr(record, "user_id"):
            context_parts.append(f"user_id={record.user_id}")
        if hasattr(record, "conversation_id"):
            context_parts.append(f"conversation_id={record.conversation_id}")
        if hasattr(record, "request_id"):
            context_parts.append(f"request_id={record.request_id}")
        
        if context_parts:
            record.msg = f"{record.msg} ({', '.join(context_parts)})"
        
        # Add error details if present
        if record.exc_info:
            error_code = getattr(record, "error_code", "UNKNOWN_ERROR")
            record.msg = f"{record.msg} [error_code={error_code}]"
        
        # Add performance timing if present
        if hasattr(record, "duration_ms"):
            operation = getattr(record, "operation", "unknown")
            record.msg = f"{record.msg} [operation={operation}, duration={record.duration_ms}ms]"
        
        # Mask sensitive data in message
        record.msg = self._mask_sensitive_data(str(record.msg))
        
        formatted = super().format(record)
        
        # Add stack trace if present
        if record.exc_info:
            formatted += "\n" + self._mask_sensitive_data(
                "".join(traceback.format_exception(*record.exc_info))
            )
        
        return formatted
    
    def _mask_sensitive_data(self, text: str) -> str:
        """Mask sensitive data in log text."""
        if not text:
            return text
        
        masked = text
        for field in SENSITIVE_FIELDS:
            import re
            pattern = rf'({field}["\s:=]+)([^\s"\'\),]+)'
            masked = re.sub(
                pattern,
                lambda m: m.group(1) + mask_sensitive_value(m.group(2)),
                masked,
                flags=re.IGNORECASE
            )
        
        return masked


def get_logger(name: str = "backend", service_name: str = "backend") -> logging.Logger:
    """
    Get configured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        service_name: Service name for log identification
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Get configuration
    try:
        config = get_config()
        log_level = config.get("LOG_LEVEL", "INFO")
        environment = config.get("ENVIRONMENT", "dev")
    except Exception:
        # Fallback to environment variables
        import os
        log_level = os.getenv("LOG_LEVEL", "INFO")
        environment = os.getenv("ENVIRONMENT", "dev")
    
    # Set log level
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Create handler (stdout for Docker)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)
    
    # Choose formatter based on environment
    if environment.lower() == "prod":
        formatter = JSONFormatter()
    else:
        formatter = HumanReadableFormatter()
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Add service name to all records
    old_factory = logging.getLogRecordFactory()
    
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = service_name
        return record
    
    logging.setLogRecordFactory(record_factory)
    
    return logger


def log_performance(operation_name: Optional[str] = None):
    """
    Decorator for logging slow operations (>1s).
    
    Args:
        operation_name: Name of the operation (defaults to function name)
    
    Usage:
        @log_performance("database_query")
        def query_database():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            logger = get_logger(func.__module__)
            op_name = operation_name or func.__name__
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                if duration_ms > 1000:  # Log if >1 second
                    logger.warning(
                        f"Slow operation detected: {op_name}",
                        extra={
                            "operation": op_name,
                            "duration_ms": duration_ms,
                        }
                    )
                
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    f"Operation failed: {op_name}",
                    exc_info=True,
                    extra={
                        "operation": op_name,
                        "duration_ms": duration_ms,
                        "error_code": "OPERATION_FAILED",
                    }
                )
                raise
        
        return wrapper
    return decorator


# Default logger instance
logger = get_logger(__name__)
