#!/usr/bin/env python3
"""
Quick test of the Playwright grabber functionality.
"""

import asyncio
import sys
sys.path.insert(0, '/home/slither/code/backvora')

from backend.services.browser_grabber import PlaywrightGrabber
from backend.services.scraper import ContactsGrabber


async def test_static_vs_browser():
    """Test both static and browser modes on a domain."""
    test_domain = "example.com"  # Simple test domain
    
    print("=" * 60)
    print(f"Testing grabber on: {test_domain}")
    print("=" * 60)
    
    # Test static mode
    print("\n1. Testing STATIC mode...")
    grabber = ContactsGrabber()
    static_result = await grabber.grab_all(test_domain, use_browser=False)
    
    print(f"   Method: {static_result.get('method')}")
    print(f"   Emails found: {len(static_result['emails'])}")
    print(f"   Forms found: {len(static_result['forms'])}")
    print(f"   Socials: Twitter={len(static_result['socials']['twitter'])}, "
          f"LinkedIn={len(static_result['socials']['linkedin'])}, "
          f"Telegram={len(static_result['socials']['telegram'])}")
    
    # Test browser mode (forced)
    print("\n2. Testing BROWSER mode (forced)...")
    browser_result = await grabber.grab_all(test_domain, use_browser=True)
    
    print(f"   Method: {browser_result.get('method')}")
    print(f"   Emails found: {len(browser_result['emails'])}")
    print(f"   Forms found: {len(browser_result['forms'])}")
    print(f"   Socials: Twitter={len(browser_result['socials']['twitter'])}, "
          f"LinkedIn={len(browser_result['socials']['linkedin'])}, "
          f"Telegram={len(browser_result['socials']['telegram'])}")
    
    if "_browser_error" in browser_result:
        print(f"   ⚠️  Browser error: {browser_result['_browser_error']}")
    
    # Test auto-fallback (on a domain with no static results)
    print("\n3. Testing AUTO-FALLBACK (use_browser=False on empty domain)...")
    empty_domain = "example.org"
    fallback_result = await grabber.grab_all(empty_domain, use_browser=False)
    
    print(f"   Method: {fallback_result.get('method')}")
    print(f"   Emails found: {len(fallback_result['emails'])}")
    print(f"   Forms found: {len(fallback_result['forms'])}")
    
    print("\n" + "=" * 60)
    print("✅ Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_static_vs_browser())
