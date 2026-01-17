"""
Backend API Environment Configuration and Validation

This module handles environment variable loading, validation, and masking
of sensitive values for the Backend API service.
"""

import os
from functools import lru_cache
from typing import List, Optional


def mask_sensitive_value(value: str, show_first: int = 4, show_last: int = 4) -> str:
    """
    Mask sensitive values in logs and error messages.
    
    Shows only first N and last N characters, replacing middle with '...'
    
    Args:
        value: The sensitive value to mask
        show_first: Number of characters to show at start (default: 4)
        show_last: Number of characters to show at end (default: 4)
    
    Returns:
        Masked string (e.g., "secr...2345" for "secret-key-12345")
    """
    if not value or len(value) <= show_first + show_last:
        return "***"  # Too short to mask meaningfully
    
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


# Required environment variables for Backend service
REQUIRED_VARS = [
    "AGENTIC_MEMORIES_URL",
]

# Optional environment variables with defaults
OPTIONAL_VARS = {
    "LOG_LEVEL": "INFO",
    "REDIS_HOST": "redis",
    "REDIS_PORT": "6379",
    "MCP_SERVER_URL": "http://mcp-server:8002",
    "BACKEND_PORT": "8000",
    "ENVIRONMENT": "dev",
    "TELEGRAM_BOT_TOKEN": None,  # Required for proactive worker
}

# Sensitive variables that should be masked in logs
SENSITIVE_VARS = [
    "GROK_API_KEY",
    "CHATGPT_API_KEY",
    "GEMINI_API_KEY",  # Story 9.2
    "TELEGRAM_BOT_TOKEN",
    "BRAVE_SEARCH_API_KEY",
    "STOCK_API_KEY",
    "LANGFUSE_SECRET_KEY",
    "HA_MQTT_PASSWORD",  # Epic 16: Home Assistant Integration
    "HA_ACCESS_TOKEN",  # Epic 16: Home Assistant REST API token
    "TAVILY_API_KEY",  # Epic 15: Web search
    "JINA_API_KEY",  # Epic 15: Web crawl
    "REDDIT_CLIENT_SECRET",  # Epic 15: Reddit search
]


# Epic 16: Home Assistant MQTT Configuration
# These are loaded at module level for easy access by MQTT subscriber
HA_MQTT_BROKER = os.getenv("HA_MQTT_BROKER", "")
HA_MQTT_PORT = int(os.getenv("HA_MQTT_PORT", "1883"))
HA_MQTT_USERNAME = os.getenv("HA_MQTT_USERNAME", "")
HA_MQTT_PASSWORD = os.getenv("HA_MQTT_PASSWORD", "")
HA_MQTT_TOPICS = os.getenv("HA_MQTT_TOPICS", "annie/alerts/#")
HA_MQTT_ALERT_USER_ID = os.getenv("HA_MQTT_ALERT_USER_ID", "")


def validate_mqtt_config() -> list:
    """
    Validate MQTT configuration for Home Assistant alerts.

    Only validates if HA_MQTT_BROKER is set (MQTT is optional).

    Returns:
        List of configuration issues (empty list = valid)
    """
    issues = []

    # Only validate if MQTT is being used
    if not HA_MQTT_BROKER:
        return issues  # No issues - MQTT is simply disabled

    # If broker is set, alert user ID is required
    if not HA_MQTT_ALERT_USER_ID:
        issues.append("HA_MQTT_ALERT_USER_ID required when HA_MQTT_BROKER is set")

    # Validate port is reasonable
    if HA_MQTT_PORT < 1 or HA_MQTT_PORT > 65535:
        issues.append(f"HA_MQTT_PORT must be 1-65535, got {HA_MQTT_PORT}")

    return issues


def is_mqtt_configured() -> bool:
    """
    Check if MQTT is configured and valid for use.

    Returns:
        True if HA_MQTT_BROKER is set and configuration is valid
    """
    if not HA_MQTT_BROKER:
        return False
    return len(validate_mqtt_config()) == 0


def validate_environment() -> dict:
    """
    Validate and load all environment variables for Backend service.
    
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

    # Load LLM provider configuration (optional for Story 2.1, required for Story 2.2)
    # For now, log warnings if not configured
    from api.logging import get_logger
    logger = get_logger(__name__)

    llm_provider = get_env_var("LLM_PROVIDER", default="grok-4")
    config["LLM_PROVIDER"] = llm_provider

    if llm_provider == "grok-4":
        grok_key = get_env_var("GROK_API_KEY")
        if not grok_key or grok_key == "REPLACE_ME":
            logger.warning(
                "LLM_PROVIDER is set to 'grok-4' but GROK_API_KEY is not set. "
                "LLM functionality will not work until configured (required for Story 2.2)."
            )
        else:
            config["GROK_API_KEY"] = grok_key
    elif llm_provider == "chatgpt-5":
        chatgpt_key = get_env_var("CHATGPT_API_KEY")
        if not chatgpt_key or chatgpt_key == "REPLACE_ME":
            logger.warning(
                "LLM_PROVIDER is set to 'chatgpt-5' but CHATGPT_API_KEY is not set. "
                "LLM functionality will not work until configured (required for Story 2.2)."
            )
        else:
            config["CHATGPT_API_KEY"] = chatgpt_key
    elif llm_provider == "gemini-3-pro-preview":
        # Story 9.2: Gemini 3 Pro support
        gemini_key = get_env_var("GEMINI_API_KEY")
        if not gemini_key or gemini_key == "REPLACE_ME":
            raise ValueError(
                "GEMINI_API_KEY is required when LLM_PROVIDER is set to 'gemini-3-pro-preview'. "
                "Get your API key from https://aistudio.google.com/app/apikey"
            )
        else:
            config["GEMINI_API_KEY"] = gemini_key
            # Load Gemini-specific configuration
            config["GEMINI_MODEL"] = get_env_var("GEMINI_MODEL", default="gemini-3-pro-preview")
            config["GEMINI_MAX_OUTPUT_TOKENS"] = get_env_var("GEMINI_MAX_OUTPUT_TOKENS", default="8192")
            config["GEMINI_TEMPERATURE"] = get_env_var("GEMINI_TEMPERATURE", default="1.0")
            config["GEMINI_SAFETY_SETTING"] = get_env_var("GEMINI_SAFETY_SETTING", default="BLOCK_NONE")
            config["GEMINI_CONTEXT_CACHE_TTL"] = get_env_var("GEMINI_CONTEXT_CACHE_TTL", default="300")
    else:
        logger.warning(
            f"Invalid LLM_PROVIDER '{llm_provider}'. Must be 'grok-4', 'chatgpt-5', or 'gemini-3-pro-preview'. "
            f"LLM functionality will not work until configured properly."
        )

    # Load research-specific LLM provider (optional, falls back to LLM_PROVIDER)
    # This allows using a different model for deep research tasks (e.g., GPT-5.2 for 128K output)
    research_provider = get_env_var("RESEARCH_LLM_PROVIDER")
    if research_provider and research_provider != "REPLACE_ME":
        valid_providers = ["grok-4", "chatgpt-5", "gemini-3-pro-preview"]
        if research_provider in valid_providers:
            config["RESEARCH_LLM_PROVIDER"] = research_provider
            # Note: Don't log here - causes recursive loop with logger init
        else:
            # Invalid provider - just ignore it (don't log to avoid recursive loop)
            pass

    # Load optional LLM keys (may be set even if not primary provider)
    grok_key = get_env_var("GROK_API_KEY")
    if grok_key and grok_key != "REPLACE_ME":
        config["GROK_API_KEY"] = grok_key

    chatgpt_key = get_env_var("CHATGPT_API_KEY")
    if chatgpt_key and chatgpt_key != "REPLACE_ME":
        config["CHATGPT_API_KEY"] = chatgpt_key

    # Load optional Gemini API key (Story 9.2)
    gemini_key = get_env_var("GEMINI_API_KEY")
    if gemini_key and gemini_key != "REPLACE_ME":
        config["GEMINI_API_KEY"] = gemini_key

    # Epic 16: Home Assistant MQTT configuration (optional - for MQTT subscriber)
    # Uses module-level variables for easy access by subscriber
    config["HA_MQTT_BROKER"] = HA_MQTT_BROKER
    config["HA_MQTT_PORT"] = HA_MQTT_PORT
    config["HA_MQTT_USERNAME"] = HA_MQTT_USERNAME
    config["HA_MQTT_PASSWORD"] = HA_MQTT_PASSWORD
    config["HA_MQTT_TOPICS"] = HA_MQTT_TOPICS
    config["HA_MQTT_ALERT_USER_ID"] = HA_MQTT_ALERT_USER_ID

    # Note: MQTT status logging moved to application startup (main.py)
    # to avoid log spam during test module reloads

    # Raise errors if any validation failed
    if errors:
        error_msg = "Environment validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    return config


def get_config() -> dict:
    """
    Get validated configuration dictionary.
    
    This function should be called at application startup to validate
    environment variables and provide configuration to the application.
    
    Returns:
        Dictionary of validated configuration values
    """
    return validate_environment()


# Langfuse Configuration Functions (Story 8.1)

@lru_cache(maxsize=1)
def get_langfuse_public_key() -> Optional[str]:
    """Get Langfuse public key from environment.

    Cached for performance optimization.

    Returns:
        Public key if set, None otherwise.
    """
    key = get_env_var("LANGFUSE_PUBLIC_KEY")
    if key and key != "REPLACE_ME":
        return key
    return None


@lru_cache(maxsize=1)
def get_langfuse_secret_key() -> Optional[str]:
    """Get Langfuse secret key from environment.

    Cached for performance optimization.

    Returns:
        Secret key if set, None otherwise.
    """
    key = get_env_var("LANGFUSE_SECRET_KEY")
    if key and key != "REPLACE_ME":
        return key
    return None


@lru_cache(maxsize=1)
def get_langfuse_host() -> str:
    """Get Langfuse host URL from environment.

    Cached for performance optimization.

    Returns:
        Host URL (defaults to Langfuse Cloud US region).
    """
    return get_env_var("LANGFUSE_HOST", default="https://us.cloud.langfuse.com")


@lru_cache(maxsize=1)
def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled (both keys configured).

    Cached for performance optimization.

    Returns:
        True if both public and secret keys are set, False otherwise.
    """
    return get_langfuse_public_key() is not None and get_langfuse_secret_key() is not None


# Validate on import (can be disabled for testing)
if os.getenv("SKIP_ENV_VALIDATION") != "true":
    try:
        _config = get_config()
    except ValueError:
        # Don't fail on import - let application handle validation
        pass
