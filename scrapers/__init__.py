"""
Patient Safety Monitor - Scrapers Package

This package provides web scraping functionality for various data sources.

Modules:
    base: Abstract base scraper class and factory
    scheduler: APScheduler-based job management
    uk_pfd: UK Prevention of Future Deaths scraper
    
Usage:
    from scrapers import ScraperFactory, BaseScraper, ScrapedFinding
    
    # Create a scraper instance
    scraper = ScraperFactory.create(
        source_code="uk_pfd",
        base_url="https://www.judiciary.uk/prevention-of-future-death-reports/",
        config={"max_pages": 5}
    )
    
    # Run the scraper
    async with scraper:
        result = await scraper.scrape()

Registered Scrapers:
    - uk_pfd: UK Prevention of Future Deaths reports
    - uk_hssib: UK HSSIB investigations (Phase 6)
    - au_vic: Victoria Coroners Court (Phase 6)
    - au_nsw: NSW Coroners Court (Phase 6)
    - au_qld: Queensland Coroners Court (Phase 6)
    - nz_hdc: NZ Health & Disability Commissioner (Phase 6)
    - nz_coroner: NZ Coronial Services (Phase 6)
"""

from scrapers.base import (
    BaseScraper,
    ScrapedFinding,
    ScrapeResult,
    ScraperFactory,
)
from scrapers.scheduler import ScraperScheduler

# Import concrete scrapers to register them with the factory
# This ensures they're registered when the package is imported
from scrapers.uk_pfd import UKPFDScraper

__all__ = [
    # Base classes
    "BaseScraper",
    "ScrapedFinding",
    "ScrapeResult",
    "ScraperFactory",
    # Scheduler
    "ScraperScheduler",
    # Concrete scrapers
    "UKPFDScraper",
]
