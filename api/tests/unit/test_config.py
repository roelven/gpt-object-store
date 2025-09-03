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
        assert settings.api_url == "http://localhost:8000"
    
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
            "MAX_PAGE_SIZE": "100",
            "API_URL": "https://api.example.com"
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
            assert settings.api_url == "https://api.example.com"
    
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
    
    def test_api_url_field_exists(self):
        """Test that Settings class has api_url field (regression test)."""
        settings = Settings()
        
        # Should have api_url attribute - this was missing and caused AttributeError
        assert hasattr(settings, 'api_url'), "Settings must have api_url field"
        
        # Should not raise AttributeError when accessed
        try:
            api_url = settings.api_url
            assert isinstance(api_url, str), "api_url should be a string"
        except AttributeError as e:
            pytest.fail(f"Settings.api_url should not raise AttributeError: {e}")
    
    def test_api_url_environment_mapping(self):
        """Test that API_URL environment variable maps to api_url field."""
        test_urls = [
            "https://api.production.com",
            "https://gpt-backend.w22.io",
            "http://localhost:3000",
            "https://api.staging.example.com"
        ]
        
        for test_url in test_urls:
            with patch.dict(os.environ, {"API_URL": test_url}):
                settings = Settings()
                assert settings.api_url == test_url, f"API_URL={test_url} should map to api_url field"
    
    def test_api_url_default_value(self):
        """Test api_url has reasonable default value."""
        # Ensure no API_URL env var interferes
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Default should be localhost for development
            assert settings.api_url == "http://localhost:8000"
            assert settings.api_url.startswith("http"), "Default api_url should be a valid URL"
    
    def test_settings_regression_openapi_server_url(self):
        """Test regression: Settings.api_url is accessible for OpenAPI server URL generation."""
        # This test ensures the AttributeError that caused OpenAPI /openapi.json to fail is fixed
        
        with patch.dict(os.environ, {"API_URL": "https://test.example.com"}):
            settings = Settings()
            
            # This should work without AttributeError (the original bug)
            server_url = settings.api_url
            assert server_url == "https://test.example.com"
            
            # Simulate the OpenAPI spec generation that was failing
            openapi_server_config = {
                "url": settings.api_url,
                "description": "Production server"
            }
            
            assert openapi_server_config["url"] == "https://test.example.com"