"""
Patient Safety Monitor - NZ Health and Disability Commissioner Scraper

Scraper for NZ Health and Disability Commissioner decisions database.
Source: https://www.hdc.org.nz/decisions/

Well-structured HTML with categorization by provider type.
Focus on healthcare providers including hospitals, rest homes, and mental health.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlencode, urlparse

from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    ScrapedFinding,
    ScrapeResult,
    ScraperFactory,
)


logger = logging.getLogger(__name__)


class NZHDCScraper(BaseScraper):
    """
    Scraper for NZ Health and Disability Commissioner decisions.

    The HDC publishes decisions about complaints related to health
    and disability services in New Zealand.

    Site structure:
        - Main listing: /decisions/
        - Category filtering via URL parameters
        - Individual decisions as HTML pages
        - Pagination via page parameter
    """

    # Healthcare-related categories to filter
    HEALTHCARE_CATEGORIES = [
        "Public hospital",
        "Private hospital",
        "Rest home",
        "Mental health",
        "Medical centre",
        "Pharmacy",
        "Aged care",
        "Disability services",
        "Community health",
    ]

    # CSS selectors for the HDC website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": ".decision-item, .search-result-item, article.decision",
        "title": "h2 a, h3 a, .decision-title a",
        "date": ".decision-date, .date, time",
        "categories": ".decision-category, .category, .provider-type",
        "case_number": ".case-number, .reference",
        "pagination": ".pagination a.next, .next-page",

        # Detail page selectors
        "content": ".decision-content, .entry-content, main article",
        "pdf_link": "a[href*='.pdf']",
        "provider_name": ".provider-name, .respondent",
        "provider_type": ".provider-type, .service-type",
        "case_details": ".case-details, .decision-details",
        "outcome": ".decision-outcome, .outcome",
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

        Scrapes HDC decisions from the NZ HDC website, filtering
        for healthcare-related categories.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting NZ HDC scrape",
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
            f"NZ HDC scrape completed",
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
        Parse an HDC listing page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Find all decision items - try multiple selectors
        items = []
        for selector in self.selectors["list_container"].split(", "):
            items = soup.select(selector.strip())
            if items:
                break

        self.logger.debug(f"Found {len(items)} items on listing page")

        for item in items:
            try:
                # Extract title and link
                title_elem = None
                for selector in self.selectors["title"].split(", "):
                    title_elem = item.select_one(selector.strip())
                    if title_elem:
                        break

                if not title_elem:
                    self.logger.debug("Skipping item without title")
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")

                if not href:
                    self.logger.debug(f"Skipping item without link: {title[:50]}")
                    continue

                source_url = urljoin(page_url, href)

                # Generate external ID from URL or case number
                case_number = None
                case_number_elem = None
                for selector in self.selectors["case_number"].split(", "):
                    case_number_elem = item.select_one(selector.strip())
                    if case_number_elem:
                        case_number = case_number_elem.get_text(strip=True)
                        # Clean up prefixes like "Case: " or "Ref: "
                        case_number = re.sub(r"^(Case|Ref|Reference):\s*", "", case_number, flags=re.I)
                        break

                if case_number:
                    external_id = case_number
                else:
                    external_id = self._extract_external_id(source_url)

                # Parse date
                date_of_finding = None
                date_elem = None
                for selector in self.selectors["date"].split(", "):
                    date_elem = item.select_one(selector.strip())
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        # Check for datetime attribute (if it's a <time> element)
                        if date_elem.get("datetime"):
                            date_text = date_elem["datetime"]
                        date_of_finding = self._parse_nz_date(date_text)
                        break

                # Get categories
                categories = []
                for selector in self.selectors["categories"].split(", "):
                    category_elems = item.select(selector.strip())
                    for cat_elem in category_elems:
                        cat_text = cat_elem.get_text(strip=True)
                        if cat_text:
                            categories.append(cat_text)
                    if categories:
                        break

                # Filter by healthcare categories if configured
                if self.categories and not self._is_healthcare_category(categories):
                    self.logger.debug(
                        f"Skipping non-healthcare finding",
                        extra={"title": title[:50], "categories": categories},
                    )
                    continue

                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    categories=categories,
                    metadata={
                        "case_number": case_number or external_id,
                        "scraped_at": datetime.utcnow().isoformat(),
                        "scraper_version": "1.0.0",
                    },
                )
                findings.append(finding)

            except Exception as e:
                self.logger.warning(f"Failed to parse listing item: {e}")

        # Find next page link
        next_url = None
        for selector in self.selectors["pagination"].split(", "):
            next_link = soup.select_one(selector.strip())
            if next_link and next_link.get("href"):
                next_url = urljoin(page_url, next_link["href"])
                self.logger.debug(f"Found next page: {next_url}")
                break

        return findings, next_url

    async def parse_finding_page(
        self,
        page_content: str,
        finding: ScrapedFinding,
    ) -> ScrapedFinding:
        """
        Parse an individual HDC decision page.

        Args:
            page_content: HTML content of finding page
            finding: Partial finding from listing

        Returns:
            Completed finding with all details
        """
        soup = BeautifulSoup(page_content, "lxml")

        # Extract main content
        content_elem = None
        for selector in self.selectors["content"].split(", "):
            content_elem = soup.select_one(selector.strip())
            if content_elem:
                finding.content_html = str(content_elem)
                finding.content_text = content_elem.get_text(separator="\n", strip=True)
                break

        # Find PDF link
        pdf_link = soup.select_one(self.selectors["pdf_link"])
        if pdf_link and pdf_link.get("href"):
            finding.pdf_url = urljoin(finding.source_url, pdf_link["href"])

        # Extract provider name if available
        for selector in self.selectors["provider_name"].split(", "):
            provider_elem = soup.select_one(selector.strip())
            if provider_elem:
                provider_text = provider_elem.get_text(strip=True)
                provider_text = re.sub(r"^(Provider|Respondent):\s*", "", provider_text, flags=re.I)
                finding.metadata["provider_name"] = provider_text
                break

        # Extract provider type if available
        for selector in self.selectors["provider_type"].split(", "):
            type_elem = soup.select_one(selector.strip())
            if type_elem:
                type_text = type_elem.get_text(strip=True)
                type_text = re.sub(r"^(Provider type|Service type):\s*", "", type_text, flags=re.I)
                finding.metadata["provider_type"] = type_text
                # Add to categories if not already present
                if type_text and type_text not in finding.categories:
                    finding.categories.append(type_text)
                break

        # Extract case details
        for selector in self.selectors["case_details"].split(", "):
            details_elem = soup.select_one(selector.strip())
            if details_elem:
                finding.metadata["case_details"] = details_elem.get_text(separator="\n", strip=True)
                break

        # Extract outcome/decision
        for selector in self.selectors["outcome"].split(", "):
            outcome_elem = soup.select_one(selector.strip())
            if outcome_elem:
                finding.metadata["outcome"] = outcome_elem.get_text(strip=True)
                break

        return finding

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_listing_url(self, page: int = 1) -> str:
        """
        Build listing URL with pagination.

        Args:
            page: Page number (1-indexed)

        Returns:
            Full URL with query parameters
        """
        base = self.base_url.rstrip("/")

        params = {}
        if page > 1:
            # HDC site might use different pagination parameter
            # Common patterns: page=N, p=N, offset=N
            params["page"] = page

        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from HDC decision URL.

        Args:
            url: Full decision URL

        Returns:
            External ID string
        """
        # URL patterns:
        # /decisions/decision-name-123/
        # /decisions/2026/case-123/

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment
        segments = path.split("/")
        if segments:
            return segments[-1]

        # Fallback to full path hash
        return path.replace("/", "-")

    def _parse_nz_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse NZ-formatted date string.

        Args:
            date_text: Date string (e.g., "15 January 2026", "15/01/2026", ISO format)

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
            "%Y-%m-%dT%H:%M:%S",  # ISO format with time
            "%Y-%m-%d",           # ISO date
            "%d %B %Y",           # 15 January 2026
            "%d %b %Y",           # 15 Jan 2026
            "%d/%m/%Y",           # 15/01/2026 (NZ format)
            "%d-%m-%Y",           # 15-01-2026
            "%d.%m.%Y",           # 15.01.2026
            "%B %d, %Y",          # January 15, 2026
            "%b %d, %Y",          # Jan 15, 2026
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
            categories: List of category strings from the decision

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
ScraperFactory.register("nz_hdc", NZHDCScraper)
