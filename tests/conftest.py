"""
Patient Safety Monitor - Test Configuration

Pytest fixtures and configuration for test suite.
Handles database compatibility issues between SQLite (for unit tests)
and PostgreSQL (for integration tests).
"""

import os
import pytest
from unittest.mock import MagicMock, patch


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_postgres: mark test as requiring PostgreSQL database",
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test",
    )


# =============================================================================
# Environment Configuration
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure environment for testing."""
    # Set test environment variables
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-not-real")
    os.environ.setdefault("ADMIN_USERNAME", "admin")
    # Use bcrypt hash for "admin" password for testing
    os.environ.setdefault("ADMIN_PASSWORD_HASH", "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.mqH0F3B.aGmD2q")
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("LOG_LEVEL", "WARNING")

    yield

    # Cleanup if needed


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.database_url = "sqlite:///:memory:"
    settings.anthropic_api_key = "sk-ant-test-key"
    settings.openai_api_key = None
    settings.admin_username = "admin"
    # Use bcrypt hash for "admin" password for testing
    settings.admin_password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.mqH0F3B.aGmD2q"
    settings.secret_key = "test-secret"
    settings.log_level = "WARNING"
    settings.environment = "test"
    settings.is_production = False
    settings.debug = True
    settings.blog_base_url = "https://test.example.com"
    settings.llm_primary_model = "claude-sonnet-4-20250514"

    with patch("config.settings.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.complete.return_value = MagicMock(
        content="Test response",
        tokens_used=100,
        cost_usd=0.001,
    )
    return client


# =============================================================================
# Database Fixtures (PostgreSQL-only tests)
# =============================================================================

def check_postgres_available():
    """Check if PostgreSQL is available for testing."""
    db_url = os.environ.get("DATABASE_URL", "")
    return db_url.startswith("postgresql://")


@pytest.fixture(scope="function")
def postgres_engine():
    """
    Create PostgreSQL engine for integration tests.
    
    Skip tests if PostgreSQL is not configured.
    """
    if not check_postgres_available():
        pytest.skip("PostgreSQL not available for testing")
    
    from sqlalchemy import create_engine
    from database.models import Base
    
    db_url = os.environ["DATABASE_URL"]
    engine = create_engine(db_url, echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    yield engine
    
    # Cleanup - drop all tables
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def postgres_session(postgres_engine):
    """Create PostgreSQL session for testing."""
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=postgres_engine)
    session = Session()
    
    yield session
    
    session.rollback()
    session.close()


# =============================================================================
# Skip Conditions
# =============================================================================

@pytest.fixture
def skip_without_postgres():
    """Skip test if PostgreSQL is not available."""
    if not check_postgres_available():
        pytest.skip("Test requires PostgreSQL database")


# =============================================================================
# Sample Data Factories
# =============================================================================

@pytest.fixture
def source_factory():
    """Factory for creating source test data."""
    def _create_source(**kwargs):
        from uuid import uuid4
        defaults = {
            "id": uuid4(),
            "code": f"test_source_{uuid4().hex[:8]}",
            "name": "Test Source",
            "country": "GB",
            "region": None,
            "base_url": "https://example.com/",
            "scraper_class": "TestScraper",
            "schedule_cron": "0 6 * * *",
            "is_active": True,
            "config_json": {},
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)
    return _create_source


@pytest.fixture
def finding_factory(source_factory):
    """Factory for creating finding test data."""
    def _create_finding(**kwargs):
        from uuid import uuid4
        from decimal import Decimal
        from database.models import FindingStatus
        
        source = kwargs.pop("source", source_factory())
        defaults = {
            "id": uuid4(),
            "source_id": source.id,
            "source": source,
            "external_id": f"finding-{uuid4().hex[:8]}",
            "title": "Test Finding",
            "source_url": "https://example.com/finding",
            "content_text": "Test content",
            "status": FindingStatus.NEW,
            "is_healthcare": None,
            "healthcare_confidence": None,
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)
    return _create_finding


@pytest.fixture
def analysis_factory(finding_factory):
    """Factory for creating analysis test data."""
    def _create_analysis(**kwargs):
        from uuid import uuid4
        from decimal import Decimal
        from database.models import LLMProvider
        
        finding = kwargs.pop("finding", finding_factory())
        defaults = {
            "id": uuid4(),
            "finding_id": finding.id,
            "finding": finding,
            "llm_provider": LLMProvider.CLAUDE,
            "llm_model": "claude-sonnet-4-20250514",
            "prompt_version": "1.0.0",
            "summary": "Test summary",
            "human_factors": {},
            "latent_hazards": [],
            "recommendations": [],
            "key_learnings": ["Test learning"],
            "tokens_input": 500,
            "tokens_output": 1000,
            "cost_usd": Decimal("0.02"),
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)
    return _create_analysis


@pytest.fixture
def post_factory(analysis_factory):
    """Factory for creating post test data."""
    def _create_post(**kwargs):
        from uuid import uuid4
        from datetime import datetime
        from database.models import PostStatus
        
        analysis = kwargs.pop("analysis", analysis_factory())
        defaults = {
            "id": uuid4(),
            "analysis_id": analysis.id,
            "analysis": analysis,
            "slug": f"test-post-{uuid4().hex[:8]}",
            "title": "Test Post",
            "content_markdown": "# Test\n\nContent",
            "content_html": "<h1>Test</h1><p>Content</p>",
            "excerpt": "Test excerpt",
            "tags": ["test", "example"],
            "status": PostStatus.DRAFT,
            "published_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return MagicMock(**defaults)
    return _create_post
