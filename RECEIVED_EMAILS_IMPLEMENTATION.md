# ReceivedEmail Implementation Summary

## ✅ Completed Tasks

### 1. Added `ReceivedEmail` Model
**File:** `backend/models.py`

Added the new `ReceivedEmail` model with all requested fields:
- `id`, `domain_id`, `contact_id` (foreign keys)
- `from_addr`, `subject`, `body_text`
- `received_at` (parsed from email Date header)
- `imap_uid` (for deduplication)
- `parsed_data` (JSON, stores full Claude parse result)
- `processing_status` (processed, skipped, skipped_but_verified, error)
- `processing_notes` (audit trail)

### 2. Created Database Table
**Status:** ✅ Table created successfully

The `received_emails` table now exists in the database with all 14 columns (including TimestampMixin fields).

### 3. Updated Reply Parser
**File:** `backend/services/reply_parser.py`

#### Changes to `scan_replies()`:
- **Stores EVERY matched email** before processing check
- Creates `ReceivedEmail` record immediately after domain match
- Parses email date from header for `received_at` field
- Checks for duplicate emails by `imap_uid` before processing
- **Even for skipped emails (domain_already_processed):**
  - Fetches email body
  - Looks for published URLs matching the publisher domain
  - Runs verification against `sent` orders
  - Updates `processing_status` to "skipped_but_verified" or "skipped"
  - Sends Slack alerts for verified/failed verifications
- Passes `received_email` to `process_reply()` for full processing

#### Changes to `process_reply()`:
- Accepts optional `received_email` parameter
- Updates `received_email.body_text` (limited to 10,000 chars)
- Updates `received_email.subject` after fetching email
- Stores `parsed_data` after Claude parsing
- Links `received_email.contact_id` to created/updated contact
- Sets `processing_status` to "processed" or "error"

### 4. Added API Endpoint
**File:** `backend/routers/inbox.py`

New endpoint: `GET /inbox/received`
- Query params: `domain_id` (optional), `limit` (default 50)
- Returns received emails ordered by created_at DESC
- Can filter by specific domain

### 5. Validation Tests
All tests passed:
- ✅ Table creation verified
- ✅ Model CRUD operations working
- ✅ Imports successful (no syntax errors)
- ✅ API endpoint registered

## 🔧 Next Steps (Required)

### Restart the Service
You need to restart the BackVora service to load the updated code:

```bash
sudo systemctl restart backvora
```

Verify it's running:
```bash
sudo systemctl status backvora
```

### Manual Test
After restart, trigger a manual scan to test the new functionality:

```bash
curl -X POST http://localhost:8000/inbox/scan-replies
```

Or through the API dashboard:
```
http://localhost:8000/docs#/inbox/scan_replies_endpoint_inbox_scan_replies_post
```

## 📊 What This Fixes

### Before:
- ❌ Emails were processed but never stored
- ❌ Follow-up emails (with published URLs) were silently dropped if domain already had contact+prices+payment
- ❌ No audit trail of what was received
- ❌ No way to review what Claude extracted

### After:
- ✅ Complete email archive in `received_emails` table
- ✅ Follow-up emails with published URLs are checked even if domain is "complete"
- ✅ Auto-verification runs on skipped emails
- ✅ Full audit trail with processing status and notes
- ✅ Claude parse results stored for review
- ✅ Can query received emails via API
- ✅ Deduplication by `imap_uid` prevents reprocessing

## 🎯 Key Features

### Auto-Verification for Skipped Emails
When a domain already has contact+prices+payment, the scanner:
1. Still fetches the email body
2. Looks for URLs matching the publisher domain
3. Checks if there are any `sent` orders
4. Runs `verify_live_url()` on the first matching URL
5. Sends Slack alerts on success/failure
6. Updates `processing_status` to "skipped_but_verified"

This ensures "Here's your published URL" emails aren't ignored!

### Complete Audit Trail
Every email is now stored with:
- Original email data (from, subject, body, date)
- Processing status (processed, skipped, error)
- Processing notes (why it was skipped, error details)
- Claude's full parse result
- Link to domain and contact

### Deduplication
Uses `imap_uid` to prevent processing the same email twice.

## 📝 Database Schema

```sql
CREATE TABLE received_emails (
    id VARCHAR(36) PRIMARY KEY,
    domain_id VARCHAR(36),
    contact_id VARCHAR(36),
    from_addr VARCHAR(255) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    body_text TEXT,
    received_at DATETIME,
    imap_uid VARCHAR(100),
    parsed_data JSON,
    processing_status VARCHAR(50) DEFAULT 'processed',
    processing_notes TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    deleted_at DATETIME,
    FOREIGN KEY(domain_id) REFERENCES domains(id),
    FOREIGN KEY(contact_id) REFERENCES contacts(id)
);
```

## 🔍 Testing the Implementation

### Check received emails for a domain:
```bash
curl "http://localhost:8000/inbox/received?domain_id=<domain_id>&limit=10"
```

### Check all recent received emails:
```bash
curl "http://localhost:8000/inbox/received?limit=50"
```

### Verify table contents:
```bash
cd /home/slither/clawd/projects/linkbuilder
source venv/bin/activate
python3 -c "
from backend.database import SessionLocal
from backend.models import ReceivedEmail

db = SessionLocal()
count = db.query(ReceivedEmail).count()
print(f'Total received emails: {count}')

# Show recent ones
recent = db.query(ReceivedEmail).order_by(ReceivedEmail.created_at.desc()).limit(5).all()
for email in recent:
    print(f'  - {email.from_addr} -> {email.subject[:50]} [{email.processing_status}]')
db.close()
"
```

## 📚 Files Modified

1. `backend/models.py` - Added `ReceivedEmail` model
2. `backend/services/reply_parser.py` - Updated `scan_replies()` and `process_reply()`
3. `backend/routers/inbox.py` - Added `/inbox/received` endpoint

## ⚠️ Important Notes

- Body text is limited to 10,000 characters to prevent database bloat
- Email date is parsed from the Date header (may be None if parsing fails)
- `imap_uid` is used for deduplication (prevents reprocessing same email)
- Skipped emails still create records with `processing_status="skipped"`
- Auto-verification only runs on first matching `sent` order per email
- All changes maintain backward compatibility with existing functionality

---

**Implementation Date:** 2026-03-02  
**Status:** ✅ Complete, awaiting service restart
