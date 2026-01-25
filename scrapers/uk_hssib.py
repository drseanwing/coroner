"""
Patient Safety Monitor - UK HSSIB Scraper

Scraper for UK Healthcare Safety Investigation Branch (HSSIB) reports.
Source: https://www.hssib.org.uk/patient-safety-investigations/

HSSIB conducts independent safety investigations into NHS-funded healthcare in England.
Each investigation produces a comprehensive report with findings and safety recommendations.
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


class HSSIBScraper(BaseScraper):
    """
    Scraper for UK Healthcare Safety Investigation Branch reports.

    HSSIB investigates patient safety incidents in NHS-funded care in England.
    Each investigation results in a published report with findings and
    safety recommendations.

    Site structure:
        - Main listing: /patient-safety-investigations/
        - Investigation pages with HTML summaries
        - Downloadable PDF reports
        - Categories/tags for investigation types
        - Pagination via URL parameters or links
    """

    # CSS selectors for the HSSIB website
    DEFAULT_SELECTORS = {
        # Listing page selectors
        "list_container": "article.investigation",
        "title": "h2 a, h3 a, .investigation-title a",
        "link": "a[href*='patient-safety-investigations']",
        "date": ".investigation-date, .published-date, time",
        "summary": ".investigation-summary, .excerpt, .entry-summary",
        "categories": ".investigation-category, .tags a, .category-tag",
        "pagination": ".pagination a.next, .next-page",

        # Detail page selectors
        "content": ".investigation-content, .entry-content, main article",
        "pdf_link": "a[href$='.pdf'], a:contains('Download PDF')",
        "reference": ".investigation-reference, .ref-number",
        "findings": ".findings, .key-findings",
        "recommendations": ".recommendations, .safety-recommendations",
        "responses": ".responses, .addressee-responses",
        "status": ".investigation-status",
    }

    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        super().__init__(source_code, base_url, config)

        # Configuration
        self.max_pages = config.get("max_pages", 10)
        self.selectors = {**self.DEFAULT_SELECTORS, **config.get("selectors", {})}

        # Rate limiting
        self.request_delay = config.get("request_delay", 2.0)

    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.

        Scrapes HSSIB investigation reports from the official website.

        Returns:
            ScrapeResult with all scraped findings
        """
        self.logger.info(
            f"Starting UK HSSIB scrape",
            extra={
                "max_pages": self.max_pages,
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
            current_url: Optional[str] = self.base_url

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

                            # Extract PDF content if available
                            if finding.pdf_url:
                                try:
                                    await asyncio.sleep(self.request_delay)
                                    pdf_bytes, _ = await self.download_pdf(finding.pdf_url)
                                    pdf_text = self.extract_text_from_pdf(pdf_bytes)

                                    # Append PDF text to content
                                    if pdf_text:
                                        finding.content_text = (
                                            f"{finding.content_text}\n\n"
                                            f"=== PDF CONTENT ===\n\n{pdf_text}"
                                            if finding.content_text
                                            else pdf_text
                                        )
                                        self.logger.debug(
                                            f"Extracted PDF text ({len(pdf_text)} chars)",
                                            extra={"external_id": finding.external_id},
                                        )
                                except Exception as e:
                                    self.logger.warning(
                                        f"Failed to extract PDF",
                                        extra={
                                            "external_id": finding.external_id,
                                            "error": str(e),
                                        },
                                    )
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
                        current_url = self._build_next_page_url(current_url, pages_scraped + 2)

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
            f"UK HSSIB scrape completed",
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
        Parse an HSSIB listing page.

        Args:
            page_content: HTML content of listing page
            page_url: URL of the page being parsed

        Returns:
            Tuple of (findings list, next page URL or None)
        """
        soup = BeautifulSoup(page_content, "lxml")
        findings: list[ScrapedFinding] = []

        # Find all investigation items
        items = soup.select(self.selectors["list_container"])

        # Fallback: if no items found with specific selector, try generic articles
        if not items:
            items = soup.select("article")
            self.logger.debug(f"Using fallback selector, found {len(items)} articles")

        self.logger.debug(f"Found {len(items)} items on listing page")

        for item in items:
            try:
                # Extract title and link
                title_elem = item.select_one(self.selectors["title"])

                # Fallback: try to find any link with investigation in URL
                if not title_elem:
                    title_elem = item.select_one(self.selectors["link"])

                # Fallback: try any heading with a link
                if not title_elem:
                    for heading in ["h2 a", "h3 a", "h4 a"]:
                        title_elem = item.select_one(heading)
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

                # Generate external ID from URL
                external_id = self._extract_external_id(source_url)

                # Parse date
                date_of_finding = None
                date_elem = item.select_one(self.selectors["date"])
                if date_elem:
                    # Try datetime attribute first
                    date_text = date_elem.get("datetime") or date_elem.get_text(strip=True)
                    date_of_finding = self._parse_uk_date(date_text)

                # Get summary if available
                summary = None
                summary_elem = item.select_one(self.selectors["summary"])
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)

                # Get categories/tags
                categories = []
                category_elems = item.select(self.selectors["categories"])
                for cat_elem in category_elems:
                    cat_text = cat_elem.get_text(strip=True)
                    if cat_text:
                        categories.append(cat_text)

                # Create finding
                finding = ScrapedFinding(
                    external_id=external_id,
                    title=title,
                    source_url=source_url,
                    date_of_finding=date_of_finding,
                    categories=categories,
                    content_text=summary,  # Use summary as initial content
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
        Parse an individual HSSIB investigation page.

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

        # Fallback: search for any PDF link
        if not pdf_link:
            pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))

        if pdf_link and pdf_link.get("href"):
            finding.pdf_url = urljoin(finding.source_url, pdf_link["href"])
            self.logger.debug(f"Found PDF: {finding.pdf_url}")

        # Extract investigation reference number
        ref_elem = soup.select_one(self.selectors["reference"])
        if ref_elem:
            ref_text = ref_elem.get_text(strip=True)
            ref_text = re.sub(r"^(Reference|Ref|Investigation):\s*", "", ref_text, flags=re.I)
            finding.metadata["investigation_reference"] = ref_text

        # Extract investigation status
        status_elem = soup.select_one(self.selectors["status"])
        if status_elem:
            status_text = status_elem.get_text(strip=True)
            finding.metadata["investigation_status"] = status_text

        # Extract findings section
        findings_elem = soup.select_one(self.selectors["findings"])
        if findings_elem:
            findings_text = findings_elem.get_text(separator="\n", strip=True)
            finding.metadata["key_findings"] = findings_text

        # Extract recommendations section
        recommendations_elem = soup.select_one(self.selectors["recommendations"])
        if recommendations_elem:
            recommendations_text = recommendations_elem.get_text(separator="\n", strip=True)
            finding.metadata["safety_recommendations"] = recommendations_text

        # Extract responses section
        responses_elem = soup.select_one(self.selectors["responses"])
        if responses_elem:
            responses_text = responses_elem.get_text(separator="\n", strip=True)
            finding.metadata["responses"] = responses_text

        # Update date if found in detail page and not already set
        if not finding.date_of_finding:
            date_elem = soup.select_one(self.selectors["date"])
            if date_elem:
                date_text = date_elem.get("datetime") or date_elem.get_text(strip=True)
                finding.date_of_finding = self._parse_uk_date(date_text)

        return finding

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_next_page_url(self, current_url: str, page: int) -> Optional[str]:
        """
        Build next page URL for pagination.

        Args:
            current_url: Current page URL
            page: Page number (1-indexed)

        Returns:
            Next page URL or None
        """
        # Common pagination patterns:
        # - /page/2/
        # - ?page=2
        # - ?paged=2

        base = self.base_url.rstrip("/")

        # Try path-based pagination first
        if "/page/" in current_url:
            return re.sub(r"/page/\d+/?", f"/page/{page}/", current_url)

        # Try query parameter pagination
        if "?" in base:
            return f"{base}&page={page}"
        else:
            return f"{base}?page={page}"

    def _extract_external_id(self, url: str) -> str:
        """
        Extract unique ID from HSSIB investigation URL.

        Args:
            url: Full investigation URL

        Returns:
            External ID string
        """
        # URL patterns:
        # /patient-safety-investigations/investigation-name/
        # /patient-safety-investigations/i2021-123/

        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # Get last path segment
        segments = path.split("/")
        if segments:
            # Use last non-empty segment
            for segment in reversed(segments):
                if segment:
                    return segment

        # Fallback to full path hash
        return path.replace("/", "-")

    def _parse_uk_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse UK-formatted date string.

        Args:
            date_text: Date string (e.g., "15 January 2026", "15/01/2026", "2026-01-15T10:00:00")

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
            "%d/%m/%Y",           # 15/01/2026
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


# Register scraper with factory
ScraperFactory.register("uk_hssib", HSSIBScraper)
