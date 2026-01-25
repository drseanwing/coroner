"""
Patient Safety Monitor - NZ Coronial Services Scraper

Scraper for New Zealand Coronial Services findings database.
Source: https://coronialservices.justice.govt.nz/findings/

Filters for healthcare-related cases using keyword matching.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    ScrapedFinding,
    ScrapeResult,
    ScraperFactory,
)


logger = logging.getLogger(__name__)


class NZCoronerScraper(BaseScraper):
    """
    Scraper for NZ Coronial Services findings.

    The NZ Ministry of Justice publishes coronial findings from investigations
    into deaths. This scraper filters for healthcare-related cases.

    Site structure:
        - Main listing: /findings/
        - Search/filter functionality
        - Individual findings as HTML pages with potential PDF attachments
        - Pagination (mechanism to be determined)
    """

    # Healthcare-related keywords for filtering
    HEALTHCARE_KEYWORDS = [
        "hospital",
        "medical",
        "health",
        "clinical",
        "patient",
        "ambulance",
        "nurse",
        "doctor",
        "surgery",
        "treatment",
        "medication",
        "diagnosis",
        "emergency department",
        "ward",
        "ICU",
        "intensive care",
        "GP",
        "practitioner",
        "healthcare",
        "paramedic",
        "pharmacy",
        "pharmacist",
        "mental health",
        "psychiatric",
    ]

    # CSS selectors for the NZ Coronial Services website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": ".finding-item, .search-result, article",
        "title": "h2 a, h3 a, .finding-title a",
        "date": ".finding-date, .date, time",
        "excerpt": ".finding-excerpt, .excerpt, .summary",
        "link": "a[href*='finding'], a.read-more",
        "pagination": ".pagination a.next, .next-page",

        # Detail page selectors
        "content": ".finding-content, .entry-content, article .content",
        "pdf_link": "a[href*='.pdf']",
        "deceased_name": ".deceased-name, .deceased, .name-deceased",
        "date_of_death": ".date-of-death, .death-date",
        "date_of_finding": ".finding-date, .date-finding",
        "coroner": ".coroner-name, .coroner",
        "location": ".location, .place-of-death",
    }

    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(source_code, base_url, config)

        # Configuration
        self.keywords = config.get("keywords", self.HEALTHCARE_KEYWORDS)
        self.max_pages = config.get("max_pages", 10)
        self.selectors = {**self.DEFAULT_SELECTORS, **config.get("selectors", {})}

        # Rate limiting - be more conservative for NZ site
        self.request_delay = config.get("request_delay", 2.0)
        self._min_request_interval = self.request_delay

    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.

        Scrapes coronial findings from the NZ Coronial Services website,
        filtering for healthcare-related cases.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting NZ Coroner scrape",
            extra={
                "max_pages": self.max_pages,
                "keywords": len(self.keywords),
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
                        f"Found {len(findings)} healthcare findings on page",
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
            f"NZ Coroner scrape completed",
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
        Parse a NZ coronial findings listing page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Try different container selectors
        items = None
        for selector in self.selectors["list_container"].split(", "):
            items = soup.select(selector)
            if items:
                break

        if not items:
            self.logger.warning("No items found with configured selectors")
            return findings, None

        self.logger.debug(f"Found {len(items)} items on listing page")

        for item in items:
            try:
                # Extract title and link
                title_elem = None
                for selector in self.selectors["title"].split(", "):
                    title_elem = item.select_one(selector)
                    if title_elem:
                        break

                if not title_elem:
                    # Try to find any link in the item
                    link_elem = item.select_one(self.selectors["link"])
                    if link_elem:
                        title_elem = link_elem

                if not title_elem:
                    self.logger.debug("Skipping item without title/link")
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")

                if not href:
                    self.logger.debug(f"Skipping item without link: {title[:50]}")
                    continue

                source_url = urljoin(page_url, href)

                # Extract excerpt/summary for healthcare filtering
                excerpt = ""
                excerpt_elem = item.select_one(self.selectors["excerpt"])
                if excerpt_elem:
                    excerpt = excerpt_elem.get_text(strip=True)

                # Combine title and excerpt for filtering
                filter_text = f"{title} {excerpt}".lower()

                # Filter by healthcare keywords
                if not self._is_healthcare_related(filter_text):
                    self.logger.debug(
                        f"Skipping non-healthcare finding",
                        extra={"title": title[:50]},
                    )
                    continue

                # Generate external ID from URL
                external_id = self._extract_external_id(source_url)

                # Parse date
                date_of_finding = None
                date_elem = item.select_one(self.selectors["date"])
                if date_elem:
                    # Try datetime attribute first
                    date_text = date_elem.get("datetime", "")
                    if not date_text:
                        date_text = date_elem.get_text(strip=True)
                    date_of_finding = self._parse_nz_date(date_text)

                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    metadata={
                        "scraped_at": datetime.utcnow().isoformat(),
                        "scraper_version": "1.0.0",
                        "excerpt": excerpt[:200] if excerpt else None,
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
        Parse an individual NZ coronial finding page.

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
            content_elem = soup.select_one(selector)
            if content_elem:
                break

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
            # Clean up common prefixes
            deceased_text = re.sub(
                r"^(Deceased|Name|The late):\s*",
                "",
                deceased_text,
                flags=re.I
            )
            finding.deceased_name = deceased_text or None

        # Extract date of death if available
        dod_elem = soup.select_one(self.selectors["date_of_death"])
        if dod_elem:
            dod_text = dod_elem.get("datetime", "")
            if not dod_text:
                dod_text = dod_elem.get_text(strip=True)
            dod_text = re.sub(r"^Date of death:\s*", "", dod_text, flags=re.I)
            finding.date_of_death = self._parse_nz_date(dod_text)

        # Extract date of finding if not already set
        if not finding.date_of_finding:
            dof_elem = soup.select_one(self.selectors["date_of_finding"])
            if dof_elem:
                dof_text = dof_elem.get("datetime", "")
                if not dof_text:
                    dof_text = dof_elem.get_text(strip=True)
                dof_text = re.sub(r"^Date of finding:\s*", "", dof_text, flags=re.I)
                finding.date_of_finding = self._parse_nz_date(dof_text)

        # Extract coroner name
        coroner_elem = soup.select_one(self.selectors["coroner"])
        if coroner_elem:
            coroner_text = coroner_elem.get_text(strip=True)
            coroner_text = re.sub(r"^(Coroner|By):\s*", "", coroner_text, flags=re.I)
            finding.coroner_name = coroner_text or None

        # Extract location/place of death
        location_elem = soup.select_one(self.selectors["location"])
        if location_elem:
            location_text = location_elem.get_text(strip=True)
            finding.metadata["location"] = location_text

        # Extract categories if present
        categories = []
        category_elems = soup.select(".category, .tag, .finding-type")
        for cat_elem in category_elems:
            cat_text = cat_elem.get_text(strip=True)
            if cat_text:
                categories.append(cat_text)

        if categories:
            finding.categories = categories

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
            # Common pagination patterns - may need adjustment
            params["page"] = page

        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from NZ coronial finding URL.

        Args:
            url: Full finding URL

        Returns:
            External ID string
        """
        # URL patterns to handle:
        # /findings/finding-name-2026/
        # /findings/123/
        # /findings/finding-name/

        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment
        segments = path.split("/")
        if segments:
            # Use last segment as ID
            return segments[-1]

        # Fallback to full path hash
        return path.replace("/", "-")

    def _parse_nz_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse NZ-formatted date string.

        NZ typically uses day/month/year format similar to UK.

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
            "%Y-%m-%d",      # 2026-01-15 (ISO format)
            "%d.%m.%Y",      # 15.01.2026
            "%B %d, %Y",     # January 15, 2026
            "%b %d, %Y",     # Jan 15, 2026
            "%Y-%m-%dT%H:%M:%S",  # ISO datetime
            "%Y-%m-%dT%H:%M:%S.%f",  # ISO datetime with microseconds
        ]

        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        # Try to extract just the date part from longer strings
        date_match = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", cleaned)
        if date_match:
            date_part = date_match.group(0)
            for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
                try:
                    return datetime.strptime(date_part, fmt)
                except ValueError:
                    continue

        self.logger.debug(f"Could not parse date: {date_text}")
        return None

    def _is_healthcare_related(self, text: str) -> bool:
        """
        Check if text contains healthcare-related keywords.

        Args:
            text: Text to check (title + excerpt, already lowercased)

        Returns:
            True if healthcare-related
        """
        if not self.keywords:
            # No filtering configured, accept all
            return True

        for keyword in self.keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in text:
                self.logger.debug(f"Matched keyword: {keyword}")
                return True

        return False


# Register scraper with factory
ScraperFactory.register("nz_coroner", NZCoronerScraper)
