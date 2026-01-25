"""
Patient Safety Monitor - Database Models

SQLAlchemy ORM models for all database entities.
Uses PostgreSQL with UUID primary keys and JSONB columns.

Tables:
    - sources: Data source configurations
    - findings: Raw collected investigation data
    - analyses: LLM-generated analysis results
    - posts: Generated blog content
    - audit_log: Change tracking for compliance

Usage:
    from database.models import Source, Finding, Analysis, Post
    
    # Create a new finding
    finding = Finding(
        source_id=source.id,
        external_id="report-001",
        title="Investigation Report",
        source_url="https://example.com/report",
        status=FindingStatus.NEW,
    )
"""

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# =============================================================================
# Base Class
# =============================================================================

class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# =============================================================================
# Enums
# =============================================================================

class FindingStatus(enum.Enum):
    """Status of a finding through the processing pipeline."""
    NEW = "new"                      # Just scraped
    CLASSIFIED = "classified"        # Healthcare classification complete
    ANALYSED = "analysed"           # Full analysis complete
    PUBLISHED = "published"         # Blog post published
    EXCLUDED = "excluded"           # Excluded from processing


class PostStatus(enum.Enum):
    """Status of a blog post."""
    DRAFT = "draft"                  # Initial AI-generated draft
    PENDING_REVIEW = "pending_review"  # Awaiting human review
    APPROVED = "approved"            # Approved but not published
    PUBLISHED = "published"          # Live on the blog
    REJECTED = "rejected"            # Rejected by reviewer


class LLMProvider(enum.Enum):
    """LLM provider used for analysis."""
    CLAUDE = "claude"
    OPENAI = "openai"


# =============================================================================
# Mixins
# =============================================================================

class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# =============================================================================
# Models
# =============================================================================

class Source(Base, TimestampMixin):
    """
    Data source registry.
    
    Stores configuration for each scraping source (UK PFD, HSSIB, etc.)
    including schedule, base URL, and source-specific settings.
    """
    __tablename__ = "sources"
    
    # Primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Identification
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique identifier (e.g., uk_pfd, au_vic)",
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable name",
    )
    
    # Location
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        index=True,
        comment="ISO country code (AU, NZ, GB)",
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="State/region if applicable",
    )
    
    # Scraping configuration
    base_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Root URL for scraping",
    )
    scraper_class: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Python class name (e.g., UKPFDScraper)",
    )
    schedule_cron: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="0 6 * * *",
        comment="Cron expression for scheduling",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Enable/disable scraping",
    )
    
    # Metadata
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful scrape timestamp",
    )
    config_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Source-specific configuration",
    )
    
    # Relationships
    findings: Mapped[list["Finding"]] = relationship(
        "Finding",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_sources_country_active", "country", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<Source(code={self.code!r}, name={self.name!r})>"


class Finding(Base, TimestampMixin):
    """
    Raw collected investigation data.
    
    Stores the original finding data from scraping before analysis.
    Each finding represents a single coronial investigation or safety report.
    """
    __tablename__ = "findings"
    
    # Primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Foreign key
    source_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Identification
    external_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="ID from source system (for deduplication)",
    )
    
    # Content
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Finding/case title",
    )
    deceased_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Name of deceased (if public)",
    )
    date_of_death: Mapped[Optional[datetime]] = mapped_column(
        Date,
        nullable=True,
        comment="Date of incident/death",
    )
    date_of_finding: Mapped[Optional[datetime]] = mapped_column(
        Date,
        nullable=True,
        comment="Date finding was published",
    )
    coroner_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Name of coroner/investigator",
    )
    
    # URLs and storage
    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="URL to original document",
    )
    pdf_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Direct PDF link if available",
    )
    pdf_stored_path: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Local path to archived PDF",
    )
    
    # Content storage
    content_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Extracted text content",
    )
    content_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Raw HTML if scraped from web",
    )
    
    # Classification
    categories: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Source-provided categories",
    )
    is_healthcare: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="Classified as healthcare-related",
    )
    healthcare_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="Classification confidence (0.00-1.00)",
    )
    
    # Status
    status: Mapped[FindingStatus] = mapped_column(
        SQLEnum(FindingStatus, name="finding_status"),
        nullable=False,
        default=FindingStatus.NEW,
        index=True,
    )
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Source-specific metadata",
    )
    
    # Relationships
    source: Mapped["Source"] = relationship(
        "Source",
        back_populates="findings",
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        "Analysis",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_findings_source_external", "source_id", "external_id", unique=True),
        Index("ix_findings_status_healthcare", "status", "is_healthcare"),
        Index("ix_findings_date", "date_of_finding"),
    )
    
    def __repr__(self) -> str:
        return f"<Finding(id={self.id!r}, title={self.title[:50]!r}...)>"


class Analysis(Base):
    """
    LLM-generated analysis results.
    
    Stores the output from the analysis pipeline including
    human factors analysis, recommendations, and key learnings.
    """
    __tablename__ = "analyses"
    
    # Primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Foreign key
    finding_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # LLM metadata
    llm_provider: Mapped[LLMProvider] = mapped_column(
        SQLEnum(LLMProvider, name="llm_provider"),
        nullable=False,
    )
    llm_model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Model identifier used",
    )
    prompt_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version of prompt template",
    )
    
    # Analysis content
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Executive summary of incident",
    )
    human_factors: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Structured HF analysis (SEIPS framework)",
    )
    latent_hazards: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="System vulnerabilities identified",
    )
    recommendations: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Improvement opportunities",
    )
    key_learnings: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        comment="Bullet-point takeaways",
    )
    
    # Context
    settings: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Healthcare settings involved (ED, ambulance, etc.)",
    )
    specialties: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Medical specialties relevant",
    )
    
    # Usage tracking
    tokens_input: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Input tokens consumed",
    )
    tokens_output: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Output tokens generated",
    )
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
        comment="API cost for this analysis",
    )
    
    # Debug
    raw_response: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full LLM response for debugging",
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    
    # Relationships
    finding: Mapped["Finding"] = relationship(
        "Finding",
        back_populates="analyses",
    )
    posts: Mapped[list["Post"]] = relationship(
        "Post",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Analysis(id={self.id!r}, finding_id={self.finding_id!r})>"


class Post(Base, TimestampMixin):
    """
    Generated blog content.
    
    Stores the blog post content from draft through publication.
    Tracks review workflow and publication status.
    """
    __tablename__ = "posts"
    
    # Primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Foreign key
    analysis_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Identification
    slug: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe identifier",
    )
    
    # Content
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Blog post title",
    )
    content_markdown: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Post content in Markdown",
    )
    content_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Rendered HTML",
    )
    excerpt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Short preview text",
    )
    tags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Categorisation tags",
    )
    
    # Status
    status: Mapped[PostStatus] = mapped_column(
        SQLEnum(PostStatus, name="post_status"),
        nullable=False,
        default=PostStatus.DRAFT,
        index=True,
    )
    
    # Review workflow
    reviewer_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human reviewer feedback",
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Reviewer identifier",
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Review timestamp",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Publication timestamp",
    )
    
    # Relationships
    analysis: Mapped["Analysis"] = relationship(
        "Analysis",
        back_populates="posts",
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_posts_status_published", "status", "published_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Post(slug={self.slug!r}, status={self.status!r})>"


class AuditLog(Base):
    """
    Change tracking for compliance.
    
    Records all create, update, and delete operations
    for auditing and debugging purposes.
    """
    __tablename__ = "audit_log"
    
    # Primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    
    # Target
    table_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    record_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Action
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="insert, update, delete",
    )
    
    # Changes
    old_values: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    new_values: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    
    # Context
    changed_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="User or system that made the change",
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
        index=True,
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_audit_log_table_record", "table_name", "record_id"),
        Index("ix_audit_log_changed_at", "changed_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(table={self.table_name!r}, action={self.action!r})>"


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "Base",
    "Source",
    "Finding",
    "Analysis",
    "Post",
    "AuditLog",
    "FindingStatus",
    "PostStatus",
    "LLMProvider",
]
