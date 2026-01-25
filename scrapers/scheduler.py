"""
Patient Safety Monitor - Scraper Scheduler

APScheduler-based job scheduler for running scrapers on configured schedules.
Supports cron expressions, manual triggers, and job monitoring.

Usage:
    # As a module (Docker)
    python -m scrapers.scheduler
    
    # Programmatically
    from scrapers.scheduler import ScraperScheduler
    scheduler = ScraperScheduler()
    scheduler.start()
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

from config.settings import get_settings
from config.logging import setup_logging, get_logger
from database.connection import get_session, init_database
from database.models import Source, Finding, FindingStatus
from database.repository import SourceRepository, FindingRepository
from scrapers.base import ScraperFactory, ScrapeResult


logger = get_logger(__name__)


class ScraperScheduler:
    """
    Manages scheduled execution of web scrapers.
    
    Features:
    - Loads schedules from database
    - Supports cron expressions
    - Manual trigger capability
    - Job execution logging
    - Graceful shutdown
    """
    
    def __init__(self):
        """Initialize the scheduler."""
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,  # Combine missed runs
                "max_instances": 1,  # Only one instance per job
                "misfire_grace_time": 3600,  # 1 hour grace period
            },
        )
        self._running = False
        
        # Register event listeners
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED,
        )
        self.scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR,
        )
        self.scheduler.add_listener(
            self._on_job_missed,
            EVENT_JOB_MISSED,
        )
    
    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle successful job execution."""
        logger.info(
            f"Job executed successfully",
            extra={
                "job_id": event.job_id,
                "scheduled_time": event.scheduled_run_time.isoformat(),
                "return_value": str(event.retval)[:100] if event.retval else None,
            },
        )
    
    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handle job execution error."""
        logger.error(
            f"Job execution failed",
            extra={
                "job_id": event.job_id,
                "scheduled_time": event.scheduled_run_time.isoformat(),
                "exception": str(event.exception),
            },
        )
    
    def _on_job_missed(self, event: JobExecutionEvent) -> None:
        """Handle missed job execution."""
        logger.warning(
            f"Job execution missed",
            extra={
                "job_id": event.job_id,
                "scheduled_time": event.scheduled_run_time.isoformat(),
            },
        )
    
    def load_schedules(self) -> int:
        """
        Load scraper schedules from database.
        
        Returns:
            Number of jobs scheduled
        """
        logger.info("Loading scraper schedules from database")
        jobs_added = 0
        
        with get_session() as session:
            repo = SourceRepository(session)
            sources = repo.get_active_sources()
            
            for source in sources:
                try:
                    # Parse cron expression
                    trigger = CronTrigger.from_crontab(source.schedule_cron)
                    
                    # Add job
                    self.scheduler.add_job(
                        self._run_scraper,
                        trigger=trigger,
                        id=f"scraper_{source.code}",
                        name=f"Scraper: {source.name}",
                        kwargs={"source_code": source.code},
                        replace_existing=True,
                    )
                    
                    jobs_added += 1
                    logger.info(
                        f"Scheduled scraper",
                        extra={
                            "source_code": source.code,
                            "schedule": source.schedule_cron,
                        },
                    )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to schedule scraper",
                        extra={
                            "source_code": source.code,
                            "error": str(e),
                        },
                    )
        
        logger.info(f"Loaded {jobs_added} scraper schedules")
        return jobs_added
    
    async def _run_scraper(self, source_code: str) -> Optional[ScrapeResult]:
        """
        Execute a scraper for the given source.
        
        Args:
            source_code: Source identifier
            
        Returns:
            ScrapeResult or None on failure
        """
        logger.info(f"Starting scraper run", extra={"source_code": source_code})
        start_time = datetime.utcnow()
        
        try:
            # Load source configuration
            with get_session() as session:
                repo = SourceRepository(session)
                source = repo.get_by_code(source_code)
                
                if not source:
                    logger.error(f"Source not found: {source_code}")
                    return None
                
                if not source.is_active:
                    logger.warning(f"Source is inactive: {source_code}")
                    return None
                
                source_config = {
                    "id": source.id,
                    "base_url": source.base_url,
                    "config": source.config_json or {},
                }
            
            # Create and run scraper
            scraper = ScraperFactory.create(
                source_code,
                source_config["base_url"],
                source_config["config"],
            )
            
            async with scraper:
                result = await scraper.scrape()
            
            # Save results
            await self._save_scrape_results(source_config["id"], result)
            
            # Update last scraped timestamp
            with get_session() as session:
                repo = SourceRepository(session)
                repo.update_last_scraped(source_config["id"])
                session.commit()
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Scraper run completed",
                extra={
                    "source_code": source_code,
                    "duration_seconds": duration,
                    "findings_count": len(result.findings),
                    "new_findings": result.new_findings,
                    "errors": len(result.errors),
                },
            )
            
            return result
            
        except Exception as e:
            logger.exception(
                f"Scraper run failed",
                extra={"source_code": source_code, "error": str(e)},
            )
            return None
    
    async def _save_scrape_results(
        self,
        source_id: Any,
        result: ScrapeResult,
    ) -> tuple[int, int]:
        """
        Save scraped findings to database.
        
        Args:
            source_id: Source UUID
            result: Scrape result
            
        Returns:
            Tuple of (new_count, duplicate_count)
        """
        new_count = 0
        duplicate_count = 0
        
        with get_session() as session:
            repo = FindingRepository(session)
            
            for scraped in result.findings:
                # Check for duplicate
                if repo.exists(source_id, scraped.external_id):
                    duplicate_count += 1
                    logger.debug(
                        f"Skipping duplicate finding",
                        extra={"external_id": scraped.external_id},
                    )
                    continue
                
                # Create new finding
                finding = repo.create(
                    source_id=source_id,
                    external_id=scraped.external_id,
                    title=scraped.title,
                    source_url=scraped.source_url,
                    deceased_name=scraped.deceased_name,
                    date_of_death=scraped.date_of_death,
                    date_of_finding=scraped.date_of_finding,
                    coroner_name=scraped.coroner_name,
                    pdf_url=scraped.pdf_url,
                    content_text=scraped.content_text,
                    content_html=scraped.content_html,
                    categories=scraped.categories,
                    status=FindingStatus.NEW,
                    metadata_json=scraped.metadata,
                )
                new_count += 1
                
                logger.debug(
                    f"Saved new finding",
                    extra={
                        "finding_id": str(finding.id),
                        "external_id": scraped.external_id,
                    },
                )
            
            session.commit()
        
        logger.info(
            f"Saved scrape results",
            extra={
                "new_findings": new_count,
                "duplicates": duplicate_count,
            },
        )
        
        return new_count, duplicate_count
    
    async def trigger_scraper(self, source_code: str) -> Optional[ScrapeResult]:
        """
        Manually trigger a scraper run.
        
        Args:
            source_code: Source identifier
            
        Returns:
            ScrapeResult or None on failure
        """
        logger.info(f"Manual trigger for scraper: {source_code}")
        return await self._run_scraper(source_code)
    
    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        logger.info("Starting scheduler")
        self.load_schedules()
        self.scheduler.start()
        self._running = True
        
        # Log scheduled jobs
        jobs = self.scheduler.get_jobs()
        logger.info(f"Scheduler started with {len(jobs)} jobs")
        for job in jobs:
            logger.debug(
                f"Scheduled job",
                extra={
                    "job_id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                },
            )
    
    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping scheduler")
        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Scheduler stopped")
    
    def get_job_status(self) -> list[dict[str, Any]]:
        """
        Get status of all scheduled jobs.
        
        Returns:
            List of job status dictionaries
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending,
            })
        return jobs


# =============================================================================
# Main Entry Point
# =============================================================================

async def main() -> int:
    """
    Main entry point for scheduler service.
    
    Returns:
        Exit code (0 for success)
    """
    # Setup logging
    setup_logging()
    logger.info("=" * 60)
    logger.info("Patient Safety Monitor - Scheduler Service")
    logger.info("=" * 60)
    
    # Initialize database
    if not init_database():
        logger.error("Database initialization failed")
        return 1
    
    # Create scheduler
    scheduler = ScraperScheduler()
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    
    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        scheduler.stop()
        loop.stop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
    
    # Start scheduler
    scheduler.start()
    
    # Keep running until stopped
    try:
        while True:
            await asyncio.sleep(60)
            # Periodic health log
            jobs = scheduler.get_job_status()
            logger.debug(f"Scheduler health check: {len(jobs)} jobs active")
    except asyncio.CancelledError:
        logger.info("Scheduler loop cancelled")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
        sys.exit(0)
