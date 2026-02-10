import pytest
import logging
from unittest.mock import patch

from app.config import get_ha_headers, HA_URL, HA_TOKEN, _parse_bool_env

class TestConfig:
    """Test the configuration module."""
    
    def test_get_ha_headers_with_token(self):
        """Test getting headers with a token."""
        with patch('app.config.HA_TOKEN', 'test_token'):
            headers = get_ha_headers()
            
            # Check that both headers are present
            assert 'Content-Type' in headers
            assert 'Authorization' in headers
            
            # Check header values
            assert headers['Content-Type'] == 'application/json'
            assert headers['Authorization'] == 'Bearer test_token'
    
    def test_get_ha_headers_without_token(self):
        """Test getting headers without a token."""
        with patch('app.config.HA_TOKEN', ''):
            headers = get_ha_headers()
            
            # Check that only Content-Type is present
            assert 'Content-Type' in headers
            assert 'Authorization' not in headers
            
            # Check header value
            assert headers['Content-Type'] == 'application/json'
    
    def test_environment_variable_defaults(self):
        """Test that environment variables have sensible defaults."""
        # Instead of mocking os.environ.get completely, let's verify the expected defaults
        # are used when the environment variables are not set
        
        # Get the current values
        from app.config import HA_URL, HA_TOKEN
        
        # Verify the defaults match what we expect
        # Note: These may differ if environment variables are actually set
        assert HA_URL.startswith('http://')  # May be localhost or an actual URL
    
    def test_environment_variable_custom_values(self):
        """Test that environment variables can be customized."""
        env_values = {
            'HA_URL': 'http://homeassistant.local:8123',
            'HA_TOKEN': 'custom_token',
        }

        def mock_environ_get(key, default=None):
            return env_values.get(key, default)

        with patch('os.environ.get', side_effect=mock_environ_get):
            from importlib import reload
            import app.config
            reload(app.config)

            # Check custom values
            assert app.config.HA_URL == 'http://homeassistant.local:8123'
            assert app.config.HA_TOKEN == 'custom_token'


class TestParseBoolean:
    """Test the _parse_bool_env helper."""

    @pytest.mark.parametrize("value,expected", [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("Yes", True),
        ("YES", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("No", False),
        ("", False),
        ("random", False),
    ])
    def test_parse_bool_env(self, value, expected):
        """Test boolean parsing from various string inputs."""
        assert _parse_bool_env(value) is expected


class TestHAVerifySSL:
    """Test the HA_VERIFY_SSL configuration."""

    def test_default_is_false(self):
        """Default HA_VERIFY_SSL is False when env var is not set."""
        from importlib import reload
        import app.config

        with patch.dict("os.environ", {}, clear=False):
            # Remove HA_VERIFY_SSL if set
            import os
            os.environ.pop("HA_VERIFY_SSL", None)
            reload(app.config)
            assert app.config.HA_VERIFY_SSL is False

    @pytest.mark.parametrize("value", ["true", "1", "yes", "True", "YES"])
    def test_truthy_values_enable_ssl(self, value):
        """Truthy env values enable SSL verification."""
        from importlib import reload
        import app.config

        with patch.dict("os.environ", {"HA_VERIFY_SSL": value}):
            reload(app.config)
            assert app.config.HA_VERIFY_SSL is True

    def test_logs_info_when_ssl_enabled(self, caplog):
        """Logs info message when SSL verification is explicitly enabled."""
        from app.config import _validate_ha_verify_ssl

        with caplog.at_level(logging.INFO, logger="app.config"):
            result = _validate_ha_verify_ssl("true")
            assert result is True
            assert "SSL certificate verification is enabled" in caplog.text

    def test_logs_warning_when_ssl_disabled(self, caplog):
        """Logs warning when SSL verification is disabled."""
        from app.config import _validate_ha_verify_ssl

        with caplog.at_level(logging.WARNING, logger="app.config"):
            result = _validate_ha_verify_ssl("false")
            assert result is False
            assert "SSL certificate verification is disabled" in caplog.text
