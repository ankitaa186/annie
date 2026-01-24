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
    "MCP_SERVER_PORT": "8002",
}

# Sensitive variables that should be masked in logs
SENSITIVE_VARS = [
    "BRAVE_SEARCH_API_KEY",
    "STOCK_API_KEY",
    "TAVILY_API_KEY",
    "JINA_API_KEY",
    "REDDIT_CLIENT_SECRET",
    "HA_ACCESS_TOKEN",  # Epic 16: Home Assistant Integration
]


# Epic 16: Home Assistant Configuration
# These are loaded at module level for easy access by HA tools
HA_URL = os.getenv("HA_URL", "")
HA_ACCESS_TOKEN = os.getenv("HA_ACCESS_TOKEN", "")
HA_CONTROL_ALLOWLIST = os.getenv("HA_CONTROL_ALLOWLIST", "")
HA_TIMEOUT = int(os.getenv("HA_TIMEOUT", "10"))


def validate_ha_config() -> list:
    """
    Validate Home Assistant configuration.

    Returns:
        List of configuration issues (empty list = valid)
    """
    issues = []
    if not HA_URL:
        issues.append("HA_URL not configured")
    if not HA_ACCESS_TOKEN:
        issues.append("HA_ACCESS_TOKEN not configured")
    return issues


def is_ha_configured() -> bool:
    """
    Check if Home Assistant is configured.

    Returns:
        True if both HA_URL and HA_ACCESS_TOKEN are set
    """
    return bool(HA_URL and HA_ACCESS_TOKEN)


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
    
    # Load tool API keys (optional - for Epic 4 tools)
    # These keys are not required for Sprint 1, just log warnings
    from mcp_server.logging import get_logger
    logger = get_logger(__name__)

    brave_key = get_env_var("BRAVE_SEARCH_API_KEY")
    if brave_key and brave_key != "REPLACE_ME":
        config["BRAVE_SEARCH_API_KEY"] = brave_key
    else:
        logger.warning(
            "BRAVE_SEARCH_API_KEY is not set. Internet access tool will not work until configured."
        )

    stock_key = get_env_var("STOCK_API_KEY")
    if stock_key and stock_key != "REPLACE_ME":
        config["STOCK_API_KEY"] = stock_key
    else:
        logger.warning(
            "STOCK_API_KEY is not set. Stock trader tool will not work until configured."
        )

    tavily_key = get_env_var("TAVILY_API_KEY")
    if tavily_key and tavily_key != "REPLACE_ME":
        config["TAVILY_API_KEY"] = tavily_key
    else:
        logger.warning(
            "TAVILY_API_KEY is not set. Web search will fall back to DuckDuckGo only."
        )

    # Jina Reader API key (optional - for web_crawl fallback)
    jina_key = get_env_var("JINA_API_KEY")
    if jina_key:
        config["JINA_API_KEY"] = jina_key

    # Reddit API credentials (optional - falls back to JSON API)
    reddit_client_id = get_env_var("REDDIT_CLIENT_ID")
    reddit_client_secret = get_env_var("REDDIT_CLIENT_SECRET")
    reddit_user_agent = get_env_var("REDDIT_USER_AGENT", default="annie-bot/1.0")

    if reddit_client_id and reddit_client_id != "REPLACE_ME":
        config["REDDIT_CLIENT_ID"] = reddit_client_id
    if reddit_client_secret and reddit_client_secret != "REPLACE_ME":
        config["REDDIT_CLIENT_SECRET"] = reddit_client_secret
    config["REDDIT_USER_AGENT"] = reddit_user_agent

    if not (reddit_client_id and reddit_client_id != "REPLACE_ME" and
            reddit_client_secret and reddit_client_secret != "REPLACE_ME"):
        logger.warning(
            "REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET is not set. "
            "Reddit search will use JSON API fallback (no comments)."
        )

    # Epic 16: Home Assistant configuration (optional - for HA tools)
    # Uses module-level variables for easy access by tools
    config["HA_URL"] = HA_URL
    config["HA_ACCESS_TOKEN"] = HA_ACCESS_TOKEN
    config["HA_CONTROL_ALLOWLIST"] = HA_CONTROL_ALLOWLIST
    config["HA_TIMEOUT"] = HA_TIMEOUT

    if not is_ha_configured():
        logger.info(
            "Home Assistant not configured (HA_URL or HA_ACCESS_TOKEN missing). "
            "HA tools will return CONFIG_ERROR until configured."
        )

    # Raise errors only if critical validation failed
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
    config = validate_environment()

    # Convert port to int for uvicorn
    if "MCP_SERVER_PORT" in config:
        config["MCP_SERVER_PORT"] = int(config["MCP_SERVER_PORT"])

    return config


# Validate on import (can be disabled for testing)
if os.getenv("SKIP_ENV_VALIDATION") != "true":
    try:
        _config = get_config()
    except ValueError:
        # Don't fail on import - let application handle validation
        pass
