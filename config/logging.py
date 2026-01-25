"""
Patient Safety Monitor - Logging Configuration

Provides structured JSON logging with file rotation, sensitive data censoring,
and contextual information. Designed for production debugging and monitoring.

Features:
    - JSON structured logging for easy parsing
    - Automatic file rotation by size
    - Sensitive data censoring (API keys, passwords)
    - Contextual extras (request IDs, source codes)
    - Console and file handlers

Usage:
    from config.logging import setup_logging, get_logger
    
    # Initialize at application start
    setup_logging()
    
    # Get a logger for a module
    logger = get_logger(__name__)
    logger.info("Operation completed", extra={"finding_id": "123"})
"""

import json
import logging
import logging.handlers
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.settings import get_settings


# =============================================================================
# Sensitive Data Patterns
# =============================================================================

# Patterns to censor in log output
SENSITIVE_PATTERNS = [
    (re.compile(r'(sk-ant-api\d+-)[A-Za-z0-9_-]+'), r'\1[REDACTED]'),  # Anthropic API keys
    (re.compile(r'(sk-)[A-Za-z0-9_-]{20,}'), r'\1[REDACTED]'),  # OpenAI API keys
    (re.compile(r'(password["\']?\s*[:=]\s*["\']?)[^"\'&\s]+', re.I), r'\1[REDACTED]'),
    (re.compile(r'(api_key["\']?\s*[:=]\s*["\']?)[^"\'&\s]+', re.I), r'\1[REDACTED]'),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\']?)[^"\'&\s]+', re.I), r'\1[REDACTED]'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\']?)[^"\'&\s]+', re.I), r'\1[REDACTED]'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9._-]+', re.I), r'\1[REDACTED]'),
]


def censor_sensitive_data(text: str) -> str:
    """
    Remove sensitive data from text using pattern matching.
    
    Args:
        text: Text that may contain sensitive data
        
    Returns:
        Text with sensitive data redacted
    """
    if not isinstance(text, str):
        return text
    
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


# =============================================================================
# Custom Formatter
# =============================================================================

class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.
    
    Outputs each log record as a single JSON line with:
        - timestamp (ISO 8601)
        - level
        - logger name
        - message
        - extra fields from the record
        - exception info if present
    """
    
    # Fields that are part of LogRecord but shouldn't be in extras
    RESERVED_ATTRS = {
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "exc_info", "exc_text", "thread", "threadName",
        "taskName", "message",
    }
    
    def __init__(self, include_extras: bool = True, censor_sensitive: bool = True):
        """
        Initialize the formatter.
        
        Args:
            include_extras: Include extra fields from the log record
            censor_sensitive: Censor sensitive data in output
        """
        super().__init__()
        self.include_extras = include_extras
        self.censor_sensitive = censor_sensitive
    
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON."""
        # Build the base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add location info for errors and above
        if record.levelno >= logging.WARNING:
            log_entry["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }
        
        # Add extra fields
        if self.include_extras:
            extras = {}
            for key, value in record.__dict__.items():
                if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                    try:
                        # Ensure value is JSON serializable
                        json.dumps(value)
                        extras[key] = value
                    except (TypeError, ValueError):
                        extras[key] = str(value)
            
            if extras:
                log_entry["extra"] = extras
        
        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }
        
        # Convert to JSON string
        json_str = json.dumps(log_entry, default=str, ensure_ascii=False)
        
        # Censor sensitive data if enabled
        if self.censor_sensitive:
            json_str = censor_sensitive_data(json_str)
        
        return json_str


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter with colors.
    
    Format: TIMESTAMP | LEVEL | LOGGER | MESSAGE [extras]
    """
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"
    
    RESERVED_ATTRS = JSONFormatter.RESERVED_ATTRS
    
    def __init__(self, use_colors: bool = True, censor_sensitive: bool = True):
        """
        Initialize the formatter.
        
        Args:
            use_colors: Use ANSI color codes in output
            censor_sensitive: Censor sensitive data in output
        """
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
        self.censor_sensitive = censor_sensitive
    
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record for console output."""
        timestamp = datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
        
        level = record.levelname
        if self.use_colors:
            color = self.COLORS.get(level, "")
            level = f"{color}{level:8}{self.RESET}"
        else:
            level = f"{level:8}"
        
        # Get logger name (shortened)
        logger_name = record.name
        if len(logger_name) > 25:
            logger_name = "..." + logger_name[-22:]
        
        message = record.getMessage()
        
        # Add extras if present
        extras = []
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                extras.append(f"{key}={value}")
        
        extra_str = ""
        if extras:
            extra_str = f" [{', '.join(extras)}]"
        
        output = f"{timestamp} | {level} | {logger_name:25} | {message}{extra_str}"
        
        # Add exception if present
        if record.exc_info and record.exc_info[0] is not None:
            output += "\n" + "".join(traceback.format_exception(*record.exc_info))
        
        # Censor sensitive data
        if self.censor_sensitive:
            output = censor_sensitive_data(output)
        
        return output


# =============================================================================
# Log Setup Functions
# =============================================================================

def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
) -> None:
    """
    Configure application logging.
    
    Sets up both console and file handlers with appropriate formatters.
    Should be called once at application startup.
    
    Args:
        log_level: Override settings log level
        log_file: Override settings log file path
        log_format: Override settings log format (json or text)
    """
    settings = get_settings()
    
    # Determine configuration
    level = getattr(logging, (log_level or settings.log_level).upper())
    file_path = log_file or settings.log_file
    format_type = (log_format or settings.log_format).lower()
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    if format_type == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())
    
    root_logger.addHandler(console_handler)
    
    # File handler (if configured)
    if file_path:
        file_path_obj = Path(file_path)
        
        # Handle relative paths
        if not file_path_obj.is_absolute():
            file_path_obj = settings.project_root / file_path_obj
        
        # Ensure directory exists
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            file_path_obj,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        
        # Always use JSON for file logging (easier to parse)
        file_handler.setFormatter(JSONFormatter())
        
        root_logger.addHandler(file_handler)
    
    # Configure third-party loggers to be less verbose
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    
    # Log startup
    logger = get_logger(__name__)
    logger.info(
        "Logging initialized",
        extra={
            "level": settings.log_level,
            "file": str(file_path) if file_path else None,
            "format": format_type,
        },
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    
    This is a convenience function that ensures consistent logger retrieval.
    
    Args:
        name: Logger name, typically __name__
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding contextual information to logs.
    
    Usage:
        with LogContext(request_id="abc123", source="uk_pfd"):
            logger.info("Processing")  # Will include request_id and source
    """
    
    _context: dict[str, Any] = {}
    
    def __init__(self, **kwargs: Any):
        """
        Initialize log context with key-value pairs.
        
        Args:
            **kwargs: Context fields to add to log records
        """
        self.fields = kwargs
        self.previous: dict[str, Any] = {}
    
    def __enter__(self) -> "LogContext":
        """Enter context and add fields."""
        self.previous = LogContext._context.copy()
        LogContext._context.update(self.fields)
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Exit context and restore previous fields."""
        LogContext._context = self.previous
    
    @classmethod
    def get_context(cls) -> dict[str, Any]:
        """Get current context fields."""
        return cls._context.copy()


# =============================================================================
# Logging Filter for Context
# =============================================================================

class ContextFilter(logging.Filter):
    """Filter that adds context fields to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to the record."""
        for key, value in LogContext.get_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "setup_logging",
    "get_logger",
    "LogContext",
    "JSONFormatter",
    "ConsoleFormatter",
    "censor_sensitive_data",
]
