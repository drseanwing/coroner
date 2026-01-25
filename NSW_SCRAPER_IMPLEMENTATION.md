# NSW Coroner Scraper Implementation

## Overview

Successfully implemented the NSW Coroner's Court scraper at `scrapers/au_nsw_coroner.py` following the established pattern from the UK PFD scraper.

## Implementation Details

### File Created
- **Path:** `scrapers/au_nsw_coroner.py`
- **Class:** `NSWCoronerScraper`
- **Base Class:** `BaseScraper`
- **Factory Code:** `au_nsw`

### Key Features

#### 1. Healthcare Filtering
Implements keyword-based filtering for healthcare-related findings:
- hospital
- medical
- health
- clinical
- patient
- ambulance
- doctor
- nurse
- treatment
- surgery
- emergency department
- intensive care
- mental health

#### 2. Date Parsing
Australian date format support including:
- `15 January 2026` (day month year)
- `15/01/2026` (Australian dd/mm/yyyy format)
- `2026-01-15` (ISO format)
- Handles ordinal suffixes (1st, 2nd, 3rd, etc.)

#### 3. PDF Extraction
- Automatic PDF download from finding pages
- Text extraction using pdfplumber/pypdf
- PDF content appended to finding content_text
- PDF extraction status tracked in metadata

#### 4. Data Extraction

**From Listing Pages:**
- Title and link
- Date of finding
- Summary/snippet for filtering
- External ID generation

**From Detail Pages:**
- Full content (HTML and text)
- PDF URL and content
- Deceased name
- Date of death
- Date of finding
- Coroner name
- Court location
- Categories (auto-extracted from content)

#### 5. Category Detection
Automatic categorization based on content keywords:
- Hospital Death
- Medical Treatment
- Emergency Services
- Mental Health
- Clinical Care
- Patient Safety

### CSS Selectors

The scraper includes configurable CSS selectors for:

**Listing Pages:**
- `list_container`: `div.search-result`
- `title`: `h3 a, h4 a`
- `date`: `span.date, .result-date`
- `summary`: `div.summary, p.summary`
- `link`: `a.result-link, h3 a, h4 a`
- `pagination`: `a.next, .pagination a[rel='next']`

**Detail Pages:**
- `content`: `div.content, .page-content, main article`
- `pdf_link`: `a[href*='.pdf'], a.pdf-link`
- `deceased_name`: `.deceased-name, .field-deceased`
- `date_of_death`: `.date-of-death, .field-date-of-death`
- `date_of_finding`: `.date-of-finding, .field-date-finding`
- `coroner_name`: `.coroner-name, .field-coroner`
- `court_location`: `.court-location, .field-location`

### Configuration

The scraper is pre-configured in `config/sources.yaml`:

```yaml
- code: au_nsw
  name: "NSW Coroners Court"
  country: AU
  region: NSW
  base_url: "https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html"
  scraper_class: NSWCoronerScraper
  schedule: "0 20 * * *"  # Daily at 8 PM UTC (6 AM AEST)
  is_active: false
  priority: P1
  implementation_phase: 6
  config:
    max_pages: 10
    request_delay: 2.0
```

### Error Handling

- HTTP request retries with exponential backoff (inherited from BaseScraper)
- Rate limiting at 2 seconds between requests
- Failed detail page fetches still preserve partial data
- PDF extraction failures are logged but don't block the finding
- Comprehensive error logging with structured context

### Integration

#### Factory Registration
```python
ScraperFactory.register("au_nsw", NSWCoronerScraper)
```

#### Module Import
Added to `scrapers/__init__.py`:
```python
from scrapers.au_nsw_coroner import NSWCoronerScraper
```

## Usage

### Via Factory
```python
from scrapers import ScraperFactory

scraper = ScraperFactory.create(
    source_code="au_nsw",
    base_url="https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html",
    config={"max_pages": 5, "request_delay": 2.0}
)

async with scraper:
    result = await scraper.scrape()
```

### Direct Instantiation
```python
from scrapers.au_nsw_coroner import NSWCoronerScraper

scraper = NSWCoronerScraper(
    source_code="au_nsw",
    base_url="https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html",
    config={
        "max_pages": 10,
        "request_delay": 2.0,
        "healthcare_keywords": ["hospital", "medical", "clinical"],
    }
)

async with scraper:
    result = await scraper.scrape()
    print(f"Scraped {len(result.findings)} findings")
```

## Testing

A test script has been created at `test_nsw_scraper.py` to verify:
- Module imports
- Factory registration
- Scraper instantiation
- External ID extraction
- Date parsing (multiple formats)
- Healthcare keyword filtering
- Helper method functionality

To run the test (requires Python):
```bash
python test_nsw_scraper.py
```

## Patterns Followed from UK PFD Scraper

1. **Structure:** Same class structure with `scrape()`, `parse_listing_page()`, and `parse_finding_page()` methods
2. **Rate Limiting:** Configurable request delay with sleep between requests
3. **Pagination:** Support for next page URL detection and iteration
4. **Error Handling:** Try-catch blocks with logging and graceful degradation
5. **Metadata Tracking:** Scraper version and timestamp in metadata
6. **Factory Pattern:** Registration with ScraperFactory for centralized management
7. **Configuration:** YAML-based source configuration with sensible defaults

## Australian-Specific Adaptations

1. **Date Formats:** Day-first date formats (dd/mm/yyyy) prioritized
2. **Keywords vs Categories:** Uses keyword filtering instead of predefined categories
3. **Content Categories:** Automatically extracts categories from content text
4. **Court Location:** Captures NSW-specific court location metadata
5. **Timezone:** Schedule set for 8 PM UTC = 6 AM AEST (Australian Eastern Standard Time)

## Next Steps

1. **Activate Source:** Set `is_active: true` in `sources.yaml` when ready to go live
2. **Selector Validation:** Test against actual NSW website to validate CSS selectors
3. **Site Analysis:** Visit NSW Coroners Court website to confirm HTML structure
4. **Testing:** Run integration tests with real website data
5. **Monitoring:** Monitor scrape logs for errors after activation
6. **Fine-tuning:** Adjust selectors and filters based on initial results

## Files Modified

1. **Created:** `scrapers/au_nsw_coroner.py` - Main scraper implementation
2. **Modified:** `scrapers/__init__.py` - Added NSWCoronerScraper import
3. **Created:** `test_nsw_scraper.py` - Test script for validation

## Notes

- Selectors are educated guesses based on common NSW government website patterns
- May need adjustment after testing with actual website
- PDF extraction is automatic but can be disabled via config
- Healthcare filtering can be customized via `healthcare_keywords` config parameter
- Rate limiting is conservative (2 seconds) to be respectful to government infrastructure
