#!/usr/bin/env python3
"""
Test script for link verifier bug fix.
Tests both tubeorigin.com and celebfapper.com URLs.
"""
import asyncio
from backend.database import SessionLocal
from backend.services.link_monitor import verify_live_url


async def test_order(order_id: str, url: str, name: str):
    """Test a single order verification."""
    print(f"\n{'='*70}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Order ID: {order_id}")
    print('='*70)
    
    db = SessionLocal()
    try:
        result = await verify_live_url(
            order_id,
            url,
            db,
            auto_update_status=False
        )
        
        print(f"\n✓ Status: {result['status']}")
        print(f"✓ Verified: {result['verified']}")
        print(f"✓ HTTP Status: {result['http_status']}")
        
        if result['issues']:
            print(f"\n⚠ Issues found:")
            for issue in result['issues']:
                print(f"  - {issue}")
        
        print(f"\nLink Details:")
        for detail in result.get('link_details', []):
            print(f"  Slot {detail.get('slot')}:")
            print(f"    Expected: \"{detail.get('expected_anchor')}\" -> {detail.get('expected_url')}")
            print(f"    Found: \"{detail.get('found_anchor')}\" -> {detail.get('found_url')}")
            print(f"    Dofollow: {detail.get('is_dofollow')}")
            if detail.get('issues'):
                print(f"    Issues: {detail.get('issues')}")
        
        return result['verified']
    finally:
        db.close()


async def main():
    """Run all tests."""
    print("🔍 Link Verifier Bug Fix Test Suite")
    print("Testing URL normalization and matching improvements")
    
    results = []
    
    # Test 1: TubeOrigin (the original failing case)
    results.append(await test_order(
        '67ce198d-bdc7-4311-b7be-c3c34d31b6bd',
        'https://www.tubeorigin.com/@tubeorigin/post/bYg_c1pd1HMeKliO',
        'TubeOrigin (original failing case)'
    ))
    
    # Test 2: CelebFapper (should still work)
    results.append(await test_order(
        '61dbe85a-ca7b-4ee6-b904-f578a9e75dda',
        'https://celebfapper.com/posts/view/75/Beyond-the-Screen-How-Virtual-Reality-and-AI-Are-Creating-the-Future-of-Intimate-Entertainment',
        'CelebFapper (regression test)'
    ))
    
    # Summary
    print(f"\n{'='*70}")
    print("📊 Test Summary")
    print('='*70)
    print(f"Total tests: {len(results)}")
    print(f"Passed: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("\n✅ All tests PASSED! The verifier is working correctly.")
    else:
        print("\n❌ Some tests FAILED! Please review the output above.")
    
    return all(results)


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
