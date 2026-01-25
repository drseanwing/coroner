"""
Patient Safety Monitor - Victoria Coroner's Court Scraper

Scraper for Victoria Coroner's Court findings.
Source: https://www.coronerscourt.vic.gov.au/inquests-findings

Scrapes searchable database of coroner findings with category filters.
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


class VICCoronerScraper(BaseScraper):
    """
    Scraper for Victoria Coroner's Court findings.

    The Victoria Coroner's Court publishes findings from coronial investigations.
    This scraper focuses on healthcare-related cases.

    Site structure:
        - Main listing: /inquests-findings
        - Category filters via URL parameters or dynamic loading
        - Individual findings as HTML pages with PDF attachments
        - May use dynamic content loading (Playwright required)
    """

    # Healthcare-related keywords for filtering
    HEALTHCARE_KEYWORDS = [
        "hospital",
        "medical",
        "health",
        "clinical",
        "patient",
        "nurse",
        "doctor",
        "ambulance",
    ]

    # CSS selectors for the Victoria Coroner's website
    # These will need to be verified/adjusted based on actual site structure
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": ".finding-item, .inquest-item, article",
        "title": "h2, h3, .title",
        "title_link": "a",
        "date": ".date, .published-date, .finding-date",
        "deceased_name": ".deceased-name, .name",
        "categories": ".category, .tags a",
        "summary": ".summary, .excerpt",
        "pagination": ".pagination a.next, .next-page",

        # Detail page selectors
        "content": ".content, .finding-content, .entry-content",
        "pdf_link": "a[href*='.pdf']",
        "coroner_name": ".coroner-name, .presiding-coroner",
        "date_of_death": ".date-of-death",
        "date_of_finding": ".date-of-finding, .finding-date",
        "inquest_details": ".inquest-details",
    }

    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(source_code, base_url, config)

        # Configuration
        self.healthcare_keywords = config.get("healthcare_keywords", self.HEALTHCARE_KEYWORDS)
        self.max_pages = config.get("max_pages", 10)
        self.selectors = {**self.DEFAULT_SELECTORS, **config.get("selectors", {})}
        self.use_browser = config.get("use_browser", True)  # May need Playwright for dynamic content

        # Rate limiting
        self.request_delay = config.get("request_delay", 2.0)

    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.

        Scrapes findings from Victoria Coroner's Court, filtering
        for healthcare-related cases.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting Victoria Coroner scrape",
            extra={
                "max_pages": self.max_pages,
                "use_browser": self.use_browser,
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

                    # Fetch listing page (may use browser for dynamic content)
                    page_content = await self.fetch_page(
                        current_url,
                        use_browser=self.use_browser,
                        wait_for_selector=self.selectors.get("list_container"),
                    )

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

                            detail_content = await self.fetch_page(
                                finding.source_url,
                                use_browser=self.use_browser,
                            )
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
            f"Victoria Coroner scrape completed",
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
        Parse a Victoria Coroner listing page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Find all finding items
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

                # Try to find link - might be nested in title or separate
                link_elem = title_elem if title_elem.name == "a" else title_elem.select_one(self.selectors["title_link"])
                if not link_elem:
                    # Try to find any link in the item
                    link_elem = item.select_one("a")

                if not link_elem or not link_elem.get("href"):
                    self.logger.debug(f"Skipping item without link: {title[:50]}")
                    continue

                href = link_elem["href"]
                source_url = urljoin(page_url, href)

                # Get summary/excerpt text to check for healthcare keywords
                summary_text = ""
                summary_elem = item.select_one(self.selectors["summary"])
                if summary_elem:
                    summary_text = summary_elem.get_text(strip=True).lower()
                else:
                    # Use all text from item if no specific summary
                    summary_text = item.get_text(strip=True).lower()

                # Also check title for keywords
                full_text = f"{title.lower()} {summary_text}"

                # Filter by healthcare keywords
                if not self._is_healthcare_related(full_text):
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
                    date_text = date_elem.get_text(strip=True)
                    date_of_finding = self._parse_au_date(date_text)

                # Get deceased name if available
                deceased_name = None
                deceased_elem = item.select_one(self.selectors["deceased_name"])
                if deceased_elem:
                    deceased_name = deceased_elem.get_text(strip=True)
                    # Clean up prefix like "Name: " or "Deceased: "
                    deceased_name = re.sub(r"^(Deceased|Name):\s*", "", deceased_name, flags=re.I)

                # Get categories if available
                categories = []
                category_elems = item.select(self.selectors["categories"])
                for cat_elem in category_elems:
                    cat_text = cat_elem.get_text(strip=True)
                    if cat_text:
                        categories.append(cat_text)

                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    deceased_name=deceased_name,
                    categories=categories,
                    metadata={
                        "scraped_at": datetime.utcnow().isoformat(),
                        "scraper_version": "1.0.0",
                        "summary": summary_text[:500] if summary_text else None,
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
        Parse an individual Victoria Coroner finding page.

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

        # Extract coroner name if available
        coroner_elem = soup.select_one(self.selectors["coroner_name"])
        if coroner_elem:
            coroner_text = coroner_elem.get_text(strip=True)
            coroner_text = re.sub(r"^(Coroner|Presiding Coroner):\s*", "", coroner_text, flags=re.I)
            finding.coroner_name = coroner_text

        # Extract deceased name from detail page if not already set
        if not finding.deceased_name:
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
            finding.date_of_death = self._parse_au_date(dod_text)

        # Update date of finding from detail page if not already set
        if not finding.date_of_finding:
            date_elem = soup.select_one(self.selectors["date_of_finding"])
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                date_text = re.sub(r"^(Date of finding|Finding date):\s*", "", date_text, flags=re.I)
                finding.date_of_finding = self._parse_au_date(date_text)

        # Extract inquest details if available
        inquest_elem = soup.select_one(self.selectors["inquest_details"])
        if inquest_elem:
            finding.metadata["inquest_details"] = inquest_elem.get_text(strip=True)

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

        # The actual pagination mechanism may vary
        # Common patterns: ?page=N, ?p=N, /page/N/
        params = {}
        if page > 1:
            params["page"] = page
            # OR it might be: params["p"] = page
            # OR URL might be: f"{base}/page/{page}/"

        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from finding URL.

        Args:
            url: Full finding URL

        Returns:
            External ID string
        """
        # URL patterns might be:
        # /finding/123/
        # /inquest/finding-name-123/
        # /inquests-findings/2026/finding-name/

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment as ID
        segments = path.split("/")
        if segments:
            # Try to extract numeric ID if present
            last_segment = segments[-1]
            numeric_match = re.search(r'(\d+)', last_segment)
            if numeric_match:
                return f"vic_{numeric_match.group(1)}"
            return f"vic_{last_segment}"

        # Fallback to full path hash
        return f"vic_{path.replace('/', '-')}"

    def _parse_au_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse Australian-formatted date string.

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
            True if healthcare-related
        """
        if not self.healthcare_keywords:
            # No filtering configured, accept all
            return True

        text_lower = text.lower()

        for keyword in self.healthcare_keywords:
            if keyword.lower() in text_lower:
                return True

        return False


# Register scraper with factory
ScraperFactory.register("au_vic", VICCoronerScraper)
