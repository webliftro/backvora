# Bug Fix: Link Verifier HTML Parser

**Date:** 2026-03-03  
**Status:** ✅ FIXED  
**File:** `backend/services/link_monitor.py`

## Problem

The link verifier in BackVora failed to extract anchor text and URLs from tubeorigin.com's page, reporting:
- `found_anchor=''` (empty)
- `found_url='/'` (wrong URL)

When the actual link was correctly placed: `[Cam Hours](https://camhours.com)`

This caused a false `WRONG_ANCHORS` alert and an embarrassing auto-email to the publisher.

## Root Cause

The URL matching logic had a critical bug:

```python
if expected_url in href or href in expected_url:
```

When the first link on the page had `href="/"`, after stripping trailing slashes it became an empty string `""`. Since **empty string is in every string in Python**, this matched first and returned the wrong link.

## Solution

### 1. Added URL Normalization Functions

```python
def _normalize_url(url: str) -> str:
    """
    Normalize URL for comparison.
    - Lowercase
    - Strip trailing slash
    - Remove protocol differences (treat http/https same)
    - Remove www prefix
    """
```

```python
def _urls_match(url1: str, url2: str) -> bool:
    """
    Check if two URLs match, handling protocol/www/trailing slash variations.
    Prevents empty string matches.
    """
```

### 2. Improved Link Matching Logic

**Before:**
- Used simple string containment (`in` operator)
- Didn't filter out empty/invalid hrefs
- Case-sensitive URL comparisons

**After:**
- Explicitly skips empty or fragment-only links (`#`, `/`, `''`)
- Uses robust URL normalization before comparison
- Handles http vs https, www vs non-www, trailing slashes

### 3. Better Anchor Text Extraction

**Before:**
```python
actual_anchor = matched_tag.get_text(strip=True)
```

**After:**
```python
actual_anchor = matched_tag.get_text(separator=" ", strip=True)
# Normalize whitespace for comparison
actual_norm = " ".join(actual_anchor.split()).lower()
expected_norm = " ".join(expected_anchor.split()).lower()
```

Now handles:
- Nested elements inside `<a>` tags (e.g., `<a><span>Text</span></a>`)
- Multiple whitespace characters
- Case-insensitive comparison

## Testing

### Test Results

✅ **TubeOrigin** (original failing case)
- URL: `https://www.tubeorigin.com/@tubeorigin/post/bYg_c1pd1HMeKliO`
- Expected: "Cam Hours" → `https://camhours.com`
- Result: **VERIFIED** ✓

✅ **CelebFapper** (regression test)
- URL: `https://celebfapper.com/posts/view/75/...`
- Expected: "camhours.com girls" → `https://camhours.com/girls`
- Result: **VERIFIED** ✓

### Run Tests

```bash
cd /home/slither/clawd/projects/linkbuilder
source venv/bin/activate
python test_link_verifier_fix.py
```

## Edge Cases Handled

- ✅ Empty hrefs (`""`, `/`, `#`)
- ✅ Trailing slashes (`https://example.com` vs `https://example.com/`)
- ✅ Protocol variations (`http://` vs `https://`)
- ✅ www prefix (`www.example.com` vs `example.com`)
- ✅ Nested anchor text elements
- ✅ Multiple whitespace in anchor text
- ✅ Case-insensitive comparisons

## What Was NOT Changed

- No changes to HTTP status checks
- No changes to dofollow detection
- No changes to image verification
- No changes to content completeness checks
- All existing functionality preserved

## Deployment

Service restarted successfully:
```bash
systemctl --user restart backvora
```

Status: **Active (running)** ✅

## Prevention

To avoid similar bugs in the future:
1. Always check for empty strings before using `in` operator for substring matching
2. Normalize URLs before comparison (protocol, www, trailing slashes)
3. Add comprehensive test cases for edge cases
4. Use explicit filtering (`if href not in ('#', '/', '')`) before processing

## Files Changed

1. `/home/slither/clawd/projects/linkbuilder/backend/services/link_monitor.py`
   - Added `_normalize_url()` function
   - Added `_urls_match()` function
   - Updated link matching logic in `verify_live_url()`
   - Improved anchor text extraction and comparison

2. `/home/slither/clawd/projects/linkbuilder/test_link_verifier_fix.py`
   - New comprehensive test suite

---

**Result:** No more false WRONG_ANCHORS alerts! 🎉
