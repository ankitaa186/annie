"""
Tests for Home Assistant configuration in MCP server.

Story 16.4: Configuration & Environment Setup
Tests AC #2 (HA_ACCESS_TOKEN masking) and AC #4 (config loading).
"""

import os
from unittest.mock import patch

import pytest


class TestHAConfigLoading:
    """Test Home Assistant config variables are loaded correctly."""

    def test_ha_url_loaded_from_env(self):
        """AC #4: HA_URL is loaded from environment."""
        with patch.dict(os.environ, {"HA_URL": "http://192.168.1.100:8123"}):
            # Re-import to pick up new env
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_URL == "http://192.168.1.100:8123"

    def test_ha_access_token_loaded_from_env(self):
        """AC #4: HA_ACCESS_TOKEN is loaded from environment."""
        with patch.dict(os.environ, {"HA_ACCESS_TOKEN": "test-token-12345"}):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_ACCESS_TOKEN == "test-token-12345"

    def test_ha_control_allowlist_loaded_from_env(self):
        """AC #4: HA_CONTROL_ALLOWLIST is loaded from environment."""
        with patch.dict(os.environ, {"HA_CONTROL_ALLOWLIST": "light.*,switch.fan"}):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_CONTROL_ALLOWLIST == "light.*,switch.fan"

    def test_ha_timeout_loaded_with_default(self):
        """AC #4: HA_TIMEOUT defaults to 10."""
        with patch.dict(os.environ, {"HA_TIMEOUT": ""}, clear=False):
            # Remove HA_TIMEOUT to test default
            env_copy = os.environ.copy()
            if "HA_TIMEOUT" in env_copy:
                del env_copy["HA_TIMEOUT"]

            with patch.dict(os.environ, env_copy, clear=True):
                import importlib
                import mcp_server.config as config_module
                importlib.reload(config_module)

                assert config_module.HA_TIMEOUT == 10

    def test_ha_timeout_loaded_custom_value(self):
        """AC #4: HA_TIMEOUT can be customized."""
        with patch.dict(os.environ, {"HA_TIMEOUT": "30"}):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_TIMEOUT == 30


class TestHAAccessTokenMasking:
    """Test HA_ACCESS_TOKEN is properly masked in logs."""

    def test_ha_access_token_in_sensitive_vars(self):
        """AC #2: HA_ACCESS_TOKEN is in SENSITIVE_VARS list."""
        from mcp_server.config import SENSITIVE_VARS

        assert "HA_ACCESS_TOKEN" in SENSITIVE_VARS

    def test_mask_sensitive_value_masks_token(self):
        """AC #2: Token is masked correctly (show first 4 + last 4)."""
        from mcp_server.config import mask_sensitive_value

        # Long token shows first 4 and last 4
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test"
        masked = mask_sensitive_value(token)

        assert masked == "eyJ0...test"
        assert "J1QiLC" not in masked  # Middle is hidden

    def test_mask_sensitive_value_short_token(self):
        """Short tokens are fully masked."""
        from mcp_server.config import mask_sensitive_value

        # Token shorter than 8 chars becomes ***
        short_token = "abc123"
        masked = mask_sensitive_value(short_token)

        assert masked == "***"


class TestValidateHAConfig:
    """Test validate_ha_config() function."""

    def test_validate_ha_config_both_set(self):
        """No issues when both HA_URL and HA_ACCESS_TOKEN are set."""
        with patch.dict(os.environ, {
            "HA_URL": "http://192.168.1.100:8123",
            "HA_ACCESS_TOKEN": "valid-token"
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_ha_config()
            assert issues == []

    def test_validate_ha_config_missing_url(self):
        """Reports issue when HA_URL is missing."""
        with patch.dict(os.environ, {
            "HA_URL": "",
            "HA_ACCESS_TOKEN": "valid-token"
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_ha_config()
            assert "HA_URL not configured" in issues

    def test_validate_ha_config_missing_token(self):
        """Reports issue when HA_ACCESS_TOKEN is missing."""
        with patch.dict(os.environ, {
            "HA_URL": "http://192.168.1.100:8123",
            "HA_ACCESS_TOKEN": ""
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_ha_config()
            assert "HA_ACCESS_TOKEN not configured" in issues

    def test_validate_ha_config_both_missing(self):
        """Reports both issues when neither is set."""
        with patch.dict(os.environ, {
            "HA_URL": "",
            "HA_ACCESS_TOKEN": ""
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_ha_config()
            assert len(issues) == 2
            assert "HA_URL not configured" in issues
            assert "HA_ACCESS_TOKEN not configured" in issues


class TestIsHAConfigured:
    """Test is_ha_configured() function."""

    def test_is_ha_configured_true_when_both_set(self):
        """Returns True when both HA_URL and HA_ACCESS_TOKEN are set."""
        with patch.dict(os.environ, {
            "HA_URL": "http://192.168.1.100:8123",
            "HA_ACCESS_TOKEN": "valid-token"
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.is_ha_configured() is True

    def test_is_ha_configured_false_when_url_missing(self):
        """Returns False when HA_URL is empty."""
        with patch.dict(os.environ, {
            "HA_URL": "",
            "HA_ACCESS_TOKEN": "valid-token"
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.is_ha_configured() is False

    def test_is_ha_configured_false_when_token_missing(self):
        """Returns False when HA_ACCESS_TOKEN is empty."""
        with patch.dict(os.environ, {
            "HA_URL": "http://192.168.1.100:8123",
            "HA_ACCESS_TOKEN": ""
        }):
            import importlib
            import mcp_server.config as config_module
            importlib.reload(config_module)

            assert config_module.is_ha_configured() is False
