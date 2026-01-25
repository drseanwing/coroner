# NSW Coroner Scraper - Implementation Checklist

## Completed ✓

### Core Implementation
- [x] Created `scrapers/au_nsw_coroner.py` with NSWCoronerScraper class
- [x] Extends BaseScraper abstract class
- [x] Implements `scrape()` method with pagination and error handling
- [x] Implements `parse_listing_page()` for search results
- [x] Implements `parse_finding_page()` for detail pages
- [x] Registered with ScraperFactory as "au_nsw"
- [x] Added import to `scrapers/__init__.py`
- [x] Source already configured in `config/sources.yaml`

### Features
- [x] Healthcare keyword filtering (hospital, medical, health, clinical, patient, ambulance)
- [x] Australian date parsing (dd/mm/yyyy priority)
- [x] PDF download and text extraction
- [x] External ID generation from URLs
- [x] Rate limiting (2.0 second default)
- [x] Pagination handling with next page detection
- [x] Error handling with logging
- [x] Metadata tracking (scraper version, timestamps)
- [x] Category auto-extraction from content
- [x] Court location extraction

### Data Extraction
- [x] Title
- [x] Source URL
- [x] External ID
- [x] Date of finding
- [x] Date of death
- [x] Deceased name
- [x] Coroner name
- [x] Content text (HTML and plain)
- [x] PDF URL
- [x] PDF content extraction
- [x] Categories
- [x] Metadata (summary, court_location, pdf_extracted, etc.)

### Helper Methods
- [x] `_build_search_url()` for pagination
- [x] `_extract_external_id()` from URL
- [x] `_parse_au_date()` for Australian date formats
- [x] `_is_healthcare_related()` for keyword filtering
- [x] `_extract_categories()` from content text

### CSS Selectors
- [x] Listing page selectors (list_container, title, date, summary, link, pagination)
- [x] Detail page selectors (content, pdf_link, deceased_name, date_of_death, date_of_finding, coroner_name, court_location)
- [x] Selectors are configurable via config dict

### Documentation
- [x] Module docstring
- [x] Class docstring with site structure
- [x] Method docstrings
- [x] Implementation guide (NSW_SCRAPER_IMPLEMENTATION.md)
- [x] This checklist document

### Testing Support
- [x] Test script created (`test_nsw_scraper.py`)
- [x] Tests factory registration
- [x] Tests instantiation
- [x] Tests external ID extraction
- [x] Tests date parsing
- [x] Tests healthcare filtering

## Pending Validation ⚠️

### Before Activation
- [ ] Visit NSW Coroners Court website to validate HTML structure
- [ ] Confirm CSS selectors match actual page structure
- [ ] Test with real website data (small sample first)
- [ ] Verify PDF links are correctly extracted
- [ ] Verify pagination URLs are correct format
- [ ] Check if JavaScript rendering is required
- [ ] Validate date format patterns on actual findings
- [ ] Confirm healthcare keyword coverage is adequate

### Testing
- [ ] Run test_nsw_scraper.py to verify basic functionality
- [ ] Create integration test with mock HTML responses
- [ ] Test error handling with invalid URLs
- [ ] Test rate limiting behavior
- [ ] Test pagination across multiple pages
- [ ] Test PDF extraction with real PDFs
- [ ] Verify deduplication works correctly

### Configuration
- [ ] Verify schedule timing (8 PM UTC = 6 AM AEST) is appropriate
- [ ] Confirm request_delay of 2.0 seconds is acceptable
- [ ] Validate max_pages setting (currently 10)
- [ ] Review healthcare keywords for completeness
- [ ] Test with custom selector overrides if needed

### Integration
- [ ] Seed NSW source to database via `scripts/seed_sources.py`
- [ ] Set `is_active: true` in sources.yaml when ready
- [ ] Configure scheduler to run NSW scraper
- [ ] Monitor first scrape run in logs
- [ ] Verify findings are saved to database
- [ ] Check analysis pipeline processes NSW findings
- [ ] Confirm blog posts can be generated from NSW findings

## Known Assumptions

1. **HTML Structure:** Selectors assume standard NSW government website patterns
   - May need adjustment based on actual site structure
   - Multiple selector fallbacks provided (e.g., "h3 a, h4 a")

2. **Pagination:** Assumes URL parameter-based pagination
   - May use different mechanism on actual site
   - Next page link detection via CSS selector

3. **PDF Format:** Assumes standard PDF format compatible with pdfplumber/pypdf
   - Some PDFs may require special handling
   - Extraction failures are logged but don't block findings

4. **No JavaScript Rendering:** Assumes content is in HTML source
   - If site uses heavy JavaScript, may need `use_browser=True`
   - Check with small test first

5. **Healthcare Keywords:** Initial keyword list may need expansion
   - Based on common healthcare terminology
   - Can be customized via config

## Site Analysis Needed

Before activation, analyze these aspects of the NSW website:

1. **Listing Page:**
   - URL structure for search/findings page
   - Pagination mechanism (URL params, links, buttons)
   - Search result item container selector
   - Title/link location within items
   - Date format and location
   - Summary/snippet availability

2. **Detail Page:**
   - URL structure for individual findings
   - Content container selector
   - PDF link location and format
   - Metadata field locations
   - Date formats used
   - Coroner name format

3. **Technical:**
   - Does site use JavaScript rendering?
   - Are there CAPTCHAs or bot detection?
   - What's the rate limit tolerance?
   - Are there any robots.txt restrictions?

## Deployment Steps

When ready to activate:

1. **Pre-deployment:**
   ```bash
   # Test scraper instantiation
   python test_nsw_scraper.py

   # Run database migrations if needed
   alembic upgrade head

   # Seed NSW source to database
   python -m scripts.seed_sources
   ```

2. **Activation:**
   ```yaml
   # In config/sources.yaml
   - code: au_nsw
     is_active: true  # Change from false to true
   ```

3. **Manual Test:**
   ```python
   # Run one-off scrape to test
   from scrapers import ScraperFactory

   async def test_nsw():
       scraper = ScraperFactory.create("au_nsw", base_url="...", config={})
       async with scraper:
           result = await scraper.scrape()
           print(f"Found {len(result.findings)} findings")
   ```

4. **Monitor:**
   - Check logs for errors
   - Verify findings in database
   - Review first few scraped findings manually
   - Adjust selectors if needed

## Success Criteria

The scraper is ready for production when:
- [x] Code implementation complete
- [ ] CSS selectors validated against real site
- [ ] Test scrape completes without errors
- [ ] Findings contain all expected fields
- [ ] Healthcare filtering works correctly
- [ ] PDF extraction succeeds for sample findings
- [ ] No excessive errors in logs
- [ ] Rate limiting is respected
- [ ] Deduplication prevents duplicates on re-scrape

## Reference

- **Base URL:** https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html
- **Schedule:** Daily at 8 PM UTC (6 AM AEST)
- **Factory Code:** au_nsw
- **Source Config:** config/sources.yaml (lines 94-110)
- **Scraper Class:** scrapers/au_nsw_coroner.py
- **Base Class:** scrapers/base.py
- **Similar Implementation:** scrapers/uk_pfd.py
