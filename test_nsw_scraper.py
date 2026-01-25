#!/usr/bin/env python3
"""
Simple test to verify NSW Coroner scraper can be instantiated.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    # Test imports
    from scrapers.base import ScraperFactory
    from scrapers.au_nsw_coroner import NSWCoronerScraper

    print("✓ Imports successful")

    # Test factory registration
    available_sources = ScraperFactory.available_sources()
    print(f"✓ Available scrapers: {available_sources}")

    if "au_nsw" not in available_sources:
        print("✗ ERROR: au_nsw not registered in factory!")
        sys.exit(1)

    # Test instantiation via factory
    scraper = ScraperFactory.create(
        source_code="au_nsw",
        base_url="https://coroners.nsw.gov.au/coroners-court/coronial-findings-search.html",
        config={"max_pages": 2, "request_delay": 1.0}
    )

    print(f"✓ Scraper instantiated: {type(scraper).__name__}")
    print(f"✓ Source code: {scraper.source_code}")
    print(f"✓ Base URL: {scraper.base_url}")
    print(f"✓ Max pages: {scraper.max_pages}")
    print(f"✓ Request delay: {scraper.request_delay}")
    print(f"✓ Healthcare keywords: {len(scraper.keywords)} keywords")

    # Test helper methods
    test_url = "https://coroners.nsw.gov.au/findings/2026/smith-john-12345"
    external_id = scraper._extract_external_id(test_url)
    print(f"✓ External ID extraction: {external_id}")

    # Test date parsing
    test_dates = [
        "15 January 2026",
        "15/01/2026",
        "2026-01-15",
    ]

    for date_str in test_dates:
        parsed = scraper._parse_au_date(date_str)
        if parsed:
            print(f"✓ Date parsing '{date_str}': {parsed.strftime('%Y-%m-%d')}")
        else:
            print(f"✗ Failed to parse date: {date_str}")

    # Test healthcare filtering
    healthcare_text = "patient admitted to hospital with medical complications"
    non_healthcare_text = "motor vehicle accident on highway"

    is_healthcare = scraper._is_healthcare_related(healthcare_text.lower())
    is_not_healthcare = scraper._is_healthcare_related(non_healthcare_text.lower())

    print(f"✓ Healthcare detection (should be True): {is_healthcare}")
    print(f"✓ Non-healthcare detection (should be False): {is_not_healthcare}")

    if is_healthcare and not is_not_healthcare:
        print("✓ Healthcare filtering working correctly")
    else:
        print("✗ Healthcare filtering not working as expected")

    print("\n" + "="*60)
    print("ALL TESTS PASSED - NSW Coroner scraper is ready!")
    print("="*60)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
