"""
Patient Safety Monitor - Database Repository Layer

Provides clean data access patterns for all entities.
Implements the Repository pattern to separate business logic from data access.

Repositories:
    - SourceRepository: Manage data sources
    - FindingRepository: Manage findings with filtering
    - AnalysisRepository: Manage LLM analyses
    - PostRepository: Manage blog posts with workflow
    - AuditLogRepository: Track changes

Usage:
    from database.repository import FindingRepository
    from database.connection import get_session
    
    with get_session() as session:
        repo = FindingRepository(session)
        findings = repo.get_pending_classification(limit=10)
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from database.models import (
    Source,
    Finding,
    Analysis,
    Post,
    AuditLog,
    FindingStatus,
    PostStatus,
    LLMProvider,
)


logger = logging.getLogger(__name__)

# Generic type for repository base
T = TypeVar("T")


# =============================================================================
# Base Repository
# =============================================================================

class BaseRepository:
    """
    Base repository with common operations.
    
    Provides basic CRUD operations and query helpers.
    Subclasses add entity-specific methods.
    """
    
    model_class: type = None
    
    def __init__(self, session: Session):
        """
        Initialize repository with a session.
        
        Args:
            session: SQLAlchemy session for database operations
        """
        self.session = session
    
    def get_by_id(self, id: UUID) -> Optional[Any]:
        """Get entity by primary key."""
        return self.session.get(self.model_class, id)
    
    def get_all(self, limit: Optional[int] = None) -> list[Any]:
        """Get all entities with optional limit."""
        query = self.session.query(self.model_class)
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def count(self) -> int:
        """Count all entities."""
        return self.session.query(func.count(self.model_class.id)).scalar()
    
    def delete(self, id: UUID) -> bool:
        """Delete entity by ID."""
        entity = self.get_by_id(id)
        if entity:
            self.session.delete(entity)
            return True
        return False


# =============================================================================
# Source Repository
# =============================================================================

class SourceRepository(BaseRepository):
    """Repository for Source entities."""
    
    model_class = Source
    
    def create(
        self,
        code: str,
        name: str,
        country: str,
        base_url: str,
        scraper_class: str,
        schedule_cron: str,
        is_active: bool = True,
        region: Optional[str] = None,
        config_json: Optional[dict] = None,
    ) -> Source:
        """
        Create a new source.
        
        Args:
            code: Unique source identifier
            name: Human-readable name
            country: ISO country code
            base_url: Root URL for scraping
            scraper_class: Python class name
            schedule_cron: Cron expression
            is_active: Enable scraping
            region: State/region if applicable
            config_json: Source-specific configuration
            
        Returns:
            Created Source entity
        """
        source = Source(
            code=code,
            name=name,
            country=country,
            region=region,
            base_url=base_url,
            scraper_class=scraper_class,
            schedule_cron=schedule_cron,
            is_active=is_active,
            config_json=config_json,
        )
        self.session.add(source)
        self.session.flush()
        
        logger.debug(f"Created source: {code}")
        return source
    
    def get_by_code(self, code: str) -> Optional[Source]:
        """Get source by unique code."""
        return self.session.query(Source).filter(
            Source.code == code
        ).first()
    
    def get_active_sources(self) -> list[Source]:
        """Get all active sources."""
        return self.session.query(Source).filter(
            Source.is_active == True
        ).all()
    
    def get_by_country(self, country: str) -> list[Source]:
        """Get sources by country code."""
        return self.session.query(Source).filter(
            Source.country == country
        ).all()
    
    def update_last_scraped(self, source_id: UUID) -> None:
        """Update the last_scraped_at timestamp."""
        source = self.get_by_id(source_id)
        if source:
            source.last_scraped_at = func.now()
            self.session.flush()


# =============================================================================
# Finding Repository
# =============================================================================

class FindingRepository(BaseRepository):
    """Repository for Finding entities."""
    
    model_class = Finding
    
    def create(
        self,
        source_id: UUID,
        external_id: str,
        title: str,
        source_url: str,
        status: FindingStatus = FindingStatus.NEW,
        deceased_name: Optional[str] = None,
        date_of_death: Optional[datetime] = None,
        date_of_finding: Optional[datetime] = None,
        coroner_name: Optional[str] = None,
        pdf_url: Optional[str] = None,
        content_text: Optional[str] = None,
        content_html: Optional[str] = None,
        categories: Optional[list[str]] = None,
        is_healthcare: Optional[bool] = None,
        healthcare_confidence: Optional[Decimal] = None,
        metadata_json: Optional[dict] = None,
    ) -> Finding:
        """
        Create a new finding.
        
        Args:
            source_id: FK to source
            external_id: ID from source system
            title: Finding title
            source_url: URL to original
            status: Processing status
            ... (other optional fields)
            
        Returns:
            Created Finding entity
        """
        finding = Finding(
            source_id=source_id,
            external_id=external_id,
            title=title,
            source_url=source_url,
            status=status,
            deceased_name=deceased_name,
            date_of_death=date_of_death,
            date_of_finding=date_of_finding,
            coroner_name=coroner_name,
            pdf_url=pdf_url,
            content_text=content_text,
            content_html=content_html,
            categories=categories,
            is_healthcare=is_healthcare,
            healthcare_confidence=healthcare_confidence,
            metadata_json=metadata_json,
        )
        self.session.add(finding)
        self.session.flush()
        
        logger.debug(f"Created finding: {external_id}")
        return finding
    
    def get_by_external_id(
        self,
        source_id: UUID,
        external_id: str,
    ) -> Optional[Finding]:
        """Get finding by source and external ID."""
        return self.session.query(Finding).filter(
            and_(
                Finding.source_id == source_id,
                Finding.external_id == external_id,
            )
        ).first()
    
    def exists(self, source_id: UUID, external_id: str) -> bool:
        """Check if finding exists (for deduplication)."""
        count = self.session.query(func.count(Finding.id)).filter(
            and_(
                Finding.source_id == source_id,
                Finding.external_id == external_id,
            )
        ).scalar()
        return count > 0
    
    def get_by_status(
        self,
        status: FindingStatus,
        limit: Optional[int] = None,
    ) -> list[Finding]:
        """Get findings by status."""
        query = self.session.query(Finding).filter(
            Finding.status == status
        ).order_by(Finding.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_pending_classification(
        self,
        limit: Optional[int] = None,
    ) -> list[Finding]:
        """Get findings needing healthcare classification."""
        query = self.session.query(Finding).filter(
            and_(
                Finding.status == FindingStatus.NEW,
                Finding.is_healthcare.is_(None),
            )
        ).order_by(Finding.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_pending_analysis(
        self,
        limit: Optional[int] = None,
    ) -> list[Finding]:
        """Get healthcare findings pending full analysis."""
        query = self.session.query(Finding).filter(
            and_(
                Finding.status == FindingStatus.CLASSIFIED,
                Finding.is_healthcare == True,
            )
        ).order_by(Finding.created_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_healthcare_findings(
        self,
        min_confidence: float = 0.7,
        limit: Optional[int] = None,
    ) -> list[Finding]:
        """Get findings classified as healthcare-related."""
        query = self.session.query(Finding).filter(
            and_(
                Finding.is_healthcare == True,
                Finding.healthcare_confidence >= min_confidence,
            )
        ).order_by(Finding.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def update_classification(
        self,
        finding_id: UUID,
        is_healthcare: bool,
        confidence: float,
    ) -> None:
        """Update healthcare classification."""
        finding = self.get_by_id(finding_id)
        if finding:
            finding.is_healthcare = is_healthcare
            finding.healthcare_confidence = Decimal(str(confidence))
            finding.status = FindingStatus.CLASSIFIED
            self.session.flush()


# =============================================================================
# Analysis Repository
# =============================================================================

class AnalysisRepository(BaseRepository):
    """Repository for Analysis entities."""
    
    model_class = Analysis
    
    def create(
        self,
        finding_id: UUID,
        llm_provider: LLMProvider,
        llm_model: str,
        prompt_version: str,
        summary: str,
        human_factors: dict,
        latent_hazards: list,
        recommendations: list,
        key_learnings: list[str],
        settings: Optional[list[str]] = None,
        specialties: Optional[list[str]] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_usd: Optional[Decimal] = None,
        raw_response: Optional[dict] = None,
    ) -> Analysis:
        """
        Create a new analysis.
        
        Args:
            finding_id: FK to finding
            llm_provider: Provider used
            llm_model: Model identifier
            prompt_version: Prompt version
            summary: Executive summary
            human_factors: SEIPS analysis
            latent_hazards: Identified hazards
            recommendations: Improvement opportunities
            key_learnings: Takeaway points
            ... (other optional fields)
            
        Returns:
            Created Analysis entity
        """
        analysis = Analysis(
            finding_id=finding_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_version=prompt_version,
            summary=summary,
            human_factors=human_factors,
            latent_hazards=latent_hazards,
            recommendations=recommendations,
            key_learnings=key_learnings,
            settings=settings,
            specialties=specialties,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            raw_response=raw_response,
        )
        self.session.add(analysis)
        self.session.flush()
        
        logger.debug(f"Created analysis for finding: {finding_id}")
        return analysis
    
    def get_by_finding(self, finding_id: UUID) -> list[Analysis]:
        """Get all analyses for a finding."""
        return self.session.query(Analysis).filter(
            Analysis.finding_id == finding_id
        ).order_by(Analysis.created_at.desc()).all()
    
    def get_latest_for_finding(self, finding_id: UUID) -> Optional[Analysis]:
        """Get the most recent analysis for a finding."""
        return self.session.query(Analysis).filter(
            Analysis.finding_id == finding_id
        ).order_by(Analysis.created_at.desc()).first()


# =============================================================================
# Post Repository
# =============================================================================

class PostRepository(BaseRepository):
    """Repository for Post entities."""
    
    model_class = Post
    
    def create(
        self,
        analysis_id: UUID,
        slug: str,
        title: str,
        content_markdown: str,
        status: PostStatus = PostStatus.DRAFT,
        content_html: Optional[str] = None,
        excerpt: Optional[str] = None,
        tags: Optional[list[str]] = None,
        published_at: Optional[datetime] = None,
    ) -> Post:
        """
        Create a new post.
        
        Args:
            analysis_id: FK to analysis
            slug: URL-safe identifier
            title: Post title
            content_markdown: Markdown content
            status: Post status
            ... (other optional fields)
            
        Returns:
            Created Post entity
        """
        post = Post(
            analysis_id=analysis_id,
            slug=slug,
            title=title,
            content_markdown=content_markdown,
            status=status,
            content_html=content_html,
            excerpt=excerpt,
            tags=tags,
            published_at=published_at,
        )
        self.session.add(post)
        self.session.flush()
        
        logger.debug(f"Created post: {slug}")
        return post
    
    def get_by_slug(self, slug: str) -> Optional[Post]:
        """Get post by URL slug."""
        return self.session.query(Post).filter(
            Post.slug == slug
        ).first()
    
    def get_by_status(
        self,
        status: PostStatus,
        limit: Optional[int] = None,
    ) -> list[Post]:
        """Get posts by status."""
        query = self.session.query(Post).filter(
            Post.status == status
        ).order_by(Post.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_pending_review(self, limit: Optional[int] = None) -> list[Post]:
        """Get posts awaiting human review."""
        return self.get_by_status(PostStatus.PENDING_REVIEW, limit)
    
    def get_published(self, limit: Optional[int] = None) -> list[Post]:
        """Get published posts."""
        query = self.session.query(Post).filter(
            Post.status == PostStatus.PUBLISHED
        ).order_by(Post.published_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def approve(
        self,
        post_id: UUID,
        reviewed_by: str,
        publish_now: bool = False,
    ) -> Optional[Post]:
        """
        Approve a post.
        
        Args:
            post_id: Post to approve
            reviewed_by: Reviewer identifier
            publish_now: Also publish immediately
            
        Returns:
            Updated Post or None
        """
        post = self.get_by_id(post_id)
        if not post:
            return None
        
        post.reviewed_by = reviewed_by
        post.reviewed_at = func.now()
        
        if publish_now:
            post.status = PostStatus.PUBLISHED
            post.published_at = func.now()
        else:
            post.status = PostStatus.APPROVED
        
        self.session.flush()
        logger.info(f"Approved post: {post.slug}", extra={"publish_now": publish_now})
        return post
    
    def reject(
        self,
        post_id: UUID,
        reviewed_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Post]:
        """
        Reject a post.
        
        Args:
            post_id: Post to reject
            reviewed_by: Reviewer identifier
            reason: Rejection reason
            
        Returns:
            Updated Post or None
        """
        post = self.get_by_id(post_id)
        if not post:
            return None
        
        post.status = PostStatus.REJECTED
        post.reviewed_by = reviewed_by
        post.reviewed_at = func.now()
        post.reviewer_notes = reason
        
        self.session.flush()
        logger.info(f"Rejected post: {post.slug}", extra={"reason": reason})
        return post
    
    def publish(self, post_id: UUID) -> Optional[Post]:
        """
        Publish an approved post.
        
        Args:
            post_id: Post to publish
            
        Returns:
            Updated Post or None
        """
        post = self.get_by_id(post_id)
        if not post or post.status not in (PostStatus.APPROVED, PostStatus.DRAFT):
            return None
        
        post.status = PostStatus.PUBLISHED
        post.published_at = func.now()
        
        self.session.flush()
        logger.info(f"Published post: {post.slug}")
        return post


# =============================================================================
# Audit Log Repository
# =============================================================================

class AuditLogRepository(BaseRepository):
    """Repository for AuditLog entries."""
    
    model_class = AuditLog
    
    def log_change(
        self,
        table_name: str,
        record_id: UUID,
        action: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        changed_by: Optional[str] = None,
    ) -> AuditLog:
        """
        Log a change to the audit trail.
        
        Args:
            table_name: Name of affected table
            record_id: ID of affected record
            action: Type of change (insert, update, delete)
            old_values: Previous values
            new_values: New values
            changed_by: User or system making change
            
        Returns:
            Created AuditLog entry
        """
        log = AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            changed_by=changed_by,
        )
        self.session.add(log)
        self.session.flush()
        return log
    
    def get_history(
        self,
        table_name: str,
        record_id: UUID,
    ) -> list[AuditLog]:
        """Get audit history for a specific record."""
        return self.session.query(AuditLog).filter(
            and_(
                AuditLog.table_name == table_name,
                AuditLog.record_id == record_id,
            )
        ).order_by(AuditLog.changed_at.desc()).all()


# =============================================================================
# Unit of Work
# =============================================================================

class UnitOfWork:
    """
    Unit of Work pattern for managing transactions.
    
    Groups multiple repository operations into a single transaction.
    
    Usage:
        with UnitOfWork(session) as uow:
            source = uow.sources.create(...)
            finding = uow.findings.create(...)
            uow.commit()
    """
    
    def __init__(self, session: Session):
        """
        Initialize with a session.
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
        self.sources = SourceRepository(session)
        self.findings = FindingRepository(session)
        self.analyses = AnalysisRepository(session)
        self.posts = PostRepository(session)
        self.audit = AuditLogRepository(session)
    
    def __enter__(self) -> "UnitOfWork":
        """Enter context."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context, rollback on exception."""
        if exc_type is not None:
            self.rollback()
    
    def commit(self) -> None:
        """Commit the transaction."""
        self.session.commit()
    
    def rollback(self) -> None:
        """Rollback the transaction."""
        self.session.rollback()


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "BaseRepository",
    "SourceRepository",
    "FindingRepository",
    "AnalysisRepository",
    "PostRepository",
    "AuditLogRepository",
    "UnitOfWork",
]
