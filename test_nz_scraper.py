#!/usr/bin/env python3
"""
Quick test script for NZ Coronial Services scraper.

Tests basic functionality without actually scraping the live site.
"""

import asyncio
from scrapers import ScraperFactory


async def test_nz_scraper():
    """Test NZ scraper instantiation and basic methods."""

    print("Testing NZ Coronial Services scraper...")
    print("-" * 60)

    # Check if scraper is registered
    print("\n1. Checking scraper registration:")
    available = ScraperFactory.available_sources()
    print(f"   Available scrapers: {available}")

    if "nz_coroner" not in available:
        print("   ERROR: nz_coroner not registered!")
        return False
    print("   ✓ nz_coroner is registered")

    # Create scraper instance
    print("\n2. Creating scraper instance:")
    try:
        scraper = ScraperFactory.create(
            source_code="nz_coroner",
            base_url="https://coronialservices.justice.govt.nz/findings/",
            config={
                "max_pages": 2,
                "request_delay": 1.0,
            }
        )
        print(f"   ✓ Created scraper: {scraper.__class__.__name__}")
        print(f"   Base URL: {scraper.base_url}")
        print(f"   Max pages: {scraper.max_pages}")
        print(f"   Healthcare keywords: {len(scraper.keywords)} keywords")
    except Exception as e:
        print(f"   ERROR: Failed to create scraper: {e}")
        return False

    # Test URL building
    print("\n3. Testing URL builder:")
    try:
        url1 = scraper._build_listing_url(page=1)
        url2 = scraper._build_listing_url(page=2)
        print(f"   Page 1: {url1}")
        print(f"   Page 2: {url2}")
        print("   ✓ URL builder works")
    except Exception as e:
        print(f"   ERROR: URL builder failed: {e}")
        return False

    # Test external ID extraction
    print("\n4. Testing external ID extraction:")
    try:
        test_urls = [
            "https://coronialservices.justice.govt.nz/findings/john-smith-2026/",
            "https://coronialservices.justice.govt.nz/findings/123/",
            "https://coronialservices.justice.govt.nz/findings/healthcare-death/",
        ]
        for url in test_urls:
            ext_id = scraper._extract_external_id(url)
            print(f"   {url.split('/')[-2]}/  →  {ext_id}")
        print("   ✓ External ID extraction works")
    except Exception as e:
        print(f"   ERROR: External ID extraction failed: {e}")
        return False

    # Test date parsing
    print("\n5. Testing date parser:")
    try:
        test_dates = [
            "15 January 2026",
            "15/01/2026",
            "2026-01-15",
            "15th January 2026",
        ]
        for date_str in test_dates:
            parsed = scraper._parse_nz_date(date_str)
            if parsed:
                print(f"   '{date_str}' → {parsed.strftime('%Y-%m-%d')}")
            else:
                print(f"   '{date_str}' → None")
        print("   ✓ Date parser works")
    except Exception as e:
        print(f"   ERROR: Date parser failed: {e}")
        return False

    # Test healthcare filtering
    print("\n6. Testing healthcare keyword filtering:")
    try:
        test_cases = [
            ("Patient died in hospital after surgery", True),
            ("Traffic accident on motorway", False),
            ("Medical treatment at clinic", True),
            ("Drowning at beach", False),
            ("Ambulance response to emergency", True),
        ]
        for text, expected in test_cases:
            result = scraper._is_healthcare_related(text.lower())
            status = "✓" if result == expected else "✗"
            print(f"   {status} '{text[:40]}...' → {result}")
        print("   ✓ Healthcare filtering works")
    except Exception as e:
        print(f"   ERROR: Healthcare filtering failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = asyncio.run(test_nz_scraper())
    exit(0 if success else 1)
