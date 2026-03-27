"""
Backend API Environment Configuration and Validation

This module handles environment variable loading, validation, and masking
of sensitive values for the Backend API service.
"""

import os
from functools import lru_cache
from typing import List, Optional

# Sanitize Langfuse env vars before any langfuse imports elsewhere.
# The @observe() decorators auto-create a Langfuse client from env vars.
# If keys are placeholder values, clear them so the SDK stays disabled.
for _lf_key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    if os.environ.get(_lf_key) in (None, "", "REPLACE_ME"):
        os.environ.pop(_lf_key, None)


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
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
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

    # Load LLM model configuration
    from api.logging import get_logger
    from api.constants import (
        PRIMARY_MODELS, ALL_MODELS, DEFAULT_MODEL,
        MODEL_API_KEY_MAP, LEGACY_PROVIDER_TO_MODEL, MODEL_GEMINI_PRO,
    )
    logger = get_logger(__name__)

    # Read LLM_MODEL (preferred) or fall back to legacy LLM_PROVIDER
    raw_model = get_env_var("LLM_MODEL") or get_env_var("LLM_PROVIDER")
    if not raw_model or raw_model == "REPLACE_ME":
        raw_model = str(DEFAULT_MODEL)

    # Map legacy provider names (e.g. "grok-4") to actual model names
    llm_model = LEGACY_PROVIDER_TO_MODEL.get(raw_model, raw_model)

    if llm_model not in ALL_MODELS:
        raise ValueError(
            f"Invalid LLM_MODEL '{raw_model}'. Must be one of: {', '.join(ALL_MODELS)}"
        )

    config["LLM_MODEL"] = llm_model
    # Backward compat: keep LLM_PROVIDER populated for any code not yet migrated
    config["LLM_PROVIDER"] = llm_model

    # Validate that the required API key is set for the chosen model
    api_key_var = MODEL_API_KEY_MAP[llm_model]
    api_key = get_env_var(api_key_var)
    if not api_key or api_key == "REPLACE_ME":
        if llm_model == MODEL_GEMINI_PRO:
            raise ValueError(
                f"{api_key_var} is required when LLM_MODEL is set to '{llm_model}'. "
                "Get your API key from https://aistudio.google.com/app/apikey"
            )
        else:
            logger.warning(
                f"LLM_MODEL is set to '{llm_model}' but {api_key_var} is not set. "
                "LLM functionality will not work until configured."
            )
    else:
        config[api_key_var] = api_key

    # Load Gemini-specific configuration if Gemini is the primary model
    if llm_model == MODEL_GEMINI_PRO:
        config["GEMINI_MODEL"] = get_env_var("GEMINI_MODEL", default=str(MODEL_GEMINI_PRO))
        config["GEMINI_MAX_OUTPUT_TOKENS"] = get_env_var("GEMINI_MAX_OUTPUT_TOKENS", default="8192")
        config["GEMINI_TEMPERATURE"] = get_env_var("GEMINI_TEMPERATURE", default="1.0")
        config["GEMINI_SAFETY_SETTING"] = get_env_var("GEMINI_SAFETY_SETTING", default="BLOCK_NONE")
        config["GEMINI_CONTEXT_CACHE_TTL"] = get_env_var("GEMINI_CONTEXT_CACHE_TTL", default="300")

    # Load research-specific LLM model (optional, falls back to LLM_MODEL)
    # This allows using a different model for deep research tasks (e.g., GPT-5.2 for 128K output)
    research_model = get_env_var("RESEARCH_LLM_MODEL") or get_env_var("RESEARCH_LLM_PROVIDER")
    if research_model and research_model != "REPLACE_ME":
        resolved = LEGACY_PROVIDER_TO_MODEL.get(research_model, research_model)
        if resolved in PRIMARY_MODELS:
            config["RESEARCH_LLM_MODEL"] = resolved

    # Load summary-specific LLM model (optional, falls back to default model)
    # Used for context compaction summarization when conversations exceed token limits
    summary_model = get_env_var("SUMMARY_LLM_MODEL") or get_env_var("SUMMARY_LLM_PROVIDER")
    if summary_model and summary_model != "REPLACE_ME":
        resolved = LEGACY_PROVIDER_TO_MODEL.get(summary_model, summary_model)
        if resolved in PRIMARY_MODELS:
            config["SUMMARY_LLM_MODEL"] = resolved

    # Load optional LLM keys (may be set even if not primary provider)
    xai_key = get_env_var("XAI_API_KEY")
    if xai_key and xai_key != "REPLACE_ME":
        config["XAI_API_KEY"] = xai_key

    openai_key = get_env_var("OPENAI_API_KEY")
    if openai_key and openai_key != "REPLACE_ME":
        config["OPENAI_API_KEY"] = openai_key

    google_key = get_env_var("GOOGLE_API_KEY")
    if google_key and google_key != "REPLACE_ME":
        config["GOOGLE_API_KEY"] = google_key

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
