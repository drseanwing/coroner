"""
Patient Safety Monitor - Scraper Unit Tests

Comprehensive unit tests for the scraper module.
Tests BaseScraper abstract class and UKPFDScraper implementation.
"""

import asyncio
import hashlib
import io
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch, Mock

import httpx
from bs4 import BeautifulSoup

from scrapers.base import (
    BaseScraper,
    ScrapedFinding,
    ScrapeResult,
    ScraperFactory,
)
from scrapers.uk_pfd import UKPFDScraper


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_uk_pfd_listing_html():
    """Sample HTML for UK PFD listing page."""
    return """
    <html>
        <body>
            <article class="pfd_single">
                <h2><a href="/pfd/report-001/">Test Report 001</a></h2>
                <div class="pfd_meta_date">15 January 2024</div>
                <div class="pfd_meta_categories">
                    <a href="/category/hospital/">Hospital Death (Clinical)</a>
                </div>
                <div class="pfd_meta_coroner">Coroner: Dr. Jane Smith</div>
            </article>
            <article class="pfd_single">
                <h2><a href="/pfd/report-002/">Test Report 002</a></h2>
                <div class="pfd_meta_date">1st February 2024</div>
                <div class="pfd_meta_categories">
                    <a href="/category/road/">Road Traffic</a>
                </div>
                <div class="pfd_meta_coroner">Coroner: Mr. John Doe</div>
            </article>
            <div class="pagination">
                <a class="next" href="/prevention-of-future-death-reports/?paged=2">Next</a>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def sample_uk_pfd_detail_html():
    """Sample HTML for UK PFD detail page."""
    return """
    <html>
        <body>
            <div class="entry-content">
                <h1>Prevention of Future Deaths Report</h1>
                <p>This report concerns the death of John Smith.</p>
                <p>Concerns were raised about hospital procedures.</p>
            </div>
            <div class="pfd_meta_deceased">Deceased: John Smith</div>
            <div class="pfd_meta_dod">Date of death: 10th March 2023</div>
            <div class="pfd_meta_coroner">Coroner: Dr. Jane Smith</div>
            <div class="pfd_meta_addressee">NHS Trust XYZ</div>
            <a href="/uploads/report-001.pdf">Download PDF Report</a>
        </body>
    </html>
    """


@pytest.fixture
def sample_pdf_bytes():
    """Sample PDF bytes for testing."""
    # This is a minimal valid PDF structure
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF content) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
307
%%EOF"""
    return pdf_content


# =============================================================================
# DataClass Tests
# =============================================================================

class TestScrapedFinding:
    """Tests for ScrapedFinding dataclass."""

    def test_create_minimal_finding(self):
        """Test creating finding with required fields only."""
        finding = ScrapedFinding(
            external_id="test-001",
            title="Test Finding",
            source_url="https://example.com/finding",
        )

        assert finding.external_id == "test-001"
        assert finding.title == "Test Finding"
        assert finding.source_url == "https://example.com/finding"
        assert finding.deceased_name is None
        assert finding.categories == []
        assert finding.metadata == {}

    def test_create_full_finding(self):
        """Test creating finding with all fields."""
        finding = ScrapedFinding(
            external_id="test-002",
            title="Complete Finding",
            source_url="https://example.com/finding/002",
            deceased_name="John Smith",
            date_of_death=datetime(2023, 3, 10),
            date_of_finding=datetime(2024, 1, 15),
            coroner_name="Dr. Jane Smith",
            pdf_url="https://example.com/report.pdf",
            content_text="Test content",
            content_html="<p>Test content</p>",
            categories=["Hospital Death (Clinical)"],
            metadata={"scraper_version": "1.0.0"},
        )

        assert finding.deceased_name == "John Smith"
        assert finding.date_of_death == datetime(2023, 3, 10)
        assert len(finding.categories) == 1
        assert finding.metadata["scraper_version"] == "1.0.0"


class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""

    def test_create_scrape_result(self):
        """Test creating scrape result."""
        started = datetime.utcnow()
        completed = started + timedelta(seconds=120)

        result = ScrapeResult(
            source_code="uk_pfd",
            started_at=started,
            completed_at=completed,
            findings=[],
            pages_scraped=5,
            new_findings=10,
            duplicate_findings=2,
            failed_pages=1,
            errors=["Error 1"],
            warnings=["Warning 1"],
        )

        assert result.source_code == "uk_pfd"
        assert result.pages_scraped == 5
        assert len(result.errors) == 1

    def test_duration_seconds_calculation(self):
        """Test duration calculation."""
        started = datetime(2024, 1, 1, 12, 0, 0)
        completed = datetime(2024, 1, 1, 12, 2, 30)

        result = ScrapeResult(
            source_code="test",
            started_at=started,
            completed_at=completed,
        )

        assert result.duration_seconds == 150.0

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        started = datetime.utcnow()
        completed = started + timedelta(seconds=60)

        result = ScrapeResult(
            source_code="test",
            started_at=started,
            completed_at=completed,
            pages_scraped=8,
            failed_pages=2,
        )

        assert result.success_rate == 0.8

    def test_success_rate_zero_pages(self):
        """Test success rate when no pages scraped."""
        started = datetime.utcnow()
        completed = started + timedelta(seconds=1)

        result = ScrapeResult(
            source_code="test",
            started_at=started,
            completed_at=completed,
            pages_scraped=0,
            failed_pages=0,
        )

        assert result.success_rate == 0.0


# =============================================================================
# BaseScraper Tests
# =============================================================================

class ConcreteScraper(BaseScraper):
    """Concrete implementation of BaseScraper for testing."""

    async def scrape(self) -> ScrapeResult:
        started = datetime.utcnow()
        completed = datetime.utcnow()
        return ScrapeResult(
            source_code=self.source_code,
            started_at=started,
            completed_at=completed,
        )

    async def parse_listing_page(self, page_content: str, page_url: str):
        return [], None

    async def parse_finding_page(self, page_content: str, finding: ScrapedFinding):
        return finding


class TestBaseScraper:
    """Tests for BaseScraper abstract class."""

    def test_init_minimal(self):
        """Test initialization with minimal parameters."""
        scraper = ConcreteScraper(
            source_code="test",
            base_url="https://example.com/",
        )

        assert scraper.source_code == "test"
        assert scraper.base_url == "https://example.com"
        assert scraper.config == {}
        assert scraper._min_request_interval == 2.0

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = {
            "user_agent": "CustomBot/1.0",
            "request_delay": 5.0,
            "max_pages": 10,
        }

        scraper = ConcreteScraper(
            source_code="test",
            base_url="https://example.com",
            config=config,
        )

        assert scraper.config == config
        assert scraper._min_request_interval == 5.0
        assert "CustomBot/1.0" in scraper._default_headers["User-Agent"]

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from base_url."""
        scraper = ConcreteScraper(
            source_code="test",
            base_url="https://example.com/path/",
        )

        assert scraper.base_url == "https://example.com/path"

    def test_generate_external_id_simple(self):
        """Test external ID generation from parts."""
        scraper = ConcreteScraper("test", "https://example.com")

        external_id = scraper.generate_external_id("uk_pfd", "2024", "report-001")

        assert external_id == "uk_pfd_2024_report-001"

    def test_generate_external_id_with_none(self):
        """Test external ID generation filters out None values."""
        scraper = ConcreteScraper("test", "https://example.com")

        external_id = scraper.generate_external_id("uk_pfd", None, "report-001")

        assert external_id == "uk_pfd_report-001"

    def test_generate_external_id_long_string(self):
        """Test external ID generation with very long string gets hashed."""
        scraper = ConcreteScraper("test", "https://example.com")

        long_part = "a" * 100
        external_id = scraper.generate_external_id("prefix", long_part)

        assert len(external_id) <= 80
        assert external_id.startswith("prefix_")

    def test_generate_external_id_consistency(self):
        """Test external ID generation is consistent."""
        scraper = ConcreteScraper("test", "https://example.com")

        id1 = scraper.generate_external_id("test", "123", "abc")
        id2 = scraper.generate_external_id("test", "123", "abc")

        assert id1 == id2

    def test_clean_text_normal(self):
        """Test text cleaning with normal input."""
        scraper = ConcreteScraper("test", "https://example.com")

        cleaned = scraper.clean_text("  Hello   World  \n\n  Test  ")

        assert cleaned == "Hello World Test"

    def test_clean_text_with_control_chars(self):
        """Test text cleaning removes control characters."""
        scraper = ConcreteScraper("test", "https://example.com")

        text_with_controls = "Hello\x00World\x08Test"
        cleaned = scraper.clean_text(text_with_controls)

        assert cleaned == "HelloWorldTest"

    def test_clean_text_none_input(self):
        """Test text cleaning with None input."""
        scraper = ConcreteScraper("test", "https://example.com")

        cleaned = scraper.clean_text(None)

        assert cleaned is None

    def test_clean_text_empty_string(self):
        """Test text cleaning with empty string."""
        scraper = ConcreteScraper("test", "https://example.com")

        cleaned = scraper.clean_text("   ")

        assert cleaned is None

    def test_clean_text_whitespace_only(self):
        """Test text cleaning with only whitespace."""
        scraper = ConcreteScraper("test", "https://example.com")

        cleaned = scraper.clean_text("\n\n  \t  \n")

        assert cleaned is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test context manager behavior."""
        scraper = ConcreteScraper("test", "https://example.com")

        async with scraper as s:
            assert s is scraper
            assert s._http_client is not None

        # After exit, client should be closed
        assert scraper._http_client is None

    @pytest.mark.asyncio
    async def test_rate_limit_timing(self):
        """Test rate limiting enforces delay."""
        scraper = ConcreteScraper(
            "test",
            "https://example.com",
            config={"request_delay": 0.1},
        )

        # First call should be immediate
        start = datetime.utcnow()
        await scraper._rate_limit()
        first_duration = (datetime.utcnow() - start).total_seconds()

        # Second call should wait
        start = datetime.utcnow()
        await scraper._rate_limit()
        second_duration = (datetime.utcnow() - start).total_seconds()

        assert first_duration < 0.05  # First call is fast
        assert second_duration >= 0.09  # Second call waits ~0.1s

    @pytest.mark.asyncio
    async def test_rate_limit_respects_previous_request(self):
        """Test rate limiting respects time since last request."""
        scraper = ConcreteScraper(
            "test",
            "https://example.com",
            config={"request_delay": 0.5},
        )

        # Make first request
        await scraper._rate_limit()

        # Wait half the required interval
        await asyncio.sleep(0.25)

        # Second request should wait additional time
        start = datetime.utcnow()
        await scraper._rate_limit()
        duration = (datetime.utcnow() - start).total_seconds()

        # Should wait approximately 0.25s more (to complete the 0.5s interval)
        assert 0.2 <= duration <= 0.35

    def test_extract_text_from_pdf_with_pdfplumber(self, sample_pdf_bytes):
        """Test PDF text extraction using pdfplumber."""
        scraper = ConcreteScraper("test", "https://example.com")

        # Mock pdfplumber
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Test PDF content"

        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf):
            text = scraper.extract_text_from_pdf(sample_pdf_bytes)

        assert text == "Test PDF content"

    def test_extract_text_from_pdf_multiple_pages(self, sample_pdf_bytes):
        """Test PDF text extraction with multiple pages."""
        scraper = ConcreteScraper("test", "https://example.com")

        # Mock pdfplumber with multiple pages
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content"

        mock_pdf = MagicMock()
        mock_pdf.__enter__.return_value = mock_pdf
        mock_pdf.__exit__.return_value = None
        mock_pdf.pages = [mock_page1, mock_page2]

        with patch("pdfplumber.open", return_value=mock_pdf):
            text = scraper.extract_text_from_pdf(sample_pdf_bytes)

        assert text == "Page 1 content\n\nPage 2 content"

    def test_extract_text_from_pdf_fallback_to_pypdf(self, sample_pdf_bytes):
        """Test PDF extraction falls back to pypdf when pdfplumber unavailable."""
        scraper = ConcreteScraper("test", "https://example.com")

        # Mock pypdf
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PyPDF content"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        # Simulate pdfplumber not available
        with patch("pdfplumber.open", side_effect=ImportError):
            with patch("scrapers.base.PdfReader", return_value=mock_reader):
                text = scraper.extract_text_from_pdf(sample_pdf_bytes)

        assert text == "PyPDF content"

    def test_extract_text_from_pdf_no_library_available(self, sample_pdf_bytes):
        """Test PDF extraction raises error when no library available."""
        scraper = ConcreteScraper("test", "https://example.com")

        # Simulate both libraries unavailable
        with patch("pdfplumber.open", side_effect=ImportError):
            with patch.dict("sys.modules", {"pypdf": None}):
                with pytest.raises(RuntimeError, match="PDF extraction requires"):
                    scraper.extract_text_from_pdf(sample_pdf_bytes)


# =============================================================================
# UKPFDScraper Tests
# =============================================================================

class TestUKPFDScraper:
    """Tests for UKPFDScraper implementation."""

    def test_init_with_defaults(self):
        """Test initialization uses default config."""
        scraper = UKPFDScraper(
            source_code="uk_pfd",
            base_url="https://www.judiciary.uk/prevention-of-future-death-reports/",
        )

        assert scraper.source_code == "uk_pfd"
        assert scraper.max_pages == 10
        assert len(scraper.categories) > 0
        assert "Hospital Death (Clinical)" in scraper.categories

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = {
            "max_pages": 5,
            "categories": ["Hospital Death (Clinical)"],
            "request_delay": 3.0,
        }

        scraper = UKPFDScraper(
            source_code="uk_pfd",
            base_url="https://example.com",
            config=config,
        )

        assert scraper.max_pages == 5
        assert len(scraper.categories) == 1
        assert scraper.request_delay == 3.0

    def test_parse_uk_date_with_ordinal(self):
        """Test parsing UK date with ordinal suffix."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        date1 = scraper._parse_uk_date("1st January 2024")
        date2 = scraper._parse_uk_date("2nd February 2024")
        date3 = scraper._parse_uk_date("3rd March 2024")
        date4 = scraper._parse_uk_date("15th April 2024")

        assert date1 == datetime(2024, 1, 1)
        assert date2 == datetime(2024, 2, 2)
        assert date3 == datetime(2024, 3, 3)
        assert date4 == datetime(2024, 4, 15)

    def test_parse_uk_date_various_formats(self):
        """Test parsing various UK date formats."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        date1 = scraper._parse_uk_date("15 January 2024")
        date2 = scraper._parse_uk_date("15 Jan 2024")
        date3 = scraper._parse_uk_date("15/01/2024")
        date4 = scraper._parse_uk_date("15-01-2024")
        date5 = scraper._parse_uk_date("2024-01-15")
        date6 = scraper._parse_uk_date("15.01.2024")

        expected = datetime(2024, 1, 15)
        assert date1 == expected
        assert date2 == expected
        assert date3 == expected
        assert date4 == expected
        assert date5 == expected
        assert date6 == expected

    def test_parse_uk_date_invalid(self):
        """Test parsing invalid date returns None."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        result = scraper._parse_uk_date("Invalid date")

        assert result is None

    def test_parse_uk_date_empty(self):
        """Test parsing empty date returns None."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        result = scraper._parse_uk_date("")

        assert result is None

    def test_extract_external_id_from_url(self):
        """Test extracting external ID from various URL patterns."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        id1 = scraper._extract_external_id("https://example.com/pfd/report-name-123/")
        id2 = scraper._extract_external_id("https://example.com/prevention-of-future-death-reports/report-name/")
        id3 = scraper._extract_external_id("https://example.com/reports/john-smith-2024")

        assert id1 == "report-name-123"
        assert id2 == "report-name"
        assert id3 == "john-smith-2024"

    def test_extract_external_id_no_trailing_slash(self):
        """Test extracting external ID from URL without trailing slash."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        external_id = scraper._extract_external_id("https://example.com/pfd/report-123")

        assert external_id == "report-123"

    def test_is_healthcare_category_matching(self):
        """Test healthcare category detection with matching categories."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        result1 = scraper._is_healthcare_category(["Hospital Death (Clinical)"])
        result2 = scraper._is_healthcare_category(["Medical cause"])
        result3 = scraper._is_healthcare_category(["Road Traffic", "Hospital Death (Other)"])

        assert result1 is True
        assert result2 is True
        assert result3 is True

    def test_is_healthcare_category_non_matching(self):
        """Test healthcare category detection with non-matching categories."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        result = scraper._is_healthcare_category(["Road Traffic", "Industrial"])

        assert result is False

    def test_is_healthcare_category_substring_match(self):
        """Test healthcare category uses substring matching."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com")

        # "hospital" is substring of "Hospital Death (Clinical)"
        result = scraper._is_healthcare_category(["hospital related incident"])

        assert result is True

    def test_is_healthcare_category_no_filter(self):
        """Test healthcare category returns True when no filter configured."""
        scraper = UKPFDScraper(
            "uk_pfd",
            "https://example.com",
            config={"categories": []},
        )

        result = scraper._is_healthcare_category(["Anything"])

        assert result is True

    def test_build_listing_url_page_1(self):
        """Test building listing URL for first page."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        url = scraper._build_listing_url(page=1)

        assert url == "https://example.com/reports"

    def test_build_listing_url_page_2(self):
        """Test building listing URL for page 2."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports")

        url = scraper._build_listing_url(page=2)

        assert url == "https://example.com/reports?paged=2"

    def test_build_listing_url_higher_page(self):
        """Test building listing URL for higher page numbers."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        url = scraper._build_listing_url(page=10)

        assert url == "https://example.com/reports?paged=10"

    @pytest.mark.asyncio
    async def test_parse_listing_page_success(self, sample_uk_pfd_listing_html):
        """Test parsing listing page extracts findings."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        findings, next_url = await scraper.parse_listing_page(
            sample_uk_pfd_listing_html,
            "https://example.com/reports/",
        )

        # Should extract only healthcare finding (Report 001)
        assert len(findings) == 1
        assert findings[0].title == "Test Report 001"
        assert findings[0].external_id == "report-001"
        assert findings[0].source_url == "https://example.com/pfd/report-001/"
        assert findings[0].coroner_name == "Dr. Jane Smith"
        assert "Hospital Death (Clinical)" in findings[0].categories

    @pytest.mark.asyncio
    async def test_parse_listing_page_with_pagination(self, sample_uk_pfd_listing_html):
        """Test parsing listing page extracts next page URL."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        findings, next_url = await scraper.parse_listing_page(
            sample_uk_pfd_listing_html,
            "https://example.com/reports/",
        )

        assert next_url == "https://example.com/prevention-of-future-death-reports/?paged=2"

    @pytest.mark.asyncio
    async def test_parse_listing_page_filters_non_healthcare(self, sample_uk_pfd_listing_html):
        """Test listing page filters out non-healthcare findings."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        findings, _ = await scraper.parse_listing_page(
            sample_uk_pfd_listing_html,
            "https://example.com/reports/",
        )

        # Report 002 has "Road Traffic" category - should be filtered out
        titles = [f.title for f in findings]
        assert "Test Report 002" not in titles

    @pytest.mark.asyncio
    async def test_parse_listing_page_no_healthcare_filter(self):
        """Test listing page without healthcare filter includes all findings."""
        scraper = UKPFDScraper(
            "uk_pfd",
            "https://example.com/reports/",
            config={"categories": []},
        )

        html = """
        <html>
            <body>
                <article class="pfd_single">
                    <h2><a href="/pfd/report-001/">Report 001</a></h2>
                    <div class="pfd_meta_categories">
                        <a href="/category/road/">Road Traffic</a>
                    </div>
                </article>
            </body>
        </html>
        """

        findings, _ = await scraper.parse_listing_page(html, "https://example.com/")

        assert len(findings) == 1
        assert findings[0].title == "Report 001"

    @pytest.mark.asyncio
    async def test_parse_listing_page_empty(self):
        """Test parsing empty listing page."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        html = "<html><body></body></html>"

        findings, next_url = await scraper.parse_listing_page(
            html,
            "https://example.com/reports/",
        )

        assert findings == []
        assert next_url is None

    @pytest.mark.asyncio
    async def test_parse_finding_page_success(self, sample_uk_pfd_detail_html):
        """Test parsing finding detail page."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        finding = ScrapedFinding(
            external_id="report-001",
            title="Test Report 001",
            source_url="https://example.com/pfd/report-001/",
        )

        updated_finding = await scraper.parse_finding_page(
            sample_uk_pfd_detail_html,
            finding,
        )

        assert updated_finding.deceased_name == "John Smith"
        assert updated_finding.date_of_death == datetime(2023, 3, 10)
        assert updated_finding.coroner_name == "Dr. Jane Smith"
        assert updated_finding.pdf_url == "https://example.com/uploads/report-001.pdf"
        assert "hospital procedures" in updated_finding.content_text.lower()
        assert updated_finding.content_html is not None
        assert updated_finding.metadata.get("addressees") == "NHS Trust XYZ"

    @pytest.mark.asyncio
    async def test_parse_finding_page_missing_fields(self):
        """Test parsing finding page with missing optional fields."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        html = """
        <html>
            <body>
                <div class="entry-content">
                    <p>Minimal content</p>
                </div>
            </body>
        </html>
        """

        finding = ScrapedFinding(
            external_id="report-001",
            title="Test Report",
            source_url="https://example.com/report/",
        )

        updated_finding = await scraper.parse_finding_page(html, finding)

        assert updated_finding.deceased_name is None
        assert updated_finding.date_of_death is None
        assert updated_finding.pdf_url is None
        assert updated_finding.content_text == "Minimal content"

    @pytest.mark.asyncio
    async def test_parse_finding_page_preserves_coroner_from_listing(self):
        """Test that coroner name from listing is preserved if not in detail."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        html = """
        <html>
            <body>
                <div class="entry-content">
                    <p>Content without coroner info</p>
                </div>
            </body>
        </html>
        """

        finding = ScrapedFinding(
            external_id="report-001",
            title="Test Report",
            source_url="https://example.com/report/",
            coroner_name="Dr. Original Coroner",
        )

        updated_finding = await scraper.parse_finding_page(html, finding)

        assert updated_finding.coroner_name == "Dr. Original Coroner"

    @pytest.mark.asyncio
    async def test_parse_finding_page_cleans_deceased_name(self):
        """Test that deceased name prefix is removed."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        html = """
        <html>
            <body>
                <div class="pfd_meta_deceased">Deceased: John Smith</div>
            </body>
        </html>
        """

        finding = ScrapedFinding(
            external_id="report-001",
            title="Test",
            source_url="https://example.com/",
        )

        updated_finding = await scraper.parse_finding_page(html, finding)

        assert updated_finding.deceased_name == "John Smith"

    @pytest.mark.asyncio
    async def test_parse_finding_page_cleans_date_of_death(self):
        """Test that date of death prefix is removed."""
        scraper = UKPFDScraper("uk_pfd", "https://example.com/reports/")

        html = """
        <html>
            <body>
                <div class="pfd_meta_dod">Date of death: 15 January 2024</div>
            </body>
        </html>
        """

        finding = ScrapedFinding(
            external_id="report-001",
            title="Test",
            source_url="https://example.com/",
        )

        updated_finding = await scraper.parse_finding_page(html, finding)

        assert updated_finding.date_of_death == datetime(2024, 1, 15)


# =============================================================================
# ScraperFactory Tests
# =============================================================================

class TestScraperFactory:
    """Tests for ScraperFactory."""

    def test_register_scraper(self):
        """Test registering a scraper class."""
        # Clear registry first
        ScraperFactory._registry.clear()

        ScraperFactory.register("test_scraper", ConcreteScraper)

        assert "test_scraper" in ScraperFactory._registry
        assert ScraperFactory._registry["test_scraper"] == ConcreteScraper

    def test_create_scraper(self):
        """Test creating a scraper instance."""
        ScraperFactory._registry.clear()
        ScraperFactory.register("test_scraper", ConcreteScraper)

        scraper = ScraperFactory.create(
            "test_scraper",
            "https://example.com",
            config={"max_pages": 5},
        )

        assert isinstance(scraper, ConcreteScraper)
        assert scraper.source_code == "test_scraper"
        assert scraper.base_url == "https://example.com"
        assert scraper.config["max_pages"] == 5

    def test_create_unknown_scraper(self):
        """Test creating unknown scraper raises error."""
        ScraperFactory._registry.clear()

        with pytest.raises(ValueError, match="Unknown source code"):
            ScraperFactory.create("nonexistent", "https://example.com")

    def test_available_sources(self):
        """Test getting list of available sources."""
        ScraperFactory._registry.clear()
        ScraperFactory.register("scraper1", ConcreteScraper)
        ScraperFactory.register("scraper2", ConcreteScraper)

        available = ScraperFactory.available_sources()

        assert len(available) == 2
        assert "scraper1" in available
        assert "scraper2" in available

    def test_uk_pfd_registered(self):
        """Test that UKPFDScraper is registered in the factory."""
        # This tests the module-level registration
        available = ScraperFactory.available_sources()

        assert "uk_pfd" in available
