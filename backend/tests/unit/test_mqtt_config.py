"""
Tests for Home Assistant MQTT configuration in Backend API.

Story 16.4: Configuration & Environment Setup
Tests AC #2 (HA_MQTT_PASSWORD masking) and AC #4 (MQTT config loading).
"""

import os
from unittest.mock import patch

import pytest


class TestMQTTConfigLoading:
    """Test MQTT config variables are loaded correctly."""

    def test_mqtt_broker_loaded_from_env(self):
        """AC #4: HA_MQTT_BROKER is loaded from environment."""
        with patch.dict(os.environ, {"HA_MQTT_BROKER": "192.168.1.100"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_BROKER == "192.168.1.100"

    def test_mqtt_port_default_value(self):
        """AC #4: HA_MQTT_PORT defaults to 1883."""
        env_copy = os.environ.copy()
        if "HA_MQTT_PORT" in env_copy:
            del env_copy["HA_MQTT_PORT"]

        with patch.dict(os.environ, env_copy, clear=True):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_PORT == 1883

    def test_mqtt_port_custom_value(self):
        """AC #4: HA_MQTT_PORT can be customized."""
        with patch.dict(os.environ, {"HA_MQTT_PORT": "8883"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_PORT == 8883

    def test_mqtt_username_loaded_from_env(self):
        """AC #4: HA_MQTT_USERNAME is loaded from environment."""
        with patch.dict(os.environ, {"HA_MQTT_USERNAME": "mqtt_user"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_USERNAME == "mqtt_user"

    def test_mqtt_password_loaded_from_env(self):
        """AC #4: HA_MQTT_PASSWORD is loaded from environment."""
        with patch.dict(os.environ, {"HA_MQTT_PASSWORD": "secret_pass"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_PASSWORD == "secret_pass"

    def test_mqtt_topics_default_value(self):
        """AC #4: HA_MQTT_TOPICS defaults to annie/alerts/#."""
        env_copy = os.environ.copy()
        if "HA_MQTT_TOPICS" in env_copy:
            del env_copy["HA_MQTT_TOPICS"]

        with patch.dict(os.environ, env_copy, clear=True):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_TOPICS == "annie/alerts/#"

    def test_mqtt_topics_custom_value(self):
        """AC #4: HA_MQTT_TOPICS can be customized."""
        with patch.dict(os.environ, {"HA_MQTT_TOPICS": "home/+/alerts"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_TOPICS == "home/+/alerts"

    def test_mqtt_alert_user_id_loaded_from_env(self):
        """AC #4: HA_MQTT_ALERT_USER_ID is loaded from environment."""
        with patch.dict(os.environ, {"HA_MQTT_ALERT_USER_ID": "12345678"}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.HA_MQTT_ALERT_USER_ID == "12345678"


class TestMQTTPasswordMasking:
    """Test HA_MQTT_PASSWORD is properly masked in logs."""

    def test_mqtt_password_in_sensitive_vars(self):
        """AC #2: HA_MQTT_PASSWORD is in SENSITIVE_VARS list."""
        from api.config import SENSITIVE_VARS

        assert "HA_MQTT_PASSWORD" in SENSITIVE_VARS

    def test_mask_sensitive_value_masks_password(self):
        """AC #2: Password is masked correctly (show first 4 + last 4)."""
        from api.config import mask_sensitive_value

        password = "my_super_secret_password123"
        masked = mask_sensitive_value(password)

        assert masked == "my_s...d123"
        assert "secret" not in masked

    def test_mask_sensitive_value_short_password(self):
        """Short passwords are fully masked."""
        from api.config import mask_sensitive_value

        short_pass = "abc"
        masked = mask_sensitive_value(short_pass)

        assert masked == "***"


class TestValidateMQTTConfig:
    """Test validate_mqtt_config() function."""

    def test_validate_mqtt_config_disabled(self):
        """No issues when MQTT is disabled (empty broker)."""
        with patch.dict(os.environ, {"HA_MQTT_BROKER": ""}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_mqtt_config()
            assert issues == []

    def test_validate_mqtt_config_valid(self):
        """No issues when MQTT is properly configured."""
        with patch.dict(os.environ, {
            "HA_MQTT_BROKER": "192.168.1.100",
            "HA_MQTT_PORT": "1883",
            "HA_MQTT_ALERT_USER_ID": "12345678"
        }):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_mqtt_config()
            assert issues == []

    def test_validate_mqtt_config_missing_alert_user_id(self):
        """Reports issue when broker set but alert user ID missing."""
        with patch.dict(os.environ, {
            "HA_MQTT_BROKER": "192.168.1.100",
            "HA_MQTT_ALERT_USER_ID": ""
        }):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_mqtt_config()
            assert "HA_MQTT_ALERT_USER_ID required when HA_MQTT_BROKER is set" in issues

    def test_validate_mqtt_config_invalid_port(self):
        """Reports issue when port is out of range."""
        with patch.dict(os.environ, {
            "HA_MQTT_BROKER": "192.168.1.100",
            "HA_MQTT_PORT": "70000",
            "HA_MQTT_ALERT_USER_ID": "12345678"
        }):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            issues = config_module.validate_mqtt_config()
            assert any("HA_MQTT_PORT must be 1-65535" in issue for issue in issues)


class TestIsMQTTConfigured:
    """Test is_mqtt_configured() function."""

    def test_is_mqtt_configured_true_when_valid(self):
        """Returns True when MQTT is properly configured."""
        with patch.dict(os.environ, {
            "HA_MQTT_BROKER": "192.168.1.100",
            "HA_MQTT_ALERT_USER_ID": "12345678"
        }):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.is_mqtt_configured() is True

    def test_is_mqtt_configured_false_when_disabled(self):
        """Returns False when MQTT is disabled."""
        with patch.dict(os.environ, {"HA_MQTT_BROKER": ""}):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.is_mqtt_configured() is False

    def test_is_mqtt_configured_false_when_invalid(self):
        """Returns False when MQTT config is invalid."""
        with patch.dict(os.environ, {
            "HA_MQTT_BROKER": "192.168.1.100",
            "HA_MQTT_ALERT_USER_ID": ""  # Missing required field
        }):
            import importlib
            import api.config as config_module
            importlib.reload(config_module)

            assert config_module.is_mqtt_configured() is False
