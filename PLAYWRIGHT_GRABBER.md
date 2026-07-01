# Playwright-Based Contact Grabber

## Overview

The BackVora Contacts Grabber now supports **Tier 2 fallback** using Playwright for browser-based scraping. This enables grabbing contacts from JavaScript-rendered content and detecting forms hidden in modals/popups.

## Architecture

### Two-Tier Approach

1. **Tier 1 - Static HTML Scraping** (default, fast)
   - Uses `httpx` to fetch pages
   - Parses with BeautifulSoup
   - Extracts emails, social links, and visible forms
   - No browser overhead

2. **Tier 2 - Playwright Browser Scraping** (fallback or forced)
   - Launches headless Chromium
   - Renders JavaScript
   - Clicks contact-like links to trigger modals/popups
   - Extracts forms from modals (fancybox, AJAX-loaded, etc.)
   - Detects Cloudflare challenges gracefully

### Auto-Fallback Logic

The system automatically falls back to browser mode when:
- **Static scraping finds 0 emails AND 0 forms**

This ensures we don't waste resources on browser automation when static scraping works.

## Files Modified

### Backend

1. **`backend/services/browser_grabber.py`** (NEW)
   - `PlaywrightGrabber` class
   - Headless Chromium automation
   - Modal detection and clicking
   - Returns data in same format as `ContactsGrabber`

2. **`backend/services/scraper.py`**
   - Added `use_browser` parameter to `ContactsGrabber.grab_all()`
   - Auto-fallback logic when static scraping finds nothing
   - Merges results from both approaches (deduplicates emails)
   - Tracks which method was used via `"method"` field

3. **`backend/routers/contacts.py`**
   - Added `use_browser` query parameter to `/contacts/grab/{domain_id}`
   - Returns `"method": "static" | "browser"` in response
   - Reports `_browser_error` if browser fails

### Frontend

4. **`frontend-react/src/api.ts`**
   - Updated `grabContacts()` to accept `useBrowser` parameter

5. **`frontend-react/src/pages/DomainDetailPage.tsx`**
   - Added "Deep Grab" button (forces browser mode)
   - Regular "Grab Contacts" button uses static + auto-fallback
   - Shows which method was used (badge: 🌐 Browser mode / 📄 Static mode)
   - Displays browser errors if any

### Config

6. **`requirements.txt`**
   - Added `playwright>=1.40.0`

## Usage

### Via Frontend

1. **Standard Grab** (click "Grab Contacts"):
   - Tries static scraping first
   - Auto-falls back to browser if nothing found

2. **Deep Grab** (click "Deep Grab"):
   - Forces browser mode immediately
   - Slower but finds more (modals, JS-rendered content)

### Via API

```bash
# Standard grab (auto-fallback)
POST /api/v1/contacts/grab/{domain_id}

# Force browser mode
POST /api/v1/contacts/grab/{domain_id}?use_browser=true
```

### Response Example

```json
{
  "success": true,
  "domain": "example.com",
  "method": "browser",
  "emails": [
    {
      "email": "contact@example.com",
      "source_url": "https://example.com/contact",
      "source_type": "contact_page"
    }
  ],
  "socials": {
    "twitter": ["https://twitter.com/example"],
    "linkedin": [],
    "telegram": []
  },
  "forms": [
    {
      "form_url": "https://example.com/contact",
      "form_action": "https://example.com/submit",
      "form_method": "POST",
      "fields": [...],
      "has_captcha": false
    }
  ],
  "contacts_added": 0,
  "forms_detected": 1,
  "_browser_error": null
}
```

## Modal Detection

The Playwright grabber actively **clicks elements** that look like contact links:
- Text matching: "contact", "feedback", "advertise", etc.
- Classes like `js-feedback_footer`, `data-fancybox`, `data-modal`
- After clicking, waits 500ms and extracts any new forms that appeared

### Real-World Example

**exeporn.net** has:
```html
<a class="js-feedback_footer" data-href="/contact/" data-fancybox="ajax">Contact</a>
```

The Playwright grabber:
1. Clicks this link
2. Waits for the fancybox modal to load
3. Extracts the AJAX-loaded form
4. Presses ESC to close the modal
5. Continues to next element

## Performance

- **Static mode**: ~2-5 seconds per domain
- **Browser mode**: ~15-30 seconds per domain (timeout: 30s)
- **Chromium path**: `/home/slither/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome`

## Limitations

1. **Cloudflare challenges**: Detected and reported, but not solved (yet)
2. **CAPTCHAs**: Forms with CAPTCHA are detected but submission requires separate solver
3. **Timeout**: 30s max per domain in browser mode
4. **Resource usage**: Browser instances are expensive (closed properly via context manager)

## Testing

Run the test script:
```bash
cd /home/slither/clawd/projects/linkbuilder
source venv/bin/activate
python test_playwright_grabber.py
```

## Future Enhancements

- [ ] Cloudflare solver integration
- [ ] Proxy rotation for browser mode
- [ ] Screenshot capture on errors
- [ ] Parallel browser instances (with concurrency limits)
- [ ] Custom user agents per domain type
