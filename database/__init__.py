"""
Patient Safety Monitor - Database Package

This package provides database connectivity and ORM models.

Modules:
    models: SQLAlchemy ORM models for all entities
    connection: Database engine and session management
    repository: Data access layer with CRUD operations
    
Usage:
    from database.connection import get_session, init_database
    from database.models import Source, Finding, Analysis, Post
    from database.repository import SourceRepository, FindingRepository
    
    # Initialize database
    init_database()
    
    # Use session context manager
    with get_session() as session:
        repo = SourceRepository(session)
        sources = repo.get_active_sources()
"""

from database.models import (
    Base,
    Source,
    Finding,
    Analysis,
    Post,
    AuditLog,
    FindingStatus,
    PostStatus,
    LLMProvider,
)
from database.connection import (
    get_engine,
    get_session,
    init_database,
    close_engine,
)
from database.repository import (
    SourceRepository,
    FindingRepository,
    AnalysisRepository,
    PostRepository,
    AuditLogRepository,
    UnitOfWork,
)

__all__ = [
    # Models
    "Base",
    "Source",
    "Finding",
    "Analysis",
    "Post",
    "AuditLog",
    "FindingStatus",
    "PostStatus",
    "LLMProvider",
    # Connection
    "get_engine",
    "get_session",
    "init_database",
    "close_engine",
    # Repositories
    "SourceRepository",
    "FindingRepository",
    "AnalysisRepository",
    "PostRepository",
    "AuditLogRepository",
    "UnitOfWork",
]
