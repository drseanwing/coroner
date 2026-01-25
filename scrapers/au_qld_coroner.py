"""
Patient Safety Monitor - Queensland Coroner Scraper

Scraper for Queensland Coroners Court findings.
Source: https://www.courts.qld.gov.au/courts/coroners-court/findings

Queensland publishes coroner findings with PDF documents.
Less frequent updates than VIC/NSW, scheduled weekly.
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


class QLDCoronerScraper(BaseScraper):
    """
    Scraper for Queensland Coroners Court findings.

    The Queensland Courts website publishes coroner findings with
    healthcare-related cases that may indicate systemic issues.

    Site structure:
        - Main listing: /courts/coroners-court/findings
        - Individual findings as HTML pages with linked PDFs
        - Pagination via query parameters
        - Less frequent updates than VIC/NSW
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
        "mental health",
    ]

    # CSS selectors for the Queensland Courts website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": "div.finding-item, article.finding, div.result-item",
        "title": "h2 a, h3 a, .finding-title a",
        "date": ".finding-date, .date-published, .published-date",
        "link": "a[href*='finding'], a.finding-link",
        "pagination": "a.next, .pagination a[rel='next']",

        # Detail page selectors
        "content": ".finding-content, .content-body, article",
        "pdf_link": "a[href$='.pdf'], a[href*='/pdf/']",
        "deceased_name": ".deceased-name, .finding-deceased",
        "date_of_death": ".date-of-death, .dod",
        "coroner_name": ".coroner-name, .finding-coroner",
        "inquest_date": ".inquest-date, .date-of-inquest",
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

        # Rate limiting - be respectful to government sites
        self.request_delay = config.get("request_delay", 2.0)

    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.

        Scrapes Queensland coroner findings, filtering for healthcare-related
        cases based on keywords in title and content.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting QLD Coroner scrape",
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

                            # Filter by healthcare keywords
                            if self._is_healthcare_related(finding):
                                all_findings.append(finding)
                            else:
                                self.logger.debug(
                                    f"Skipping non-healthcare finding",
                                    extra={"title": finding.title[:50]},
                                )

                        except Exception as e:
                            self.logger.warning(
                                f"Failed to fetch detail page",
                                extra={
                                    "external_id": finding.external_id,
                                    "error": str(e),
                                },
                            )
                            warnings.append(f"Detail fetch failed: {finding.external_id}")
                            # Still add the finding with partial data if it matches keywords
                            if self._is_healthcare_related(finding):
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
            f"QLD Coroner scrape completed",
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
        Parse a Queensland coroner findings listing page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Find all finding items - try multiple selectors
        items = soup.select(self.selectors["list_container"])

        # Fallback: if no items found, try alternative structure
        if not items:
            items = soup.find_all("div", class_=lambda x: x and ("finding" in x.lower() or "result" in x.lower()))

        self.logger.debug(f"Found {len(items)} items on listing page")

        for item in items:
            try:
                # Extract title and link - try multiple selectors
                title_elem = item.select_one(self.selectors["title"])
                if not title_elem:
                    # Fallback: find any link in the item
                    title_elem = item.find("a", href=True)

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
                    categories=["qld_coroner"],
                    metadata={
                        "scraped_at": datetime.utcnow().isoformat(),
                        "scraper_version": "1.0.0",
                        "jurisdiction": "queensland",
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
        Parse an individual Queensland coroner finding page.

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

            # Download and extract PDF text if available
            try:
                pdf_bytes, _ = await self.download_pdf(finding.pdf_url)
                pdf_text = self.extract_text_from_pdf(pdf_bytes)

                # Combine HTML and PDF text
                if finding.content_text and pdf_text:
                    finding.content_text = f"{finding.content_text}\n\n--- PDF CONTENT ---\n\n{pdf_text}"
                elif pdf_text:
                    finding.content_text = pdf_text

            except Exception as e:
                self.logger.warning(
                    f"Failed to extract PDF text",
                    extra={"pdf_url": finding.pdf_url, "error": str(e)},
                )

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
            finding.date_of_death = self._parse_au_date(dod_text)

        # Extract coroner name if available
        coroner_elem = soup.select_one(self.selectors["coroner_name"])
        if coroner_elem:
            coroner_text = coroner_elem.get_text(strip=True)
            finding.coroner_name = re.sub(r"^Coroner:\s*", "", coroner_text, flags=re.I)

        # Extract inquest date if available
        inquest_elem = soup.select_one(self.selectors["inquest_date"])
        if inquest_elem:
            inquest_text = inquest_elem.get_text(strip=True)
            inquest_date = self._parse_au_date(inquest_text)
            if inquest_date:
                finding.metadata["inquest_date"] = inquest_date.isoformat()

        return finding

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_listing_url(self, page: int = 1) -> str:
        """
        Build listing URL with pagination parameters.

        Args:
            page: Page number (1-indexed)

        Returns:
            Full URL with query parameters
        """
        base = self.base_url.rstrip("/")

        params = {}
        if page > 1:
            # Queensland may use different pagination parameter names
            # Common patterns: page, p, offset
            params["page"] = page

        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from Queensland finding URL.

        Args:
            url: Full finding URL

        Returns:
            External ID string
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment
        segments = path.split("/")
        if segments:
            # Use last segment or combination of last 2 if short
            last = segments[-1]
            if len(last) < 5 and len(segments) > 1:
                last = f"{segments[-2]}_{segments[-1]}"
            return last

        # Fallback to full path hash
        return path.replace("/", "-")

    def _parse_au_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse Australian-formatted date string.

        Handles DD/MM/YYYY and DD Month YYYY formats common in Australia.

        Args:
            date_text: Date string (e.g., "15/01/2026", "15 January 2026")

        Returns:
            Parsed datetime or None
        """
        if not date_text:
            return None

        # Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_text)
        cleaned = cleaned.strip()

        # Try various Australian date formats
        formats = [
            "%d/%m/%Y",      # 15/01/2026 (most common in AU)
            "%d-%m-%Y",      # 15-01-2026
            "%d %B %Y",      # 15 January 2026
            "%d %b %Y",      # 15 Jan 2026
            "%d.%m.%Y",      # 15.01.2026
            "%Y-%m-%d",      # 2026-01-15 (ISO format)
            "%d %B, %Y",     # 15 January, 2026
            "%B %d, %Y",     # January 15, 2026
        ]

        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        self.logger.debug(f"Could not parse date: {date_text}")
        return None

    def _is_healthcare_related(self, finding: ScrapedFinding) -> bool:
        """
        Check if finding is healthcare-related based on keywords.

        Searches title and content for healthcare-related terms.

        Args:
            finding: Scraped finding to check

        Returns:
            True if healthcare-related
        """
        if not self.keywords:
            # No filtering configured, accept all
            return True

        # Combine searchable text
        searchable_text = []
        if finding.title:
            searchable_text.append(finding.title.lower())
        if finding.content_text:
            searchable_text.append(finding.content_text.lower())

        if not searchable_text:
            # No text to search, be conservative and include it
            return True

        combined = " ".join(searchable_text)

        # Check for any keyword match
        for keyword in self.keywords:
            if keyword.lower() in combined:
                self.logger.debug(
                    f"Matched healthcare keyword: {keyword}",
                    extra={"external_id": finding.external_id},
                )
                return True

        return False


# Register scraper with factory
ScraperFactory.register("au_qld", QLDCoronerScraper)
