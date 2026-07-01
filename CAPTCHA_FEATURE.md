# CAPTCHA Solving Feature - Implementation Summary

## Overview
Added automated reCAPTCHA solving to BackVora's contacts grabber form submission system. The system can now detect, solve, and submit forms protected by reCAPTCHA v2, v3, and hCaptcha.

## Components Implemented

### 1. Backend: CAPTCHA Solver Service (`backend/services/captcha_solver.py`)
- **Dual-provider support**: 2Captcha (cheaper, tried first) + CapSolver (fallback)
- **API keys configured**:
  - 2Captcha: `82462e4753821ae508af375d9f335e5f`
  - CapSolver: `CAP-CF7B5C7037F09AB42593E80D3FABB4B932EECDC1BD87EE253FBB45F201ABBF3F`
- **Supported CAPTCHA types**: reCAPTCHA v2, v3, hCaptcha
- **Flow**: Submit to API → Poll for result (60s timeout) → Return token
- **Smart fallback**: 2Captcha fails → Auto-retry with CapSolver

### 2. Backend: Browser-based Form Submitter (`backend/services/browser_scraper.py`)
- **Selenium + Chrome**: Headless browser automation
- **Auto-detection**: Extracts site key from page if not provided
- **CAPTCHA injection**: Injects solved token into all `g-recaptcha-response` elements
- **Smart submission**: Detects success/failure indicators in response
- **Chrome flags**: `--headless=new --no-sandbox --disable-gpu` for stability
- **Anti-detection**: Removes webdriver fingerprints

### 3. Database Schema
- **New column**: `contact_forms.captcha_site_key` (TEXT)
- **Migration applied**: ALTER TABLE executed successfully
- **Model updated**: `backend/models.py` ContactForm class includes new field

### 4. Backend: Form Detection Updates (`backend/services/scraper.py`)
- **Enhanced detection**: Extracts CAPTCHA site keys during form scraping
- **Pattern matching**: Finds `data-sitekey` attributes and `grecaptcha` script calls
- **Parent checking**: Also searches parent containers for CAPTCHA elements
- **Automatic storage**: Site keys saved to database when forms detected

### 5. Backend: API Endpoint Updates (`backend/routers/contacts.py`)
- **Smart routing**: Forms with `has_captcha=True` use browser submission
- **Force browser mode**: Optional `?force_browser=true` query param
- **Two paths**:
  - CAPTCHA forms → BrowserFormSubmitter (with solving)
  - Regular forms → HTTP submission (existing flow)
- **Response enriched**: Returns `captcha_solved`, `used_browser` flags
- **Bulk operations**: Updated to save site keys during bulk contact grabbing

### 6. Frontend: CAPTCHA Solving UI (`frontend-react/src/pages/DomainDetailPage.tsx`)
- **Button changes**: "Open in Browser" → "Solve & Submit" for CAPTCHA forms
- **Live status display**: Shows solving progress:
  - "Detecting CAPTCHA..."
  - "Solving CAPTCHA..." (15-60s)
  - "Submitting form..."
  - "Done!"
- **Visual feedback**: Spinner with status text during solving
- **Unified UX**: Both CAPTCHA and regular forms use same submit button style

## Dependencies Installed
```bash
pip install selenium webdriver-manager
```
- **selenium**: Browser automation
- **webdriver-manager**: Auto-manages ChromeDriver versions

## How It Works

### Form Detection Flow
1. User clicks "Grab Contacts" on a domain
2. System fetches contact pages and detects forms
3. For each form, checks for CAPTCHA indicators:
   - `g-recaptcha`, `grecaptcha`, `recaptcha` in HTML
   - `h-captcha`, `hcaptcha` for hCaptcha
4. Extracts site key from `data-sitekey` or script tags
5. Saves form with `has_captcha=True` and site key to database

### Form Submission Flow (with CAPTCHA)
1. User clicks "Solve & Submit" button
2. Frontend shows "Detecting CAPTCHA..." status
3. Backend launches headless Chrome and navigates to form URL
4. Extracts site key from page (if not already stored)
5. Sends site key to CaptchaSolver:
   - Try 2Captcha API (cheaper, ~$0.001/solve)
   - If fails, fallback to CapSolver
   - Polls every 3-5 seconds for solution
6. Receives solved token (typically 15-60 seconds)
7. Injects token into page via JavaScript
8. Fills form fields with template data
9. Clicks submit button
10. Checks for success indicators in response
11. Returns result to frontend
12. Frontend shows "Done!" and updates form status

### Form Submission Flow (without CAPTCHA)
1. Traditional HTTP POST/GET request
2. No browser automation needed
3. Instant submission (< 1 second)

## Configuration

### Timeouts
- **CAPTCHA solving**: 60 seconds max
- **Page load**: 30 seconds max
- **Total operation**: ~90 seconds for CAPTCHA forms

### Error Handling
- CAPTCHA solving failures are reported, not crashed
- Browser errors caught and returned as `{success: false, error: "..."}`
- Original HTTP submission still works for non-CAPTCHA forms
- Frontend shows error toasts for failed submissions

## Testing

### Verification Steps
1. ✅ All imports successful
2. ✅ Database migration applied
3. ✅ Frontend built successfully
4. ✅ Backend service restarted
5. ✅ No runtime errors in logs

### Test a CAPTCHA Form
1. Add a domain with a CAPTCHA-protected contact form
2. Click "Grab Contacts" to detect the form
3. Verify CAPTCHA badge appears: `⚠️ CAPTCHA (recaptcha v2)`
4. Click "Solve & Submit" button
5. Watch status progress through solving steps
6. Verify form submission completes successfully

## Files Changed
- ✅ `backend/services/captcha_solver.py` (new)
- ✅ `backend/services/browser_scraper.py` (new)
- ✅ `backend/services/scraper.py` (updated: extract site keys)
- ✅ `backend/routers/contacts.py` (updated: browser submission routing)
- ✅ `backend/models.py` (updated: add captcha_site_key column)
- ✅ `data/linkbuilder.db` (updated: schema migration)
- ✅ `frontend-react/src/pages/DomainDetailPage.tsx` (updated: UI for CAPTCHA solving)
- ✅ `frontend-react/dist/` (rebuilt)

## Cost Estimate
- **2Captcha**: ~$0.001 per reCAPTCHA solve (~1000 solves per $1)
- **CapSolver**: ~$0.002 per reCAPTCHA solve (~500 solves per $1)
- **Average**: $0.001-0.002 per form submission with CAPTCHA

## Maintenance
- API keys stored in code (consider moving to environment variables for production)
- Chrome must be installed at `/usr/bin/google-chrome`
- ChromeDriver auto-managed by webdriver-manager (updates automatically)

## Future Improvements
- [ ] Move API keys to environment variables or config file
- [ ] Add retry logic for failed browser submissions
- [ ] Support proxy rotation for CAPTCHA solving
- [ ] Add screenshot capture on failure for debugging
- [ ] Track CAPTCHA solve success rate in analytics
- [ ] Support for Cloudflare Turnstile CAPTCHA

## Deployment Status
🟢 **LIVE** - Service running on http://127.0.0.1:8001

**Last updated**: 2026-02-20 12:08:23 EET
