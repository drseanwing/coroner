"""
Patient Safety Monitor - Base Scraper

Abstract base class for web scrapers with common functionality.
Provides HTTP client management, rate limiting, error handling, and PDF extraction.

All source-specific scrapers inherit from BaseScraper and implement:
    - scrape(): Main entry point
    - parse_listing_page(): Extract findings from listing pages
    - parse_finding_page(): Extract details from individual pages

Usage:
    from scrapers.base import BaseScraper, ScrapedFinding
    
    class MySourceScraper(BaseScraper):
        async def scrape(self) -> ScrapeResult:
            # Implementation
            pass
"""

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Type

import httpx
from playwright.async_api import async_playwright, Browser, Page, Playwright


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ScrapedFinding:
    """
    Data extracted from a source for a single finding.
    
    This is the intermediate format between scraping and database storage.
    Contains all fields that might be extracted, with optionals for
    fields that may not be available from all sources.
    """
    
    # Required fields
    external_id: str
    title: str
    source_url: str
    
    # Optional fields from scraping
    deceased_name: Optional[str] = None
    date_of_death: Optional[datetime] = None
    date_of_finding: Optional[datetime] = None
    coroner_name: Optional[str] = None
    pdf_url: Optional[str] = None
    content_text: Optional[str] = None
    content_html: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """
    Result of a scraping operation.
    
    Contains all scraped findings plus statistics and error information.
    """
    
    source_code: str
    started_at: datetime
    completed_at: datetime
    
    # Results
    findings: list[ScrapedFinding] = field(default_factory=list)
    
    # Statistics
    pages_scraped: int = 0
    new_findings: int = 0
    duplicate_findings: int = 0
    failed_pages: int = 0
    
    # Errors and warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate scrape duration."""
        return (self.completed_at - self.started_at).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.pages_scraped + self.failed_pages
        if total == 0:
            return 0.0
        return self.pages_scraped / total


# =============================================================================
# Base Scraper
# =============================================================================

class BaseScraper(ABC):
    """
    Abstract base class for web scrapers.
    
    Provides:
        - HTTP client with rate limiting and retries
        - Browser automation via Playwright (optional)
        - PDF download and text extraction
        - Common utility methods
    
    Subclasses must implement:
        - scrape(): Main scraping logic
        - parse_listing_page(): Extract findings from listing
        - parse_finding_page(): Extract details from individual pages
    """
    
    def __init__(
        self,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ):
        """
        Initialize the scraper.
        
        Args:
            source_code: Unique identifier for this source
            base_url: Root URL for scraping
            config: Source-specific configuration
        """
        self.source_code = source_code
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        
        # Logger for this scraper
        self.logger = logging.getLogger(f"scrapers.{source_code}")
        
        # HTTP client configuration
        self._http_client: Optional[httpx.AsyncClient] = None
        self._default_headers = {
            "User-Agent": self.config.get(
                "user_agent",
                "PatientSafetyMonitor/1.0 (+https://github.com/patient-safety-monitor)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        
        # Playwright browser (lazy initialization)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        
        # Rate limiting
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = self.config.get("request_delay", 2.0)
    
    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "BaseScraper":
        """Enter async context, initialize resources."""
        await self._init_http_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context, cleanup resources."""
        await self._cleanup()
    
    async def _init_http_client(self) -> None:
        """Initialize HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers=self._default_headers,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=30.0,
                    write=10.0,
                    pool=5.0,
                ),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10),
            )
            self.logger.debug("HTTP client initialized")
    
    async def _init_browser(self) -> None:
        """Initialize Playwright browser (lazy)."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self.logger.debug("Playwright browser initialized")
    
    async def _cleanup(self) -> None:
        """Cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            self.logger.debug("HTTP client closed")
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            self.logger.debug("Playwright browser closed")
    
    # -------------------------------------------------------------------------
    # Abstract Methods
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """
        Main scraping entry point.
        
        Subclasses implement this to:
        1. Fetch listing pages
        2. Extract findings from listings
        3. Fetch detail pages for each finding
        4. Return complete results
        
        Returns:
            ScrapeResult with all findings and statistics
        """
        pass
    
    @abstractmethod
    async def parse_listing_page(
        self,
        page_content: str,
        page_url: str,
    ) -> tuple[list[ScrapedFinding], Optional[str]]:
        """
        Parse a listing page to extract findings.
        
        Args:
            page_content: HTML content of the page
            page_url: URL of the page (for resolving relative links)
            
        Returns:
            Tuple of (findings list, next page URL or None)
        """
        pass
    
    @abstractmethod
    async def parse_finding_page(
        self,
        page_content: str,
        finding: ScrapedFinding,
    ) -> ScrapedFinding:
        """
        Parse an individual finding page for full details.
        
        Args:
            page_content: HTML content of the page
            finding: Partial finding from listing
            
        Returns:
            Complete finding with all extracted details
        """
        pass
    
    # -------------------------------------------------------------------------
    # HTTP Methods
    # -------------------------------------------------------------------------
    
    async def fetch_page(
        self,
        url: str,
        use_browser: bool = False,
        wait_for_selector: Optional[str] = None,
    ) -> str:
        """
        Fetch a page's HTML content.
        
        Uses HTTP client by default, or Playwright for JavaScript-rendered pages.
        
        Args:
            url: URL to fetch
            use_browser: Use Playwright instead of HTTP client
            wait_for_selector: If using browser, wait for this selector
            
        Returns:
            HTML content of the page
        """
        # Rate limiting
        await self._rate_limit()
        
        if use_browser:
            return await self._fetch_with_browser(url, wait_for_selector)
        else:
            return await self._fetch_with_http(url)
    
    async def _fetch_with_http(self, url: str) -> str:
        """Fetch page using HTTP client."""
        if self._http_client is None:
            await self._init_http_client()
        
        self.logger.debug(f"Fetching (HTTP): {url}")
        
        for attempt in range(3):
            try:
                response = await self._http_client.get(url)
                response.raise_for_status()
                return response.text
                
            except httpx.HTTPStatusError as e:
                self.logger.warning(
                    f"HTTP error on attempt {attempt + 1}: {e.response.status_code}"
                )
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
                
            except httpx.RequestError as e:
                self.logger.warning(f"Request error on attempt {attempt + 1}: {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    
    async def _fetch_with_browser(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
    ) -> str:
        """Fetch page using Playwright browser."""
        if self._browser is None:
            await self._init_browser()
        
        self.logger.debug(f"Fetching (browser): {url}")
        
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle")
            
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=10000)
            
            content = await page.content()
            return content
            
        finally:
            await page.close()
    
    async def download_pdf(
        self,
        url: str,
        save_path: Optional[Path] = None,
    ) -> tuple[bytes, Optional[Path]]:
        """
        Download a PDF file.
        
        Args:
            url: PDF URL
            save_path: Optional path to save the PDF
            
        Returns:
            Tuple of (PDF bytes, saved path or None)
        """
        await self._rate_limit()
        
        if self._http_client is None:
            await self._init_http_client()
        
        self.logger.debug(f"Downloading PDF: {url}")
        
        response = await self._http_client.get(url)
        response.raise_for_status()
        
        pdf_bytes = response.content
        
        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(pdf_bytes)
            self.logger.debug(f"Saved PDF to: {save_path}")
            return pdf_bytes, save_path
        
        return pdf_bytes, None
    
    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < self._min_request_interval:
                wait_time = self._min_request_interval - elapsed
                self.logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        self._last_request_time = datetime.utcnow()
    
    # -------------------------------------------------------------------------
    # PDF Extraction
    # -------------------------------------------------------------------------
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """
        Extract text content from a PDF.
        
        Uses pdfplumber for extraction with fallback to pypdf.
        
        Args:
            pdf_bytes: PDF file content
            
        Returns:
            Extracted text content
        """
        import io
        
        try:
            # Try pdfplumber first (better extraction)
            import pdfplumber
            
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n\n".join(text_parts)
                
        except ImportError:
            self.logger.warning("pdfplumber not available, falling back to pypdf")
            
        try:
            # Fallback to pypdf
            from pypdf import PdfReader
            
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n\n".join(text_parts)
            
        except ImportError:
            self.logger.error("No PDF extraction library available")
            raise RuntimeError("PDF extraction requires pdfplumber or pypdf")
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    def generate_external_id(self, *parts: str) -> str:
        """
        Generate a consistent external ID from parts.
        
        Args:
            *parts: Strings to combine into an ID
            
        Returns:
            Deterministic external ID
        """
        combined = "_".join(str(p) for p in parts if p)
        # Create a short hash for very long IDs
        if len(combined) > 80:
            hash_suffix = hashlib.md5(combined.encode()).hexdigest()[:8]
            combined = f"{combined[:70]}_{hash_suffix}"
        return combined
    
    def clean_text(self, text: Optional[str]) -> Optional[str]:
        """
        Clean extracted text content.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text or None
        """
        if not text:
            return None
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        
        # Remove control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        
        return text.strip() or None


# =============================================================================
# Scraper Factory
# =============================================================================

class ScraperFactory:
    """
    Factory for creating scraper instances.
    
    Maintains a registry of scraper classes by source code.
    
    Usage:
        # Register a scraper
        ScraperFactory.register("uk_pfd", UKPFDScraper)
        
        # Create instance
        scraper = ScraperFactory.create("uk_pfd", "https://...", config)
    """
    
    _registry: dict[str, Type[BaseScraper]] = {}
    
    @classmethod
    def register(cls, source_code: str, scraper_class: Type[BaseScraper]) -> None:
        """
        Register a scraper class.
        
        Args:
            source_code: Source identifier
            scraper_class: Scraper class to register
        """
        cls._registry[source_code] = scraper_class
    
    @classmethod
    def create(
        cls,
        source_code: str,
        base_url: str,
        config: Optional[dict[str, Any]] = None,
    ) -> BaseScraper:
        """
        Create a scraper instance.
        
        Args:
            source_code: Source identifier
            base_url: Root URL for scraping
            config: Source-specific configuration
            
        Returns:
            Configured scraper instance
            
        Raises:
            ValueError: If source_code is not registered
        """
        if source_code not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown source code: {source_code}. "
                f"Available: {available}"
            )
        
        scraper_class = cls._registry[source_code]
        return scraper_class(source_code, base_url, config)
    
    @classmethod
    def available_sources(cls) -> list[str]:
        """Get list of registered source codes."""
        return list(cls._registry.keys())


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "BaseScraper",
    "ScrapedFinding",
    "ScrapeResult",
    "ScraperFactory",
]
