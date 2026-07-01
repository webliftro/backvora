# Agent-Browser Integration for BackVora

Agent-browser has been integrated into BackVora as an alternative/upgrade to Selenium-based browser automation.

## What Was Added

### 1. `backend/services/agent_browser.py`
Python async wrapper around the agent-browser CLI tool.

**Key Features:**
- Async subprocess execution with proper timeout handling
- Session management (isolated browser states)
- JSON parsing for structured output
- Graceful error handling with fallbacks
- Context manager support (`async with`)

**Usage Example:**
```python
from backend.services.agent_browser import AgentBrowser

async with AgentBrowser(session="my-task") as browser:
    await browser.open("https://example.com")
    snapshot = await browser.snapshot(interactive=True)
    await browser.click("@e1")
    screenshot = await browser.screenshot("/path/to/screenshot.png")
```

### 2. Deep Link Verification (`link_monitor.py`)
New function: `deep_verify_live_url()`

**What It Does:**
- Opens published URL in real browser (headless Chrome)
- Takes full-page screenshot as proof (saved to `data/screenshots/`)
- Verifies links are present in **rendered** page (not just HTML source)
- Checks dofollow status on rendered DOM
- Validates images actually loaded (not broken)
- Detects hidden links (display:none, visibility:hidden)
- Content completeness check (word count comparison)

**API Endpoint:**
```
POST /api/v1/orders/{order_id}/deep-verify
{
  "url": "https://example.com/published-article"
}
```

**Response:**
```json
{
  "verified": true,
  "status": "VERIFIED",
  "screenshot_path": "data/screenshots/example_com_20260304_235300.png",
  "link_details": [
    {
      "slot": 1,
      "expected_url": "https://target.com",
      "expected_anchor": "click here",
      "found": true,
      "found_url": "https://target.com",
      "found_anchor": "click here",
      "is_dofollow": true,
      "issues": []
    }
  ],
  "issues": []
}
```

**Why Use Deep Verification:**
- Catches JavaScript-injected nofollow tags (not visible in raw HTML)
- Detects cloaking (links show different for bots vs browsers)
- Verifies images loaded correctly (not 404s)
- Screenshot proof for disputes
- More accurate than httpx + BeautifulSoup for dynamic sites

### 3. Agent-Browser Form Submitter (`browser_scraper.py`)
New class: `AgentBrowserFormSubmitter`

**Features:**
- Smart field discovery via snapshot (no hardcoded selectors)
- Fuzzy field matching (handles "Your Name", "Full Name", "Name*", etc.)
- CAPTCHA solving integration (2Captcha/CapSolver)
- Automatic submit button detection
- Success/error detection after submission

**Usage:**
```python
from backend.services.browser_scraper import AgentBrowserFormSubmitter

submitter = AgentBrowserFormSubmitter(timeout=45)
result = await submitter.submit_form_with_captcha(
    form_url="https://example.com/contact",
    form_data={
        "name": "John Doe",
        "email": "john@example.com",
        "message": "Hello there"
    },
    fields=[
        {"name": "name", "type": "text"},
        {"name": "email", "type": "email"},
        {"name": "message", "type": "textarea"}
    ],
    captcha_type="recaptcha_v2"
)
```

**When to Use:**
- Complex forms where Selenium struggles
- Forms with dynamic field IDs/names
- Forms requiring JavaScript rendering
- As a fallback when Selenium fails

**Current Implementation:**
- AgentBrowserFormSubmitter exists alongside BrowserFormSubmitter
- To use it in production, update the code that calls BrowserFormSubmitter to try AgentBrowserFormSubmitter first, then fall back to Selenium

### 4. API Endpoint for Deep Verification
`POST /api/v1/orders/{order_id}/deep-verify`

**When to Use:**
- Publisher-submitted URLs (don't trust raw HTML)
- High-value links (want screenshot proof)
- Suspicious verification failures (check if it's cloaking)
- Monthly link audits (combine with regular verify)

## How Agent-Browser Works

Agent-browser is a CLI tool that manages a headless Chromium instance via Playwright. It:
1. Starts a daemon process (reuses same browser for multiple commands)
2. Takes "snapshots" of the accessibility tree with refs (`@e1`, `@e2`...)
3. Lets you interact with elements via refs (click, fill, etc.)
4. Supports JavaScript evaluation in page context
5. Handles sessions (isolated browser states per task)

**Session Management:**
All commands use `--session backvora` for isolation. Sessions auto-save cookies/localStorage.

**Important:**
- Always close sessions when done (`await browser.close()`)
- agent-browser binary at: `/home/slither/.nvm/versions/node/v24.13.0/bin/agent-browser`
- Falls back gracefully if binary not found

## Next Steps

### For Deep Verification:
1. **Test it:** Try deep-verify on a known-good published URL
2. **Compare:** Run both `/verify` and `/deep-verify` on the same URL, compare results
3. **Integration:** Consider auto-triggering deep-verify for high-value domains (DA 50+)
4. **UI:** Add a "Deep Verify" button in the frontend next to regular "Verify"

### For Form Submission:
1. **Test:** Try AgentBrowserFormSubmitter on a real contact form
2. **Compare:** Compare success rate vs Selenium
3. **Fallback Chain:** Update contact form submission to:
   - Try AgentBrowserFormSubmitter first
   - Fall back to BrowserFormSubmitter (Selenium) on failure
   - Report which method succeeded
4. **Monitor:** Track which method works best for which sites

### For Both:
1. **Error Logging:** Log agent-browser errors to see failure patterns
2. **Performance:** Measure execution time (agent-browser may be faster for simple tasks)
3. **Screenshots:** Use screenshots for debugging and customer proof

## Troubleshooting

**"agent-browser not found":**
- Install: `npm install -g agent-browser`
- Or update path in `agent_browser.py` constant `AGENT_BROWSER_PATH`

**Timeouts:**
- Increase timeout in AgentBrowser constructor: `AgentBrowser(timeout=60)`
- Slow sites: Use `wait_load=True` in `open()`

**Snapshots don't show expected elements:**
- Try `snapshot(cursor_interactive=True)` to include divs with onclick
- Check if page requires login/cookies
- Use annotated screenshots: `browser.screenshot("debug.png", annotate=True)`

**Form submission fails:**
- Check snapshot output to see what refs were discovered
- Field matching might need tuning (edit `_match_field()` in `AgentBrowserFormSubmitter`)
- Try Selenium fallback for complex forms

## Files Changed

1. **New:** `backend/services/agent_browser.py` (Python wrapper)
2. **Updated:** `backend/services/link_monitor.py` (added `deep_verify_live_url`)
3. **Updated:** `backend/services/browser_scraper.py` (added `AgentBrowserFormSubmitter`)
4. **Updated:** `backend/routers/orders.py` (added `/deep-verify` endpoint)

## Resources

- agent-browser docs: `/home/slither/.openclaw/skills/agent-browser/SKILL.md`
- agent-browser CLI: `/home/slither/.nvm/versions/node/v24.13.0/bin/agent-browser`
- Screenshots: `data/screenshots/` (gitignored, created on first use)
