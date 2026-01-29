"""
REdI Patient Safety Monitor - Configuration Settings

Centralized configuration management using Pydantic Settings.
Loads configuration from environment variables and .env files.

Environment variables can be set directly or via a .env file in the project root.
All settings have sensible defaults for development, but production deployments
should explicitly set all required values.

Usage:
    from config.settings import get_settings
    
    settings = get_settings()
    print(settings.database_url)
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import bcrypt
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# Determine Project Root
# =============================================================================

def get_project_root() -> Path:
    """Get the project root directory."""
    # Start from this file's directory and go up to find the project root
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "docker-compose.yml").exists() or (current / "requirements.txt").exists():
            return current
        current = current.parent
    # Fallback to the config directory's parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = get_project_root()


# =============================================================================
# Settings Classes
# =============================================================================

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden by environment variables.
    Prefix is not used to keep variable names simple.
    
    Required settings (must be set in production):
        - DATABASE_URL
        - ANTHROPIC_API_KEY
        - ADMIN_USERNAME
        - ADMIN_PASSWORD_HASH
        - SECRET_KEY
    
    Optional settings have sensible defaults.
    """
    
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars
    )
    
    # -------------------------------------------------------------------------
    # Environment
    # -------------------------------------------------------------------------
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode (never enable in production)",
    )
    
    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql://psm_user:psm_password@localhost:7411/patient_safety_monitor",
        description="PostgreSQL connection string",
    )
    database_pool_size: int = Field(
        default=5,
        description="Connection pool size",
    )
    database_max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool size",
    )
    database_pool_timeout: int = Field(
        default=30,
        description="Seconds to wait for a connection from the pool",
    )
    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements (for debugging)",
    )
    
    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_file: Optional[str] = Field(
        default="logs/app.log",
        description="Log file path (relative to project root or absolute)",
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)",
    )
    log_max_bytes: int = Field(
        default=10_485_760,  # 10 MB
        description="Maximum log file size before rotation",
    )
    log_backup_count: int = Field(
        default=5,
        description="Number of backup log files to keep",
    )
    
    # -------------------------------------------------------------------------
    # LLM Configuration
    # -------------------------------------------------------------------------
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (fallback)",
    )
    llm_primary_provider: str = Field(
        default="claude",
        description="Primary LLM provider (claude or openai)",
    )
    llm_primary_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Primary LLM model identifier",
    )
    llm_fallback_model: str = Field(
        default="gpt-5-turbo",
        description="Fallback LLM model identifier",
    )
    llm_temperature_analysis: float = Field(
        default=0.3,
        description="Temperature for analysis tasks (lower = more deterministic)",
    )
    llm_temperature_creative: float = Field(
        default=0.7,
        description="Temperature for blog generation (higher = more creative)",
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="Maximum tokens for LLM responses",
    )
    llm_timeout_seconds: int = Field(
        default=120,
        description="Timeout for LLM API calls",
    )
    llm_max_retries: int = Field(
        default=3,
        description="Maximum retries for failed LLM API calls",
    )
    
    # -------------------------------------------------------------------------
    # Admin Dashboard
    # -------------------------------------------------------------------------
    admin_username: str = Field(
        default="admin",
        description="Admin dashboard username",
    )
    admin_password_hash: str = Field(
        default="",
        description="Bcrypt hash of admin password",
    )
    secret_key: str = Field(
        default="development-secret-key-change-in-production",
        description="Secret key for session signing and JWT token encryption",
    )
    session_expiry_hours: int = Field(
        default=24,
        description="Session expiry time in hours",
    )

    # JWT Configuration
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm (HS256, HS512, RS256, etc.)",
    )
    jwt_expiration_minutes: int = Field(
        default=60,
        description="JWT token expiration time in minutes",
    )

    # -------------------------------------------------------------------------
    # Scraping
    # -------------------------------------------------------------------------
    scrape_interval_hours: int = Field(
        default=24,
        description="Default interval between scrapes",
    )
    scrape_request_delay: float = Field(
        default=2.0,
        description="Delay between requests to respect rate limits",
    )
    scrape_timeout_seconds: int = Field(
        default=30,
        description="Timeout for web requests",
    )
    scrape_max_retries: int = Field(
        default=3,
        description="Maximum retries for failed web requests",
    )
    user_agent: str = Field(
        default="REdIPatientSafetyMonitor/1.0 (+https://github.com/patient-safety-monitor)",
        description="User agent for web requests",
    )
    
    # -------------------------------------------------------------------------
    # FTP Deployment (Hostinger)
    # -------------------------------------------------------------------------
    ftp_host: Optional[str] = Field(
        default=None,
        description="FTP hostname for blog deployment",
    )
    ftp_username: Optional[str] = Field(
        default=None,
        description="FTP username",
    )
    ftp_password: Optional[str] = Field(
        default=None,
        description="FTP password",
    )
    ftp_port: int = Field(
        default=21,
        description="FTP/SFTP port (21 for FTP, 22 for SFTP - protocol auto-detected from port)",
    )
    ftp_directory: str = Field(
        default="/public_html",
        description="Remote directory for blog files",
    )
    
    # -------------------------------------------------------------------------
    # Blog Configuration
    # -------------------------------------------------------------------------
    blog_base_url: str = Field(
        default="https://patientsafetymonitor.org",
        description="Base URL for the published blog",
    )
    
    # -------------------------------------------------------------------------
    # Paths
    # -------------------------------------------------------------------------
    data_directory: str = Field(
        default="data",
        description="Directory for storing downloaded PDFs and data",
    )
    prompts_directory: str = Field(
        default="config/prompts",
        description="Directory containing LLM prompt templates",
    )
    templates_directory: str = Field(
        default="publishing/templates",
        description="Directory containing Jinja2 templates",
    )
    output_directory: str = Field(
        default="public_html",
        description="Directory for generated static site",
    )
    
    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------
    enable_human_review: bool = Field(
        default=True,
        description="Require human review before publishing",
    )
    enable_ftp_deploy: bool = Field(
        default=False,
        description="Enable automatic FTP deployment",
    )
    enable_pdf_storage: bool = Field(
        default=True,
        description="Store local copies of PDFs",
    )
    
    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure environment is valid."""
        valid_envs = {"development", "staging", "production"}
        v_lower = v.lower()
        if v_lower not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v_lower
    
    @field_validator("llm_primary_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Ensure LLM provider is valid."""
        valid_providers = {"claude", "openai"}
        v_lower = v.lower()
        if v_lower not in valid_providers:
            raise ValueError(f"Invalid LLM provider: {v}. Must be one of {valid_providers}")
        return v_lower

    @field_validator("admin_password_hash")
    @classmethod
    def validate_password_hash(cls, v: str) -> str:
        """
        Ensure admin_password_hash is either a valid bcrypt hash or empty.

        For backward compatibility, plain text passwords are allowed but warned.
        Bcrypt hashes start with $2a$, $2b$, or $2y$.
        """
        if not v:
            return v

        # Check if it looks like a bcrypt hash
        if v.startswith(("$2a$", "$2b$", "$2y$")):
            # Validate bcrypt hash format: $2b$rounds$salt(22 chars)hash(31 chars)
            # Total length should be ~60 characters
            if len(v) < 59:
                raise ValueError(
                    "Invalid bcrypt hash format. Generate with: "
                    "python scripts/hash_password.py yourpassword"
                )
            return v

        # For backward compatibility, allow plain text but it will be handled in auth
        import warnings
        warnings.warn(
            "admin_password_hash does not appear to be a bcrypt hash. "
            "Plain text passwords are deprecated. Generate a hash with: "
            "python scripts/hash_password.py",
            DeprecationWarning,
            stacklevel=2
        )
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """
        Warn if using the default secret key.

        In production, a secure random key should be set via SECRET_KEY env var.
        """
        if v == "development-secret-key-change-in-production":
            import warnings
            # Check environment from already-validated values or env var
            env = os.environ.get("ENVIRONMENT", "development").lower()
            if env == "production":
                raise ValueError(
                    "SECRET_KEY must be set explicitly in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            warnings.warn(
                "Using default secret key. Set SECRET_KEY environment variable for production.",
                UserWarning,
                stacklevel=2
            )
        return v

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"
    
    @property
    def is_ftp_configured(self) -> bool:
        """Check if FTP deployment is fully configured."""
        return all([self.ftp_host, self.ftp_username, self.ftp_password])
    
    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return PROJECT_ROOT
    
    def get_log_file_path(self) -> Optional[Path]:
        """Get the absolute path to the log file."""
        if not self.log_file:
            return None
        log_path = Path(self.log_file)
        if log_path.is_absolute():
            return log_path
        return PROJECT_ROOT / log_path
    
    def get_data_path(self, *parts: str) -> Path:
        """Get a path within the data directory."""
        data_path = Path(self.data_directory)
        if not data_path.is_absolute():
            data_path = PROJECT_ROOT / data_path
        return data_path.joinpath(*parts)
    
    def get_prompts_path(self, filename: str) -> Path:
        """Get the path to a prompt template file."""
        prompts_path = Path(self.prompts_directory)
        if not prompts_path.is_absolute():
            prompts_path = PROJECT_ROOT / prompts_path
        return prompts_path / filename

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password to hash

        Returns:
            Bcrypt hash string

        Example:
            >>> hashed = Settings.hash_password("mypassword")
            >>> hashed.startswith("$2b$")
            True
        """
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# =============================================================================
# Settings Singleton
# =============================================================================

@lru_cache()
def get_settings() -> Settings:
    """
    Get the application settings singleton.
    
    Settings are cached after first load. To reload settings (e.g., in tests),
    call get_settings.cache_clear() first.
    
    Returns:
        Settings instance with all configuration loaded
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache, forcing reload on next access."""
    get_settings.cache_clear()


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "Settings",
    "get_settings",
    "clear_settings_cache",
    "PROJECT_ROOT",
]
