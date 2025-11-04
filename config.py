"""
Configuration management for VADG API.
Handles environment variables, settings, and configuration validation.
"""

import os
from typing import List, Optional, Dict, Any
from pydantic import BaseSettings, Field, validator
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings with validation."""
    
    # API Configuration
    app_name: str = Field(default="VADG API", description="Application name")
    app_version: str = Field(default="2.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    reload: bool = Field(default=False, description="Auto-reload on changes")
    
    # CORS Configuration
    allowed_origins: List[str] = Field(
        default=[
            "https://vadg.in",
            "https://www.vadg.in",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174"
        ],
        description="Allowed CORS origins"
    )
    
    # AI Configuration
    google_api_key: Optional[str] = Field(default=None, description="Google AI API key")
    ai_model: str = Field(default="gemini-2.0-flash", description="AI model name")
    ai_timeout: int = Field(default=30, description="AI request timeout in seconds")
    
    # Database Configuration (for future use)
    database_url: Optional[str] = Field(default=None, description="Database URL")
    
    # Security Configuration
    secret_key: str = Field(default="your-secret-key-change-in-production", description="Secret key")
    access_token_expire_minutes: int = Field(default=30, description="Token expiration time")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # Session Configuration
    session_timeout: int = Field(default=3600, description="Session timeout in seconds")
    max_sessions: int = Field(default=1000, description="Maximum concurrent sessions")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format")
    
    # Health Check Configuration
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    
    @validator("allowed_origins", pre=True)
    def parse_allowed_origins(cls, v):
        """Parse allowed origins from environment variable or use default."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("google_api_key")
    def validate_google_api_key(cls, v):
        """Validate Google API key format."""
        if v and not v.startswith("AIza"):
            raise ValueError("Invalid Google API key format")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


def get_cors_origins() -> List[str]:
    """Get CORS allowed origins."""
    return settings.allowed_origins


def is_development() -> bool:
    """Check if running in development mode."""
    return settings.debug or os.getenv("ENVIRONMENT", "development").lower() == "development"


def is_production() -> bool:
    """Check if running in production mode."""
    return not is_development()


def get_ai_config() -> Dict[str, Any]:
    """Get AI configuration."""
    return {
        "api_key": settings.google_api_key,
        "model": settings.ai_model,
        "timeout": settings.ai_timeout,
        "available": bool(settings.google_api_key)
    }


def get_security_config() -> Dict[str, Any]:
    """Get security configuration."""
    return {
        "secret_key": settings.secret_key,
        "token_expire_minutes": settings.access_token_expire_minutes,
        "rate_limit_requests": settings.rate_limit_requests,
        "rate_limit_window": settings.rate_limit_window
    }


def get_session_config() -> Dict[str, Any]:
    """Get session configuration."""
    return {
        "timeout": settings.session_timeout,
        "max_sessions": settings.max_sessions
    }


def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration."""
    return {
        "level": settings.log_level,
        "format": settings.log_format
    }


# Environment-specific configurations
def get_environment_config() -> Dict[str, Any]:
    """Get environment-specific configuration."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    configs = {
        "development": {
            "debug": True,
            "reload": True,
            "log_level": "DEBUG",
            "cors_origins": [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174"
            ]
        },
        "staging": {
            "debug": False,
            "reload": False,
            "log_level": "INFO",
            "cors_origins": [
                "https://staging.vadg.in",
                "https://vadg-staging.netlify.app"
            ]
        },
        "production": {
            "debug": False,
            "reload": False,
            "log_level": "WARNING",
            "cors_origins": [
                "https://vadg.in",
                "https://www.vadg.in"
            ]
        }
    }
    
    return configs.get(env, configs["development"])
