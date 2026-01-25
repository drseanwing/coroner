"""
Patient Safety Monitor - Application Startup

Handles application initialization, validation, and graceful shutdown.
Ensures all dependencies are available before processing begins.

Usage:
    from startup import initialize_application, shutdown_application
    
    # At application start
    success = initialize_application()
    if not success:
        sys.exit(1)
    
    # At application shutdown
    shutdown_application()
"""

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config.settings import get_settings, Settings
from config.logging import setup_logging


logger = logging.getLogger(__name__)


@dataclass
class StartupResult:
    """Result of startup validation."""
    
    success: bool = True
    settings_valid: bool = False
    database_connected: bool = False
    llm_configured: bool = False
    sources_loaded: bool = False
    
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_error(self, message: str) -> None:
        """Add an error and mark as failed."""
        self.errors.append(message)
        self.success = False
    
    def add_warning(self, message: str) -> None:
        """Add a warning (doesn't fail startup)."""
        self.warnings.append(message)


def validate_settings() -> tuple[bool, list[str]]:
    """
    Validate application settings.
    
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    try:
        settings = get_settings()
        
        # Check required settings
        if not settings.database_url:
            errors.append("DATABASE_URL is not configured")
        
        if not settings.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is not configured")
        elif not settings.anthropic_api_key.startswith("sk-ant-"):
            errors.append("ANTHROPIC_API_KEY appears to be invalid (should start with 'sk-ant-')")
        
        if not settings.admin_username:
            errors.append("ADMIN_USERNAME is not configured")
        
        if not settings.secret_key:
            errors.append("SECRET_KEY is not configured")
        
        # Validate environment-specific settings
        if settings.is_production:
            if settings.debug:
                errors.append("DEBUG should be False in production")
            if settings.log_level == "DEBUG":
                errors.append("LOG_LEVEL should not be DEBUG in production")
        
        # Check FTP configuration if in production
        if settings.is_production and not settings.is_ftp_configured:
            # This is a warning, not an error
            logger.warning("FTP deployment not configured")
        
        return len(errors) == 0, errors
        
    except Exception as e:
        return False, [f"Failed to load settings: {e}"]


def validate_database() -> tuple[bool, str]:
    """
    Validate database connection.
    
    Returns:
        Tuple of (is_connected, message)
    """
    try:
        from database.connection import init_database
        
        if init_database():
            return True, "Database connection successful"
        else:
            return False, "Database initialization failed"
            
    except ImportError as e:
        return False, f"Database module import failed: {e}"
    except Exception as e:
        return False, f"Database validation failed: {e}"


def validate_llm_client() -> tuple[bool, str]:
    """
    Validate LLM client configuration.
    
    Note: Does not make an actual API call, just validates configuration.
    
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        settings = get_settings()
        
        if settings.anthropic_api_key:
            # Could add a test API call here, but that costs money
            return True, "Anthropic API key configured"
        
        if settings.openai_api_key:
            return True, "OpenAI API key configured (fallback)"
        
        return False, "No LLM API keys configured"
        
    except Exception as e:
        return False, f"LLM validation failed: {e}"


def load_sources_config() -> tuple[bool, int, str]:
    """
    Load and validate sources configuration.
    
    Returns:
        Tuple of (is_valid, source_count, message)
    """
    try:
        import yaml
        from pathlib import Path
        
        config_path = Path("config/sources.yaml")
        
        if not config_path.exists():
            return False, 0, f"Sources config not found: {config_path}"
        
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        sources = config.get("sources", [])
        active_sources = [s for s in sources if s.get("is_active", False)]
        
        if not sources:
            return False, 0, "No sources defined in configuration"
        
        return True, len(active_sources), f"Loaded {len(sources)} sources ({len(active_sources)} active)"
        
    except yaml.YAMLError as e:
        return False, 0, f"Invalid YAML in sources config: {e}"
    except Exception as e:
        return False, 0, f"Failed to load sources: {e}"


def initialize_application(
    skip_database: bool = False,
    skip_llm: bool = False,
) -> StartupResult:
    """
    Initialize the application and validate all dependencies.
    
    Should be called once at application startup.
    
    Args:
        skip_database: Skip database validation (for testing)
        skip_llm: Skip LLM validation (for testing)
        
    Returns:
        StartupResult with validation details
    """
    result = StartupResult()
    
    # Step 1: Setup logging first
    try:
        setup_logging()
        logger.info("=" * 60)
        logger.info("Patient Safety Monitor - Starting")
        logger.info("=" * 60)
    except Exception as e:
        result.add_error(f"Logging setup failed: {e}")
        return result
    
    # Step 2: Validate settings
    logger.info("Validating settings...")
    settings_valid, settings_errors = validate_settings()
    result.settings_valid = settings_valid
    
    if not settings_valid:
        for error in settings_errors:
            result.add_error(error)
            logger.error(f"Settings error: {error}")
    else:
        settings = get_settings()
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Log level: {settings.log_level}")
    
    # Step 3: Validate database
    if not skip_database:
        logger.info("Validating database connection...")
        db_valid, db_message = validate_database()
        result.database_connected = db_valid
        
        if db_valid:
            logger.info(f"Database: {db_message}")
        else:
            result.add_error(f"Database: {db_message}")
            logger.error(f"Database: {db_message}")
    else:
        logger.info("Database validation skipped")
        result.database_connected = True
    
    # Step 4: Validate LLM client
    if not skip_llm:
        logger.info("Validating LLM configuration...")
        llm_valid, llm_message = validate_llm_client()
        result.llm_configured = llm_valid
        
        if llm_valid:
            logger.info(f"LLM: {llm_message}")
        else:
            result.add_error(f"LLM: {llm_message}")
            logger.error(f"LLM: {llm_message}")
    else:
        logger.info("LLM validation skipped")
        result.llm_configured = True
    
    # Step 5: Load sources configuration
    logger.info("Loading sources configuration...")
    sources_valid, source_count, sources_message = load_sources_config()
    result.sources_loaded = sources_valid
    
    if sources_valid:
        logger.info(f"Sources: {sources_message}")
    else:
        result.add_warning(f"Sources: {sources_message}")
        logger.warning(f"Sources: {sources_message}")
    
    # Summary
    logger.info("-" * 60)
    if result.success:
        logger.info("Startup validation PASSED")
    else:
        logger.error("Startup validation FAILED")
        for error in result.errors:
            logger.error(f"  - {error}")
    
    if result.warnings:
        logger.warning(f"Warnings: {len(result.warnings)}")
        for warning in result.warnings:
            logger.warning(f"  - {warning}")
    
    logger.info("-" * 60)
    
    return result


def shutdown_application() -> None:
    """
    Perform graceful application shutdown.
    
    Should be called when the application is stopping.
    """
    logger.info("Shutting down Patient Safety Monitor...")
    
    try:
        from database.connection import close_engine
        close_engine()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
    
    logger.info("Shutdown complete")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main() -> int:
    """
    Main entry point for validation script.
    
    Can be run standalone to check configuration:
        python -m startup
        
    Returns:
        0 on success, 1 on failure
    """
    result = initialize_application()
    
    if result.success:
        print("\nâœ“ All validations passed")
        return 0
    else:
        print("\nâœ— Validation failed:")
        for error in result.errors:
            print(f"  - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
