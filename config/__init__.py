"""
Patient Safety Monitor - Configuration Package

This package provides configuration management for the application.

Modules:
    settings: Environment-based configuration using Pydantic
    logging: Structured logging with file output
    
Usage:
    from config.settings import get_settings
    from config.logging import setup_logging, get_logger
    
    settings = get_settings()
    setup_logging()
    logger = get_logger(__name__)
"""

from config.settings import get_settings, Settings
from config.logging import setup_logging, get_logger

__all__ = [
    "get_settings",
    "Settings",
    "setup_logging",
    "get_logger",
]
