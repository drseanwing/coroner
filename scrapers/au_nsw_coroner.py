"""
Patient Safety Monitor - NSW Coroner's Court Scraper

Scraper for NSW Coroner's Court coronial findings.
Source: https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html

Extracts coronial findings with a focus on healthcare-related deaths.
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


class NSWCoronerScraper(BaseScraper):
    """
    Scraper for NSW Coroner's Court coronial findings.

    The NSW Coroner's Court publishes findings from coronial inquests
    which may include recommendations to prevent future deaths.

    Site structure:
        - Main search page: /coroners-court/coronial-findings-search.html
        - Search results with filters
        - Individual finding pages with PDF documents
        - Pagination via URL parameters
    """

    # Healthcare-related keywords for filtering
    HEALTHCARE_KEYWORDS = [
        "hospital",
        "medical",
        "health",
        "clinical",
        "patient",
        "ambulance",
        "doctor",
        "nurse",
        "treatment",
        "surgery",
        "emergency department",
        "intensive care",
        "mental health",
    ]

    # CSS selectors for the NSW Coroner's Court website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": "div.search-result",
        "title": "h3 a, h4 a",
        "date": "span.date, .result-date",
        "summary": "div.summary, p.summary",
        "link": "a.result-link, h3 a, h4 a",
        "pagination": "a.next, .pagination a[rel='next']",

        # Detail page selectors
        "content": "div.content, .page-content, main article",
        "pdf_link": "a[href*='.pdf'], a.pdf-link",
        "deceased_name": ".deceased-name, .field-deceased",
        "date_of_death": ".date-of-death, .field-date-of-death",
        "date_of_finding": ".date-of-finding, .field-date-finding",
        "coroner_name": ".coroner-name, .field-coroner",
        "court_location": ".court-location, .field-location",
    }

    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(source_code, base_url, config)

        # Configuration
        self.keywords = config.get("healthcare_keywords", self.HEALTHCARE_KEYWORDS)
        self.max_pages = config.get("max_pages", 10)
        self.selectors = {**self.DEFAULT_SELECTORS, **config.get("selectors", {})}

        # Rate limiting - be respectful to Australian government site
        self.request_delay = config.get("request_delay", 2.0)
        self._min_request_interval = self.request_delay

    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.

        Scrapes coronial findings from the NSW Coroner's Court website,
        filtering for healthcare-related cases.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting NSW Coroner scrape",
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
            current_url: Optional[str] = self._build_search_url(page=1)

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

                            # Try to download and extract PDF if available
                            if finding.pdf_url:
                                try:
                                    await asyncio.sleep(self.request_delay)
                                    pdf_bytes, _ = await self.download_pdf(finding.pdf_url)
                                    pdf_text = self.extract_text_from_pdf(pdf_bytes)

                                    # Append PDF text to content
                                    if pdf_text:
                                        if finding.content_text:
                                            finding.content_text += f"\n\n--- PDF Content ---\n\n{pdf_text}"
                                        else:
                                            finding.content_text = pdf_text

                                    finding.metadata["pdf_extracted"] = True
                                    finding.metadata["pdf_length"] = len(pdf_text) if pdf_text else 0

                                except Exception as e:
                                    self.logger.warning(
                                        f"Failed to extract PDF",
                                        extra={
                                            "external_id": finding.external_id,
                                            "pdf_url": finding.pdf_url,
                                            "error": str(e),
                                        },
                                    )
                                    finding.metadata["pdf_extracted"] = False
                                    warnings.append(f"PDF extraction failed: {finding.external_id}")

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
                        current_url = self._build_search_url(page=pages_scraped + 2)

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
            f"NSW Coroner scrape completed",
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
        Parse a NSW Coroner search results page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Find all search result items
        items = soup.select(self.selectors["list_container"])
        self.logger.debug(f"Found {len(items)} items on listing page")

        for item in items:
            try:
                # Extract title and link
                link_elem = item.select_one(self.selectors["link"])
                if not link_elem:
                    self.logger.debug("Skipping item without link")
                    continue

                title = link_elem.get_text(strip=True)
                href = link_elem.get("href", "")

                if not href:
                    self.logger.debug(f"Skipping item without href: {title[:50]}")
                    continue

                source_url = urljoin(page_url, href)

                # Generate external ID from URL
                external_id = self._extract_external_id(source_url)

                # Get summary/snippet for healthcare filtering
                summary = ""
                summary_elem = item.select_one(self.selectors["summary"])
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)

                # Filter by healthcare keywords
                combined_text = f"{title} {summary}".lower()
                if self.keywords and not self._is_healthcare_related(combined_text):
                    self.logger.debug(
                        f"Skipping non-healthcare finding",
                        extra={"title": title[:50]},
                    )
                    continue

                # Parse date if available
                date_of_finding = None
                date_elem = item.select_one(self.selectors["date"])
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    date_of_finding = self._parse_au_date(date_text)

                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    metadata={
                        "summary": summary,
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
        Parse an individual NSW Coroner finding page.

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
            finding.deceased_name = self.clean_text(deceased_text)

        # Extract date of death if available
        dod_elem = soup.select_one(self.selectors["date_of_death"])
        if dod_elem:
            dod_text = dod_elem.get_text(strip=True)
            dod_text = re.sub(r"^Date of death:\s*", "", dod_text, flags=re.I)
            finding.date_of_death = self._parse_au_date(dod_text)

        # Extract date of finding if not already set
        if not finding.date_of_finding:
            dof_elem = soup.select_one(self.selectors["date_of_finding"])
            if dof_elem:
                dof_text = dof_elem.get_text(strip=True)
                dof_text = re.sub(r"^Date of finding:\s*", "", dof_text, flags=re.I)
                finding.date_of_finding = self._parse_au_date(dof_text)

        # Extract coroner name
        coroner_elem = soup.select_one(self.selectors["coroner_name"])
        if coroner_elem:
            coroner_text = coroner_elem.get_text(strip=True)
            coroner_text = re.sub(r"^Coroner:\s*", "", coroner_text, flags=re.I)
            finding.coroner_name = self.clean_text(coroner_text)

        # Extract court location
        location_elem = soup.select_one(self.selectors["court_location"])
        if location_elem:
            finding.metadata["court_location"] = location_elem.get_text(strip=True)

        # Extract categories from content if available
        categories = self._extract_categories(finding.content_text or "")
        if categories:
            finding.categories = categories

        return finding

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_search_url(self, page: int = 1) -> str:
        """
        Build search URL with pagination.

        Args:
            page: Page number (1-indexed)

        Returns:
            Full URL with query parameters
        """
        base = self.base_url.rstrip("/")

        params = {}
        if page > 1:
            # Common NSW government pagination parameter
            params["page"] = page

        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from NSW Coroner finding URL.

        Args:
            url: Full finding URL

        Returns:
            External ID string
        """
        # URL patterns may vary:
        # /findings/2026/finding-name/
        # /finding-details/12345

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment
        segments = path.split("/")
        if segments:
            last_segment = segments[-1]
            # Clean up any .html extensions
            last_segment = re.sub(r"\.html?$", "", last_segment)
            return last_segment

        # Fallback to full path hash
        return path.replace("/", "-")

    def _parse_au_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse Australian-formatted date string.

        Handles various Australian date formats including day-first formats.

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

        # Try various Australian formats (day-first)
        formats = [
            "%d %B %Y",      # 15 January 2026
            "%d %b %Y",      # 15 Jan 2026
            "%d/%m/%Y",      # 15/01/2026 (Australian format)
            "%d-%m-%Y",      # 15-01-2026
            "%Y-%m-%d",      # 2026-01-15 (ISO)
            "%d.%m.%Y",      # 15.01.2026
            "%B %d, %Y",     # January 15, 2026
            "%b %d, %Y",     # Jan 15, 2026
        ]

        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        self.logger.debug(f"Could not parse date: {date_text}")
        return None

    def _is_healthcare_related(self, text: str) -> bool:
        """
        Check if text contains healthcare-related keywords.

        Args:
            text: Text to check (already lowercased)

        Returns:
            True if likely healthcare-related
        """
        if not self.keywords:
            # No filtering configured, accept all
            return True

        for keyword in self.keywords:
            if keyword.lower() in text:
                return True

        return False

    def _extract_categories(self, content: str) -> list[str]:
        """
        Extract healthcare categories from content text.

        Args:
            content: Full content text

        Returns:
            List of identified categories
        """
        categories = []
        content_lower = content.lower()

        # Define category patterns
        category_patterns = {
            "Hospital Death": ["hospital", "admitted to hospital", "hospitalised"],
            "Medical Treatment": ["medical treatment", "surgery", "surgical", "operation"],
            "Emergency Services": ["ambulance", "paramedic", "emergency department", "ed attendance"],
            "Mental Health": ["mental health", "psychiatric", "suicide", "self-harm"],
            "Clinical Care": ["clinical", "diagnosis", "treatment plan", "medical care"],
            "Patient Safety": ["patient safety", "adverse event", "medical error"],
        }

        for category, keywords in category_patterns.items():
            for keyword in keywords:
                if keyword in content_lower:
                    if category not in categories:
                        categories.append(category)
                    break

        return categories


# Register scraper with factory
ScraperFactory.register("au_nsw", NSWCoronerScraper)
