"""
Patient Safety Monitor - UK Prevention of Future Deaths Scraper

Scraper for UK Judiciary Prevention of Future Deaths reports.
Source: https://www.judiciary.uk/prevention-of-future-death-reports/

This is the Phase 2 priority scraper - the first fully implemented source.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs

from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    ScrapedFinding,
    ScrapeResult,
    ScraperFactory,
)


logger = logging.getLogger(__name__)


class UKPFDScraper(BaseScraper):
    """
    Scraper for UK Prevention of Future Deaths reports.
    
    The UK Judiciary publishes PFD reports when a coroner has concerns
    that future deaths may occur unless action is taken.
    
    Site structure:
        - Main listing: /prevention-of-future-death-reports/
        - Categories filter via URL parameters
        - Individual reports as HTML pages with embedded PDFs
        - Pagination via ?paged=N parameter
    """
    
    # Healthcare-related categories to filter
    HEALTHCARE_CATEGORIES = [
        "Hospital Death (Clinical)",
        "Hospital Death (Other)",
        "Medical cause",
        "Community health care and target settings",
        "Mental health related deaths",
        "Emergency services related deaths",
    ]
    
    # CSS selectors for the PFD website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": "article.pfd_single",
        "title": "h2 a",
        "date": ".pfd_meta_date",
        "categories": ".pfd_meta_categories a",
        "coroner": ".pfd_meta_coroner",
        "pagination": ".pagination a.next",
        
        # Detail page selectors
        "content": ".entry-content",
        "pdf_link": "a[href*='.pdf']",
        "deceased_name": ".pfd_meta_deceased",
        "date_of_death": ".pfd_meta_dod",
        "date_of_report": ".pfd_meta_date_report",
        "addressee": ".pfd_meta_addressee",
    }
    
    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(source_code, base_url, config)
        
        # Configuration
        self.categories = config.get("categories", self.HEALTHCARE_CATEGORIES)
        self.max_pages = config.get("max_pages", 10)
        self.selectors = {**self.DEFAULT_SELECTORS, **config.get("selectors", {})}
        
        # Rate limiting
        self.request_delay = config.get("request_delay", 2.0)
    
    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.
        
        Scrapes PFD reports from the UK Judiciary website, filtering
        for healthcare-related categories.
        
        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting UK PFD scrape",
            extra={
                "max_pages": self.max_pages,
                "categories": len(self.categories),
            },
        )
        started_at = datetime.utcnow()
        
        all_findings: list[ScrapedFinding] = []
        errors: list[str] = []
        warnings: list[str] = []
        pages_scraped = 0
        failed_pages = 0
        
        try:
            # Start with first page
            current_url: Optional[str] = self._build_listing_url(page=1)
            
            while current_url and pages_scraped < self.max_pages:
                self.logger.info(
                    f"Scraping page {pages_scraped + 1}",
                    extra={"url": current_url},
                )
                
                try:
                    # Respect rate limits
                    if pages_scraped > 0:
                        await asyncio.sleep(self.request_delay)
                    
                    # Fetch listing page
                    page_content = await self.fetch_page(current_url)
                    
                    # Parse listing
                    findings, next_url = await self.parse_listing_page(
                        page_content, current_url
                    )
                    
                    self.logger.info(
                        f"Found {len(findings)} findings on page",
                        extra={"page": pages_scraped + 1},
                    )
                    
                    # Fetch detail pages for each finding
                    for i, finding in enumerate(findings):
                        try:
                            # Rate limit between detail requests
                            if i > 0:
                                await asyncio.sleep(self.request_delay)
                            
                            self.logger.debug(
                                f"Fetching detail page",
                                extra={"external_id": finding.external_id},
                            )
                            
                            detail_content = await self.fetch_page(finding.source_url)
                            finding = await self.parse_finding_page(
                                detail_content, finding
                            )
                            all_findings.append(finding)
                            
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to fetch detail page",
                                extra={
                                    "external_id": finding.external_id,
                                    "error": str(e),
                                },
                            )
                            warnings.append(f"Detail fetch failed: {finding.external_id}")
                            # Still add the finding with partial data
                            all_findings.append(finding)
                    
                    pages_scraped += 1
                    current_url = next_url
                    
                except Exception as e:
                    self.logger.error(
                        f"Failed to scrape listing page",
                        extra={"url": current_url, "error": str(e)},
                    )
                    errors.append(f"Page scrape failed: {current_url}")
                    failed_pages += 1
                    
                    # Try to continue to next page if we can
                    if pages_scraped == 0:
                        # First page failed, can't continue
                        break
                    else:
                        # Try next page
                        current_url = self._build_listing_url(page=pages_scraped + 2)
            
        except Exception as e:
            self.logger.exception(f"Scrape failed with error: {e}")
            errors.append(f"Fatal error: {str(e)}")
        
        completed_at = datetime.utcnow()
        
        # Calculate new vs duplicates (will be updated by scheduler)
        result = ScrapeResult(
            source_code=self.source_code,
            started_at=started_at,
            completed_at=completed_at,
            findings=all_findings,
            pages_scraped=pages_scraped,
            new_findings=len(all_findings),
            duplicate_findings=0,
            failed_pages=failed_pages,
            errors=errors,
            warnings=warnings,
        )
        
        self.logger.info(
            f"UK PFD scrape completed",
            extra={
                "findings_count": len(all_findings),
                "pages_scraped": pages_scraped,
                "duration_seconds": result.duration_seconds,
                "errors": len(errors),
            },
        )
        
        return result
    
    async def parse_listing_page(
        self,
        page_content: str,
        page_url: str,
    ) -> tuple[list[ScrapedFinding], Optional[str]]:
        """
        Parse a PFD listing page.
        
        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed
            
        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []
        
        # Find all report items
        items = soup.select(self.selectors["list_container"])
        self.logger.debug(f"Found {len(items)} items on listing page")
        
        for item in items:
            try:
                # Extract title and link
                title_elem = item.select_one(self.selectors["title"])
                if not title_elem:
                    self.logger.debug("Skipping item without title")
                    continue
                
                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                
                if not href:
                    self.logger.debug(f"Skipping item without link: {title[:50]}")
                    continue
                
                source_url = urljoin(page_url, href)
                
                # Generate external ID from URL
                external_id = self._extract_external_id(source_url)
                
                # Parse date
                date_of_finding = None
                date_elem = item.select_one(self.selectors["date"])
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    date_of_finding = self._parse_uk_date(date_text)
                
                # Get categories
                categories = []
                category_elems = item.select(self.selectors["categories"])
                for cat_elem in category_elems:
                    cat_text = cat_elem.get_text(strip=True)
                    if cat_text:
                        categories.append(cat_text)
                
                # Filter by healthcare categories if configured
                if self.categories and not self._is_healthcare_category(categories):
                    self.logger.debug(
                        f"Skipping non-healthcare finding",
                        extra={"title": title[:50], "categories": categories},
                    )
                    continue
                
                # Get coroner name if available
                coroner_name = None
                coroner_elem = item.select_one(self.selectors["coroner"])
                if coroner_elem:
                    coroner_name = coroner_elem.get_text(strip=True)
                    # Clean up prefix like "Coroner: "
                    coroner_name = re.sub(r"^Coroner:\s*", "", coroner_name)
                
                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    coroner_name=coroner_name,
                    categories=categories,
                    metadata={
                        "scraped_at": datetime.utcnow().isoformat(),
                        "scraper_version": "1.0.0",
                    },
                )
                findings.append(finding)
                
            except Exception as e:
                self.logger.warning(f"Failed to parse listing item: {e}")
        
        # Find next page link
        next_url = None
        next_link = soup.select_one(self.selectors["pagination"])
        if next_link and next_link.get("href"):
            next_url = urljoin(page_url, next_link["href"])
            self.logger.debug(f"Found next page: {next_url}")
        
        return findings, next_url
    
    async def parse_finding_page(
        self,
        page_content: str,
        finding: ScrapedFinding,
    ) -> ScrapedFinding:
        """
        Parse an individual PFD report page.
        
        Args:
            page_content: HTML content of finding page
            finding: Partial finding from listing
            
        Returns:
            Completed finding with all details
        """
        soup = BeautifulSoup(page_content, "lxml")
        
        # Extract main content
        content_elem = soup.select_one(self.selectors["content"])
        if content_elem:
            finding.content_html = str(content_elem)
            finding.content_text = content_elem.get_text(separator="\n", strip=True)
        
        # Find PDF link
        pdf_link = soup.select_one(self.selectors["pdf_link"])
        if pdf_link and pdf_link.get("href"):
            finding.pdf_url = urljoin(finding.source_url, pdf_link["href"])
        
        # Extract deceased name if available
        deceased_elem = soup.select_one(self.selectors["deceased_name"])
        if deceased_elem:
            deceased_text = deceased_elem.get_text(strip=True)
            deceased_text = re.sub(r"^(Deceased|Name):\s*", "", deceased_text, flags=re.I)
            finding.deceased_name = deceased_text
        
        # Extract date of death if available
        dod_elem = soup.select_one(self.selectors["date_of_death"])
        if dod_elem:
            dod_text = dod_elem.get_text(strip=True)
            dod_text = re.sub(r"^Date of death:\s*", "", dod_text, flags=re.I)
            finding.date_of_death = self._parse_uk_date(dod_text)
        
        # Update coroner name from detail page if not already set
        if not finding.coroner_name:
            coroner_elem = soup.select_one(self.selectors["coroner"])
            if coroner_elem:
                coroner_text = coroner_elem.get_text(strip=True)
                finding.coroner_name = re.sub(r"^Coroner:\s*", "", coroner_text)
        
        # Extract addressee organizations
        addressee_elem = soup.select_one(self.selectors["addressee"])
        if addressee_elem:
            finding.metadata["addressees"] = addressee_elem.get_text(strip=True)
        
        return finding
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _build_listing_url(self, page: int = 1) -> str:
        """
        Build listing URL with category filters.
        
        Args:
            page: Page number (1-indexed)
            
        Returns:
            Full URL with query parameters
        """
        base = self.base_url.rstrip("/")
        
        params = {}
        if page > 1:
            params["paged"] = page
        
        # Note: The actual PFD site may use different filter mechanisms
        # This may need adjustment based on actual site behavior
        
        if params:
            return f"{base}?{urlencode(params)}"
        return base
    
    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from PFD report URL.
        
        Args:
            url: Full report URL
            
        Returns:
            External ID string
        """
        # URL patterns:
        # /pfd/report-name-123/
        # /prevention-of-future-death-reports/report-name/
        
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        
        # Get last path segment
        segments = path.split("/")
        if segments:
            return segments[-1]
        
        # Fallback to full path hash
        return path.replace("/", "-")
    
    def _parse_uk_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse UK-formatted date string.
        
        Args:
            date_text: Date string (e.g., "15 January 2026", "15/01/2026")
            
        Returns:
            Parsed datetime or None
        """
        if not date_text:
            return None
        
        # Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_text)
        cleaned = cleaned.strip()
        
        # Try various formats
        formats = [
            "%d %B %Y",      # 15 January 2026
            "%d %b %Y",      # 15 Jan 2026
            "%d/%m/%Y",      # 15/01/2026
            "%d-%m-%Y",      # 15-01-2026
            "%Y-%m-%d",      # 2026-01-15
            "%d.%m.%Y",      # 15.01.2026
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        
        self.logger.debug(f"Could not parse date: {date_text}")
        return None
    
    def _is_healthcare_category(self, categories: list[str]) -> bool:
        """
        Check if categories include healthcare-related ones.
        
        Args:
            categories: List of category strings from the report
            
        Returns:
            True if likely healthcare-related
        """
        if not self.categories:
            # No filtering configured, accept all
            return True
        
        categories_lower = [c.lower() for c in categories]
        
        for healthcare_cat in self.categories:
            healthcare_lower = healthcare_cat.lower()
            # Check for substring match
            for cat in categories_lower:
                if healthcare_lower in cat or cat in healthcare_lower:
                    return True
        
        return False


# Register scraper with factory
ScraperFactory.register("uk_pfd", UKPFDScraper)
