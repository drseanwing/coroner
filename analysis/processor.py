"""
Patient Safety Monitor - Analysis Processor

Processes findings through the LLM analysis pipeline in batches.
Handles classification, extraction, human factors analysis, and blog generation.

Usage:
    from analysis.processor import AnalysisProcessor
    
    processor = AnalysisProcessor()
    results = await processor.process_pending(limit=10)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from config.settings import get_settings
from config.logging import get_logger
from database.connection import get_session
from database.models import Finding, Analysis, Post, FindingStatus, PostStatus, LLMProvider
from database.repository import FindingRepository, AnalysisRepository, PostRepository
from analysis.analyser import (
    AnalysisPipeline,
    AnalysisPipelineResult,
    ClassificationResult,
)
from slugify import slugify


logger = get_logger(__name__)


@dataclass
class ProcessingStats:
    """Statistics for a processing run."""
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Counts
    findings_processed: int = 0
    findings_classified: int = 0
    findings_healthcare: int = 0
    findings_non_healthcare: int = 0
    analyses_created: int = 0
    posts_created: int = 0
    
    # Costs
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    
    # Errors
    errors: list[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    @property
    def success_rate(self) -> float:
        if self.findings_processed == 0:
            return 0.0
        return (self.findings_processed - len(self.errors)) / self.findings_processed


class AnalysisProcessor:
    """
    Processes findings through the analysis pipeline.
    
    Workflow:
    1. Fetch pending findings from database
    2. Run classification (healthcare vs non-healthcare)
    3. For healthcare findings, run full analysis
    4. Generate blog posts
    5. Save results to database
    """
    
    def __init__(
        self,
        pipeline: Optional[AnalysisPipeline] = None,
        batch_size: int = 10,
        classification_threshold: float = 0.7,
    ):
        """
        Initialize the processor.
        
        Args:
            pipeline: Analysis pipeline (creates default if not provided)
            batch_size: Number of findings to process per batch
            classification_threshold: Minimum confidence for healthcare classification
        """
        self.pipeline = pipeline or AnalysisPipeline()
        self.batch_size = batch_size
        self.classification_threshold = classification_threshold
        self.settings = get_settings()
    
    async def process_pending_classification(
        self,
        limit: Optional[int] = None,
    ) -> ProcessingStats:
        """
        Process findings pending healthcare classification.
        
        Args:
            limit: Maximum findings to process
            
        Returns:
            Processing statistics
        """
        limit = limit or self.batch_size
        stats = ProcessingStats()
        
        logger.info(
            "Starting classification processing",
            extra={"limit": limit},
        )
        
        with get_session() as session:
            repo = FindingRepository(session)
            findings = repo.get_pending_classification(limit=limit)
            
            logger.info(f"Found {len(findings)} findings to classify")
            
            for finding in findings:
                try:
                    result = await self._classify_finding(finding)
                    
                    # Update finding in database
                    repo.update_classification(
                        finding.id,
                        is_healthcare=result.is_healthcare,
                        confidence=result.confidence,
                    )
                    
                    stats.findings_classified += 1
                    stats.total_tokens += result.tokens_used
                    stats.total_cost_usd += result.cost_usd
                    
                    if result.is_healthcare:
                        stats.findings_healthcare += 1
                    else:
                        stats.findings_non_healthcare += 1
                    
                    logger.debug(
                        "Classified finding",
                        extra={
                            "finding_id": str(finding.id),
                            "is_healthcare": result.is_healthcare,
                            "confidence": result.confidence,
                        },
                    )
                    
                except Exception as e:
                    logger.error(
                        "Classification failed",
                        extra={
                            "finding_id": str(finding.id),
                            "error": str(e),
                        },
                    )
                    stats.errors.append(f"Classification failed for {finding.id}: {e}")
                
                stats.findings_processed += 1
            
            session.commit()
        
        stats.completed_at = datetime.utcnow()
        
        logger.info(
            "Classification processing complete",
            extra={
                "processed": stats.findings_processed,
                "healthcare": stats.findings_healthcare,
                "non_healthcare": stats.findings_non_healthcare,
                "duration_seconds": stats.duration_seconds,
            },
        )
        
        return stats
    
    async def process_pending_analysis(
        self,
        limit: Optional[int] = None,
    ) -> ProcessingStats:
        """
        Process healthcare findings pending full analysis.
        
        Args:
            limit: Maximum findings to process
            
        Returns:
            Processing statistics
        """
        limit = limit or self.batch_size
        stats = ProcessingStats()
        
        logger.info(
            "Starting analysis processing",
            extra={"limit": limit},
        )
        
        with get_session() as session:
            finding_repo = FindingRepository(session)
            analysis_repo = AnalysisRepository(session)
            post_repo = PostRepository(session)
            
            findings = finding_repo.get_pending_analysis(limit=limit)
            
            logger.info(f"Found {len(findings)} findings to analyze")
            
            for finding in findings:
                try:
                    # Run full pipeline (skip classification since already done)
                    result = await self.pipeline.analyse(
                        finding,
                        skip_classification=True,
                    )
                    
                    if not result.success:
                        raise ValueError(f"Pipeline failed: {result.errors}")
                    
                    # Save analysis
                    analysis = analysis_repo.create(
                        finding_id=finding.id,
                        llm_provider=LLMProvider.CLAUDE,
                        llm_model=self.settings.llm_primary_model,
                        prompt_version="1.0.0",
                        summary=result.extraction.summary if result.extraction else "",
                        human_factors=result.human_factors.to_dict() if result.human_factors else {},
                        latent_hazards=result.human_factors.latent_hazards if result.human_factors else [],
                        recommendations=result.human_factors.improvement_opportunities if result.human_factors else [],
                        key_learnings=result.blog_post.key_learnings if result.blog_post else [],
                        settings=result.extraction.healthcare_context.get("settings", []) if result.extraction else [],
                        specialties=result.extraction.healthcare_context.get("specialties", []) if result.extraction else [],
                        tokens_input=result.total_tokens // 2,  # Approximate split
                        tokens_output=result.total_tokens // 2,
                        cost_usd=result.total_cost_usd,
                    )
                    
                    stats.analyses_created += 1
                    
                    # Create blog post
                    if result.blog_post:
                        slug = self._generate_slug(result.blog_post.title, finding.id)
                        
                        post = post_repo.create(
                            analysis_id=analysis.id,
                            slug=slug,
                            title=result.blog_post.title,
                            content_markdown=result.blog_post.content_markdown,
                            excerpt=result.blog_post.excerpt,
                            tags=result.blog_post.tags,
                            status=PostStatus.PENDING_REVIEW,
                        )
                        
                        stats.posts_created += 1
                        
                        logger.debug(
                            "Created post",
                            extra={
                                "post_id": str(post.id),
                                "slug": slug,
                            },
                        )
                    
                    # Update finding status
                    finding.status = FindingStatus.ANALYSED
                    
                    stats.total_tokens += result.total_tokens
                    stats.total_cost_usd += result.total_cost_usd
                    
                    logger.info(
                        "Analyzed finding",
                        extra={
                            "finding_id": str(finding.id),
                            "tokens": result.total_tokens,
                            "cost_usd": result.total_cost_usd,
                        },
                    )
                    
                except Exception as e:
                    logger.error(
                        "Analysis failed",
                        extra={
                            "finding_id": str(finding.id),
                            "error": str(e),
                        },
                    )
                    stats.errors.append(f"Analysis failed for {finding.id}: {e}")
                
                stats.findings_processed += 1
            
            session.commit()
        
        stats.completed_at = datetime.utcnow()
        
        logger.info(
            "Analysis processing complete",
            extra={
                "processed": stats.findings_processed,
                "analyses": stats.analyses_created,
                "posts": stats.posts_created,
                "total_cost": stats.total_cost_usd,
                "duration_seconds": stats.duration_seconds,
            },
        )
        
        return stats
    
    async def process_all_pending(
        self,
        limit: Optional[int] = None,
    ) -> ProcessingStats:
        """
        Process all pending findings (classification + analysis).
        
        Args:
            limit: Maximum findings to process in each stage
            
        Returns:
            Combined processing statistics
        """
        logger.info("Starting full processing run")
        
        # First, classify pending findings
        class_stats = await self.process_pending_classification(limit=limit)
        
        # Then, analyze classified healthcare findings
        analysis_stats = await self.process_pending_analysis(limit=limit)
        
        # Combine stats
        combined = ProcessingStats(
            started_at=class_stats.started_at,
            completed_at=analysis_stats.completed_at,
            findings_processed=class_stats.findings_processed + analysis_stats.findings_processed,
            findings_classified=class_stats.findings_classified,
            findings_healthcare=class_stats.findings_healthcare,
            findings_non_healthcare=class_stats.findings_non_healthcare,
            analyses_created=analysis_stats.analyses_created,
            posts_created=analysis_stats.posts_created,
            total_tokens=class_stats.total_tokens + analysis_stats.total_tokens,
            total_cost_usd=class_stats.total_cost_usd + analysis_stats.total_cost_usd,
            errors=class_stats.errors + analysis_stats.errors,
        )
        
        logger.info(
            "Full processing run complete",
            extra={
                "classified": combined.findings_classified,
                "analyzed": combined.analyses_created,
                "posts": combined.posts_created,
                "total_cost": combined.total_cost_usd,
            },
        )
        
        return combined
    
    async def _classify_finding(self, finding: Finding) -> ClassificationResult:
        """
        Run classification on a single finding.
        
        Args:
            finding: Finding to classify
            
        Returns:
            Classification result
        """
        # Use pipeline's classification stage
        result = await self.pipeline._classify(finding)
        return result
    
    def _generate_slug(self, title: str, finding_id: UUID) -> str:
        """
        Generate a unique URL slug for a post.
        
        Args:
            title: Post title
            finding_id: Finding UUID for uniqueness
            
        Returns:
            URL-safe slug
        """
        base_slug = slugify(title, max_length=150)
        
        # Add short UUID suffix for uniqueness
        uuid_suffix = str(finding_id)[:8]
        
        return f"{base_slug}-{uuid_suffix}"


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main() -> int:
    """
    Main entry point for analysis processing.
    
    Can be run standalone to process pending findings:
        python -m analysis.processor
    """
    import sys
    from config.logging import setup_logging
    from database.connection import init_database
    
    setup_logging()
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Analysis Processor")
    logger.info("=" * 60)
    
    if not init_database():
        logger.error("Database initialization failed")
        return 1
    
    processor = AnalysisProcessor()
    
    try:
        stats = await processor.process_all_pending(limit=10)
        
        print(f"\nProcessing Complete:")
        print(f"  Findings processed: {stats.findings_processed}")
        print(f"  Healthcare findings: {stats.findings_healthcare}")
        print(f"  Analyses created: {stats.analyses_created}")
        print(f"  Posts created: {stats.posts_created}")
        print(f"  Total cost: ${stats.total_cost_usd:.4f}")
        print(f"  Duration: {stats.duration_seconds:.1f}s")
        
        if stats.errors:
            print(f"\nErrors ({len(stats.errors)}):")
            for error in stats.errors[:5]:
                print(f"  - {error}")
        
        return 0
        
    except Exception as e:
        logger.exception(f"Processing failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
