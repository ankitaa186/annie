"""
MCP Server Environment Configuration and Validation

This module handles environment variable loading and validation
for the MCP Server service.
"""

import os
from typing import List, Optional


def mask_sensitive_value(value: str, show_first: int = 4, show_last: int = 4) -> str:
    """
    Mask sensitive values in logs and error messages.
    
    Args:
        value: The sensitive value to mask
        show_first: Number of characters to show at start (default: 4)
        show_last: Number of characters to show at end (default: 4)
    
    Returns:
        Masked string
    """
    if not value or len(value) <= show_first + show_last:
        return "***"
    
    return f"{value[:show_first]}...{value[-show_last:]}"


def get_env_var(name: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Get environment variable with optional default and required validation.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        required: Whether variable is required
    
    Returns:
        Environment variable value
    
    Raises:
        ValueError: If required variable is missing
    """
    value = os.getenv(name, default)
    
    if required and (not value or value == "REPLACE_ME"):
        raise ValueError(
            f"Required environment variable '{name}' is not set or has placeholder value. "
            f"Please set it in your .env file."
        )
    
    return value


# Required environment variables for MCP Server service
REQUIRED_VARS = [
    "AGENTIC_MEMORIES_URL",
]

# Optional environment variables with defaults
OPTIONAL_VARS = {
    "LOG_LEVEL": "INFO",
    "ENVIRONMENT": "dev",
}

# Sensitive variables that should be masked in logs
SENSITIVE_VARS = [
    "BRAVE_SEARCH_API_KEY",
    "STOCK_API_KEY",
]


def validate_environment() -> dict:
    """
    Validate and load all environment variables for MCP Server service.
    
    Returns:
        Dictionary of validated environment variables
    
    Raises:
        ValueError: If required variables are missing or invalid
    """
    errors: List[str] = []
    config = {}
    
    # Validate required variables
    for var in REQUIRED_VARS:
        try:
            value = get_env_var(var, required=True)
            config[var] = value
        except ValueError as e:
            errors.append(str(e))
    
    # Load optional variables with defaults
    for var, default in OPTIONAL_VARS.items():
        config[var] = get_env_var(var, default=default)
    
    # Load tool API keys (optional but recommended)
    brave_key = get_env_var("BRAVE_SEARCH_API_KEY")
    if brave_key and brave_key != "REPLACE_ME":
        config["BRAVE_SEARCH_API_KEY"] = brave_key
    else:
        errors.append(
            "BRAVE_SEARCH_API_KEY is not set. Internet access tool will not work. "
            "Please set it in your .env file."
        )
    
    stock_key = get_env_var("STOCK_API_KEY")
    if stock_key and stock_key != "REPLACE_ME":
        config["STOCK_API_KEY"] = stock_key
    else:
        errors.append(
            "STOCK_API_KEY is not set. Stock trader tool will not work. "
            "Please set it in your .env file."
        )
    
    # Raise errors if any validation failed
    if errors:
        error_msg = "Environment validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)
    
    return config


def get_config() -> dict:
    """
    Get validated configuration dictionary.
    
    Returns:
        Dictionary of validated configuration values
    """
    return validate_environment()


# Validate on import (can be disabled for testing)
if os.getenv("SKIP_ENV_VALIDATION") != "true":
    try:
        _config = get_config()
    except ValueError:
        # Don't fail on import - let application handle validation
        pass
