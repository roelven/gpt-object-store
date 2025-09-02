"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch

from src.config import Settings, get_settings


class TestSettings:
    """Test Settings class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        settings = Settings()
        
        assert settings.app_name == "GPT Object Store API"
        assert settings.debug is False
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.database_url == "postgresql://gptstore:change-me@localhost:5432/gptstore"
        assert settings.db_pool_min_size == 1
        assert settings.db_pool_max_size == 10
        assert settings.db_command_timeout == 60
        assert settings.rate_limits == "key:60/m,write:10/m,ip:600/5m"
        assert settings.cors_origins == ["*"]
        assert settings.cors_allow_credentials is True
        assert settings.cors_allow_methods == ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        assert settings.cors_allow_headers == ["*"]
        assert settings.api_key_hash_algorithm == "sha256"
        assert settings.log_level == "INFO"
        assert settings.default_page_size == 50
        assert settings.max_page_size == 200
    
    def test_environment_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "APP_NAME": "Test API",
            "DEBUG": "true",
            "HOST": "127.0.0.1",
            "PORT": "9000",
            "DATABASE_URL": "postgresql://test:test@testhost:5432/testdb",
            "LOG_LEVEL": "DEBUG",
            "DEFAULT_PAGE_SIZE": "25",
            "MAX_PAGE_SIZE": "100"
        }
        
        with patch.dict(os.environ, env_vars):
            settings = Settings()
            
            assert settings.app_name == "Test API"
            assert settings.debug is True
            assert settings.host == "127.0.0.1"
            assert settings.port == 9000
            assert settings.database_url == "postgresql://test:test@testhost:5432/testdb"
            assert settings.log_level == "DEBUG"
            assert settings.default_page_size == 25
            assert settings.max_page_size == 100
    
    def test_cors_configuration_via_json(self):
        """Test CORS configuration via JSON arrays."""
        # Test JSON array input (pydantic-settings expects JSON for lists)
        env_vars = {
            "CORS_ORIGINS": '["http://localhost:3000", "https://example.com"]',
            "CORS_ALLOW_METHODS": '["GET", "POST", "PUT"]',
            "CORS_ALLOW_HEADERS": '["Content-Type", "Authorization"]'
        }
        
        with patch.dict(os.environ, env_vars):
            settings = Settings()
            assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
            assert settings.cors_allow_methods == ["GET", "POST", "PUT"]
            assert settings.cors_allow_headers == ["Content-Type", "Authorization"]
    
    def test_log_level_validation(self):
        """Test log level validation."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in valid_levels:
            env_vars = {"LOG_LEVEL": level.lower()}
            with patch.dict(os.environ, env_vars):
                settings = Settings()
                assert settings.log_level == level.upper()
        
        # Test invalid log level
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}):
            with pytest.raises(ValueError, match="Log level must be one of"):
                Settings()
    
    def test_get_settings_singleton(self):
        """Test that get_settings returns consistent instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should return the same instance due to module-level singleton
        assert settings1 is settings2