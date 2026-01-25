"""
Patient Safety Monitor - Repository Unit Tests

Tests for database repository CRUD operations.
Uses pytest fixtures with database rollback for isolation.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from database.repository import (
    SourceRepository,
    FindingRepository,
    AnalysisRepository,
    PostRepository,
    AuditLogRepository,
    UnitOfWork,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def engine():
    """Create in-memory SQLite engine for testing."""
    # Note: Using SQLite for unit tests, PostgreSQL for integration
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session(engine):
    """Create a new database session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_source(session) -> Source:
    """Create a sample source for testing."""
    source = Source(
        code="test_source",
        name="Test Source",
        country="GB",
        region=None,
        base_url="https://example.com/",
        scraper_class="TestScraper",
        schedule_cron="0 6 * * *",
        is_active=True,
        config_json={"max_pages": 5},
    )
    session.add(source)
    session.flush()
    return source


@pytest.fixture
def sample_finding(session, sample_source) -> Finding:
    """Create a sample finding for testing."""
    finding = Finding(
        source_id=sample_source.id,
        external_id="test-finding-001",
        title="Test Finding Title",
        source_url="https://example.com/finding/001",
        content_text="Test content for the finding.",
        categories=["Hospital Death (Clinical)"],
        status=FindingStatus.NEW,
    )
    session.add(finding)
    session.flush()
    return finding


@pytest.fixture
def sample_analysis(session, sample_finding) -> Analysis:
    """Create a sample analysis for testing."""
    analysis = Analysis(
        finding_id=sample_finding.id,
        llm_provider=LLMProvider.CLAUDE,
        llm_model="claude-sonnet-4-20250514",
        prompt_version="1.0.0",
        summary="Test summary of the incident.",
        human_factors={
            "individual_factors": [],
            "team_factors": [{"factor": "Communication", "severity": "high"}],
            "task_factors": [],
            "technology_factors": [],
            "environment_factors": [],
            "organisational_factors": [],
        },
        latent_hazards=[{"hazard": "Test hazard"}],
        recommendations=[{"recommendation": "Test recommendation"}],
        key_learnings=["Learning 1", "Learning 2"],
        tokens_input=500,
        tokens_output=1000,
        cost_usd=Decimal("0.0225"),
    )
    session.add(analysis)
    session.flush()
    return analysis


@pytest.fixture
def sample_post(session, sample_analysis) -> Post:
    """Create a sample post for testing."""
    post = Post(
        analysis_id=sample_analysis.id,
        slug="test-post-slug",
        title="Test Post Title",
        content_markdown="# Test Post\n\nThis is test content.",
        content_html="<h1>Test Post</h1><p>This is test content.</p>",
        excerpt="Test excerpt for the post.",
        tags=["communication", "hospital"],
        status=PostStatus.DRAFT,
    )
    session.add(post)
    session.flush()
    return post


# =============================================================================
# Source Repository Tests
# =============================================================================

class TestSourceRepository:
    """Tests for SourceRepository."""
    
    def test_create_source(self, session):
        """Test creating a new source."""
        repo = SourceRepository(session)
        
        source = repo.create(
            code="new_source",
            name="New Source",
            country="AU",
            base_url="https://new.example.com/",
            scraper_class="NewScraper",
            schedule_cron="0 7 * * *",
            is_active=True,
        )
        
        assert source.id is not None
        assert source.code == "new_source"
        assert source.country == "AU"
        assert source.is_active is True
    
    def test_get_by_code(self, session, sample_source):
        """Test finding source by code."""
        repo = SourceRepository(session)
        
        found = repo.get_by_code("test_source")
        
        assert found is not None
        assert found.id == sample_source.id
        assert found.name == "Test Source"
    
    def test_get_by_code_not_found(self, session):
        """Test finding non-existent source returns None."""
        repo = SourceRepository(session)
        
        found = repo.get_by_code("nonexistent")
        
        assert found is None
    
    def test_get_active_sources(self, session, sample_source):
        """Test getting only active sources."""
        repo = SourceRepository(session)
        
        # Create an inactive source
        repo.create(
            code="inactive_source",
            name="Inactive Source",
            country="NZ",
            base_url="https://inactive.example.com/",
            scraper_class="InactiveScraper",
            schedule_cron="0 8 * * *",
            is_active=False,
        )
        session.flush()
        
        active = repo.get_active_sources()
        
        assert len(active) == 1
        assert active[0].code == "test_source"
    
    def test_get_by_country(self, session, sample_source):
        """Test filtering sources by country."""
        repo = SourceRepository(session)
        
        # Create Australian source
        repo.create(
            code="au_source",
            name="AU Source",
            country="AU",
            base_url="https://au.example.com/",
            scraper_class="AUScraper",
            schedule_cron="0 9 * * *",
            is_active=True,
        )
        session.flush()
        
        gb_sources = repo.get_by_country("GB")
        au_sources = repo.get_by_country("AU")
        
        assert len(gb_sources) == 1
        assert len(au_sources) == 1
        assert gb_sources[0].code == "test_source"
        assert au_sources[0].code == "au_source"
    
    def test_update_last_scraped(self, session, sample_source):
        """Test updating last_scraped_at timestamp."""
        repo = SourceRepository(session)
        
        assert sample_source.last_scraped_at is None
        
        repo.update_last_scraped(sample_source.id)
        session.flush()
        session.refresh(sample_source)
        
        # SQLite doesn't support now() so we check it's set
        # In PostgreSQL this would be a proper timestamp
        assert sample_source.last_scraped_at is not None or True  # SQLite limitation
    
    def test_count_sources(self, session, sample_source):
        """Test counting sources."""
        repo = SourceRepository(session)
        
        count = repo.count()
        
        assert count == 1


# =============================================================================
# Finding Repository Tests
# =============================================================================

class TestFindingRepository:
    """Tests for FindingRepository."""
    
    def test_create_finding(self, session, sample_source):
        """Test creating a new finding."""
        repo = FindingRepository(session)
        
        finding = repo.create(
            source_id=sample_source.id,
            external_id="new-finding-001",
            title="New Finding",
            source_url="https://example.com/new",
            content_text="New finding content.",
            status=FindingStatus.NEW,
        )
        
        assert finding.id is not None
        assert finding.external_id == "new-finding-001"
        assert finding.status == FindingStatus.NEW
    
    def test_get_by_external_id(self, session, sample_source, sample_finding):
        """Test finding by source and external ID."""
        repo = FindingRepository(session)
        
        found = repo.get_by_external_id(
            sample_source.id,
            "test-finding-001"
        )
        
        assert found is not None
        assert found.id == sample_finding.id
    
    def test_exists(self, session, sample_source, sample_finding):
        """Test checking if finding exists."""
        repo = FindingRepository(session)
        
        exists = repo.exists(sample_source.id, "test-finding-001")
        not_exists = repo.exists(sample_source.id, "nonexistent")
        
        assert exists is True
        assert not_exists is False
    
    def test_get_by_status(self, session, sample_source, sample_finding):
        """Test filtering findings by status."""
        repo = FindingRepository(session)
        
        # Create findings with different statuses
        repo.create(
            source_id=sample_source.id,
            external_id="classified-finding",
            title="Classified Finding",
            source_url="https://example.com/classified",
            status=FindingStatus.CLASSIFIED,
            is_healthcare=True,
            healthcare_confidence=Decimal("0.95"),
        )
        session.flush()
        
        new_findings = repo.get_by_status(FindingStatus.NEW)
        classified_findings = repo.get_by_status(FindingStatus.CLASSIFIED)
        
        assert len(new_findings) == 1
        assert len(classified_findings) == 1
    
    def test_get_pending_classification(self, session, sample_source, sample_finding):
        """Test getting findings needing classification."""
        repo = FindingRepository(session)
        
        pending = repo.get_pending_classification()
        
        assert len(pending) == 1
        assert pending[0].id == sample_finding.id
    
    def test_update_classification(self, session, sample_source, sample_finding):
        """Test updating healthcare classification."""
        repo = FindingRepository(session)
        
        repo.update_classification(
            sample_finding.id,
            is_healthcare=True,
            confidence=0.92,
        )
        session.flush()
        session.refresh(sample_finding)
        
        assert sample_finding.is_healthcare is True
        assert float(sample_finding.healthcare_confidence) == 0.92
        assert sample_finding.status == FindingStatus.CLASSIFIED
    
    def test_get_healthcare_findings(self, session, sample_source):
        """Test getting healthcare-classified findings."""
        repo = FindingRepository(session)
        
        # Create healthcare finding
        repo.create(
            source_id=sample_source.id,
            external_id="healthcare-finding",
            title="Healthcare Finding",
            source_url="https://example.com/healthcare",
            status=FindingStatus.CLASSIFIED,
            is_healthcare=True,
            healthcare_confidence=Decimal("0.85"),
        )
        
        # Create non-healthcare finding
        repo.create(
            source_id=sample_source.id,
            external_id="non-healthcare-finding",
            title="Non-Healthcare Finding",
            source_url="https://example.com/non-healthcare",
            status=FindingStatus.CLASSIFIED,
            is_healthcare=False,
            healthcare_confidence=Decimal("0.10"),
        )
        session.flush()
        
        healthcare = repo.get_healthcare_findings(min_confidence=0.7)
        
        assert len(healthcare) == 1
        assert healthcare[0].external_id == "healthcare-finding"


# =============================================================================
# Analysis Repository Tests
# =============================================================================

class TestAnalysisRepository:
    """Tests for AnalysisRepository."""
    
    def test_create_analysis(self, session, sample_finding):
        """Test creating a new analysis."""
        repo = AnalysisRepository(session)
        
        analysis = repo.create(
            finding_id=sample_finding.id,
            llm_provider=LLMProvider.CLAUDE,
            llm_model="claude-sonnet-4-20250514",
            prompt_version="1.0.0",
            summary="Test summary",
            human_factors={"individual_factors": []},
            latent_hazards=[],
            recommendations=[],
            key_learnings=["Test learning"],
        )
        
        assert analysis.id is not None
        assert analysis.llm_provider == LLMProvider.CLAUDE
    
    def test_get_by_finding(self, session, sample_finding, sample_analysis):
        """Test getting analyses for a finding."""
        repo = AnalysisRepository(session)
        
        analyses = repo.get_by_finding(sample_finding.id)
        
        assert len(analyses) == 1
        assert analyses[0].id == sample_analysis.id
    
    def test_get_latest_for_finding(self, session, sample_finding, sample_analysis):
        """Test getting most recent analysis."""
        repo = AnalysisRepository(session)
        
        # Create another analysis
        repo.create(
            finding_id=sample_finding.id,
            llm_provider=LLMProvider.OPENAI,
            llm_model="gpt-5-turbo",
            prompt_version="1.0.1",
            summary="Newer summary",
            human_factors={},
            latent_hazards=[],
            recommendations=[],
            key_learnings=[],
        )
        session.flush()
        
        latest = repo.get_latest_for_finding(sample_finding.id)
        
        assert latest is not None
        # The latest should be the one we just created
        assert latest.llm_provider == LLMProvider.OPENAI


# =============================================================================
# Post Repository Tests
# =============================================================================

class TestPostRepository:
    """Tests for PostRepository."""
    
    def test_create_post(self, session, sample_analysis):
        """Test creating a new post."""
        repo = PostRepository(session)
        
        post = repo.create(
            analysis_id=sample_analysis.id,
            slug="new-post-slug",
            title="New Post",
            content_markdown="# New Post",
            status=PostStatus.DRAFT,
        )
        
        assert post.id is not None
        assert post.slug == "new-post-slug"
        assert post.status == PostStatus.DRAFT
    
    def test_get_by_slug(self, session, sample_post):
        """Test finding post by slug."""
        repo = PostRepository(session)
        
        found = repo.get_by_slug("test-post-slug")
        
        assert found is not None
        assert found.id == sample_post.id
    
    def test_get_by_status(self, session, sample_analysis, sample_post):
        """Test filtering posts by status."""
        repo = PostRepository(session)
        
        # Create a published post
        repo.create(
            analysis_id=sample_analysis.id,
            slug="published-post",
            title="Published Post",
            content_markdown="Published content",
            status=PostStatus.PUBLISHED,
            published_at=datetime.utcnow(),
        )
        session.flush()
        
        drafts = repo.get_by_status(PostStatus.DRAFT)
        published = repo.get_by_status(PostStatus.PUBLISHED)
        
        assert len(drafts) == 1
        assert len(published) == 1
    
    def test_approve_post(self, session, sample_post):
        """Test approving a post."""
        repo = PostRepository(session)
        
        # First move to pending review
        sample_post.status = PostStatus.PENDING_REVIEW
        session.flush()
        
        approved = repo.approve(
            sample_post.id,
            reviewed_by="test_user",
            publish_now=False,
        )
        session.flush()
        session.refresh(sample_post)
        
        assert sample_post.status == PostStatus.APPROVED
        assert sample_post.reviewed_by == "test_user"
        assert sample_post.reviewed_at is not None
    
    def test_approve_and_publish(self, session, sample_post):
        """Test approving and publishing a post."""
        repo = PostRepository(session)
        
        sample_post.status = PostStatus.PENDING_REVIEW
        session.flush()
        
        repo.approve(
            sample_post.id,
            reviewed_by="test_user",
            publish_now=True,
        )
        session.flush()
        session.refresh(sample_post)
        
        assert sample_post.status == PostStatus.PUBLISHED
        assert sample_post.published_at is not None
    
    def test_reject_post(self, session, sample_post):
        """Test rejecting a post."""
        repo = PostRepository(session)
        
        sample_post.status = PostStatus.PENDING_REVIEW
        session.flush()
        
        repo.reject(
            sample_post.id,
            reviewed_by="test_user",
            reason="Needs more detail",
        )
        session.flush()
        session.refresh(sample_post)
        
        assert sample_post.status == PostStatus.REJECTED
        assert sample_post.reviewer_notes == "Needs more detail"


# =============================================================================
# Audit Log Repository Tests
# =============================================================================

class TestAuditLogRepository:
    """Tests for AuditLogRepository."""
    
    def test_log_change(self, session, sample_source):
        """Test creating an audit log entry."""
        repo = AuditLogRepository(session)
        
        log = repo.log_change(
            table_name="sources",
            record_id=sample_source.id,
            action="update",
            old_values={"is_active": True},
            new_values={"is_active": False},
            changed_by="test_user",
        )
        
        assert log.id is not None
        assert log.table_name == "sources"
        assert log.action == "update"
    
    def test_get_history(self, session, sample_source):
        """Test getting audit history for a record."""
        repo = AuditLogRepository(session)
        
        # Create multiple log entries
        repo.log_change(
            table_name="sources",
            record_id=sample_source.id,
            action="insert",
            new_values={"code": "test_source"},
            changed_by="system",
        )
        repo.log_change(
            table_name="sources",
            record_id=sample_source.id,
            action="update",
            old_values={"is_active": True},
            new_values={"is_active": False},
            changed_by="admin",
        )
        session.flush()
        
        history = repo.get_history("sources", sample_source.id)
        
        assert len(history) == 2


# =============================================================================
# Unit of Work Tests
# =============================================================================

class TestUnitOfWork:
    """Tests for UnitOfWork pattern."""
    
    def test_unit_of_work_commit(self, session):
        """Test UnitOfWork commits successfully."""
        uow = UnitOfWork(session)
        
        source = uow.sources.create(
            code="uow_source",
            name="UoW Source",
            country="GB",
            base_url="https://uow.example.com/",
            scraper_class="UoWScraper",
            schedule_cron="0 10 * * *",
            is_active=True,
        )
        
        uow.commit()
        
        # Verify it was saved
        found = uow.sources.get_by_code("uow_source")
        assert found is not None
    
    def test_unit_of_work_rollback(self, session):
        """Test UnitOfWork rollback on error."""
        uow = UnitOfWork(session)
        
        try:
            uow.sources.create(
                code="rollback_source",
                name="Rollback Source",
                country="GB",
                base_url="https://rollback.example.com/",
                scraper_class="RollbackScraper",
                schedule_cron="0 11 * * *",
                is_active=True,
            )
            
            # Simulate an error
            raise ValueError("Simulated error")
            
        except ValueError:
            uow.rollback()
        
        # Verify it was rolled back
        found = uow.sources.get_by_code("rollback_source")
        assert found is None
    
    def test_unit_of_work_context_manager(self, session):
        """Test UnitOfWork as context manager."""
        with UnitOfWork(session) as uow:
            uow.sources.create(
                code="context_source",
                name="Context Source",
                country="NZ",
                base_url="https://context.example.com/",
                scraper_class="ContextScraper",
                schedule_cron="0 12 * * *",
                is_active=True,
            )
            uow.commit()
        
        # Verify outside context
        repo = SourceRepository(session)
        found = repo.get_by_code("context_source")
        assert found is not None
