"""
Patient Safety Monitor - Database Connection

Manages SQLAlchemy engine and session lifecycle.
Provides connection pooling, health checks, and transaction management.

Usage:
    from database.connection import get_session, init_database
    
    # Initialize at application start
    success = init_database()
    
    # Use session in a context manager
    with get_session() as session:
        findings = session.query(Finding).all()
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from config.settings import get_settings
from database.models import Base


logger = logging.getLogger(__name__)

# Module-level engine instance
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


# =============================================================================
# Engine Management
# =============================================================================

def get_engine() -> Engine:
    """
    Get or create the database engine.
    
    Creates a connection pool with settings from configuration.
    The engine is created lazily on first access.
    
    Returns:
        SQLAlchemy Engine instance
    """
    global _engine
    
    if _engine is None:
        settings = get_settings()
        
        logger.info(
            "Creating database engine",
            extra={
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
            },
        )
        
        _engine = create_engine(
            settings.database_url,
            poolclass=QueuePool,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,  # Verify connections before use
            echo=settings.database_echo,
        )
        
        logger.debug("Database engine created")
    
    return _engine


def close_engine() -> None:
    """
    Close the database engine and all connections.
    
    Should be called at application shutdown.
    """
    global _engine, _session_factory
    
    if _engine is not None:
        logger.info("Closing database engine")
        _engine.dispose()
        _engine = None
        _session_factory = None
        logger.debug("Database engine closed")


def get_session_factory() -> sessionmaker:
    """
    Get or create the session factory.
    
    Returns:
        sessionmaker instance configured for the engine
    """
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    
    return _session_factory


# =============================================================================
# Session Management
# =============================================================================

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session in a context manager.
    
    Automatically handles commit on success and rollback on exception.
    The session is closed after the context exits.
    
    Usage:
        with get_session() as session:
            session.add(finding)
            session.commit()
    
    Yields:
        SQLAlchemy Session instance
    """
    session_factory = get_session_factory()
    session = session_factory()
    
    try:
        yield session
    except Exception:
        logger.error("Database session error, rolling back")
        session.rollback()
        raise
    finally:
        session.close()


def get_raw_session() -> Session:
    """
    Get a raw session without context management.
    
    The caller is responsible for committing, rolling back, and closing.
    Prefer get_session() context manager for most use cases.
    
    Returns:
        SQLAlchemy Session instance
    """
    session_factory = get_session_factory()
    return session_factory()


# =============================================================================
# Initialization
# =============================================================================

def init_database() -> bool:
    """
    Initialize the database connection and verify connectivity.
    
    Should be called once at application startup to:
    1. Create the engine
    2. Verify connection is working
    3. Optionally create tables (development only)
    
    Returns:
        True if initialization successful, False otherwise
    """
    try:
        engine = get_engine()
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        
        logger.info("Database connection verified")
        
        # In development, ensure tables exist
        settings = get_settings()
        if settings.is_development:
            logger.info("Development mode: ensuring tables exist")
            Base.metadata.create_all(engine)
        
        return True
        
    except Exception as e:
        logger.error(
            "Database initialization failed",
            extra={"error": str(e)},
        )
        return False


def check_database_health() -> dict:
    """
    Check database health and return status information.
    
    Returns:
        Dictionary with health check results
    """
    result = {
        "healthy": False,
        "connected": False,
        "pool_size": None,
        "pool_checked_out": None,
        "error": None,
    }
    
    try:
        engine = get_engine()
        
        # Test query
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        result["connected"] = True
        result["healthy"] = True
        
        # Pool stats
        pool = engine.pool
        result["pool_size"] = pool.size()
        result["pool_checked_out"] = pool.checkedout()
        
    except Exception as e:
        result["error"] = str(e)
        logger.error("Database health check failed", extra={"error": str(e)})
    
    return result


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "get_engine",
    "close_engine",
    "get_session",
    "get_raw_session",
    "init_database",
    "check_database_health",
]
