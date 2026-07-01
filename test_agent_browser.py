#!/usr/bin/env python3
"""
Quick test of agent-browser integration.
Run: python3 test_agent_browser.py
"""

import asyncio
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.agent_browser import AgentBrowser, AgentBrowserError


async def test_basic_navigation():
    """Test basic open + snapshot + screenshot."""
    print("🧪 Testing agent-browser integration...")
    
    try:
        async with AgentBrowser(session="test-integration") as browser:
            print("✓ AgentBrowser initialized")
            
            # Navigate to example.com
            print("→ Opening example.com...")
            await browser.open("https://example.com", wait_load=True)
            print("✓ Page loaded")
            
            # Take snapshot
            print("→ Taking snapshot...")
            snapshot = await browser.snapshot(interactive=True, json_output=False)
            print(f"✓ Snapshot captured ({len(snapshot.get('text', ''))} chars)")
            
            # Get page text
            print("→ Getting page text...")
            text = await browser.get_text()
            print(f"✓ Page text: {text[:100]}...")
            
            # Take screenshot
            screenshot_path = "/tmp/agent_browser_test.png"
            print(f"→ Taking screenshot to {screenshot_path}...")
            await browser.screenshot(screenshot_path)
            print(f"✓ Screenshot saved")
            
            # Get URL
            url = await browser.get_url()
            print(f"✓ Current URL: {url}")
            
            print("\n🎉 All tests passed!")
            return True
    
    except AgentBrowserError as e:
        print(f"\n❌ Agent-browser error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_javascript_eval():
    """Test JavaScript evaluation."""
    print("\n🧪 Testing JavaScript evaluation...")
    
    try:
        async with AgentBrowser(session="test-js") as browser:
            await browser.open("https://example.com", wait_load=True)
            
            # Simple eval
            title = await browser.eval_js("document.title")
            print(f"✓ Page title via JS: {title}")
            
            # Complex eval with JSON
            link_count = await browser.eval_js("""
                JSON.stringify({
                    links: document.querySelectorAll('a').length,
                    paragraphs: document.querySelectorAll('p').length
                })
            """)
            print(f"✓ Page stats: {link_count}")
            
            print("🎉 JS eval tests passed!")
            return True
    
    except Exception as e:
        print(f"❌ JS eval test failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Agent-Browser Integration Test")
    print("=" * 60)
    
    success = asyncio.run(test_basic_navigation())
    
    if success:
        asyncio.run(test_javascript_eval())
    
    print("\n" + "=" * 60)
    sys.exit(0 if success else 1)
