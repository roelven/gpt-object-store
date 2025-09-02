"""Configuration management for GPT Object Store API."""

import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application settings
    app_name: str = "GPT Object Store API"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database settings
    database_url: str = "postgresql://gptstore:change-me@localhost:5432/gptstore"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_command_timeout: int = 60
    
    # Rate limiting settings
    rate_limits: str = "key:60/m,write:10/m,ip:600/5m"
    
    # CORS settings
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_allow_headers: List[str] = ["*"]
    
    # Security settings
    api_key_hash_algorithm: str = "sha256"
    
    # Logging settings
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Pagination settings
    default_page_size: int = 50
    max_page_size: int = 200
    
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
        "env_parse_none_str": True,
    }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings