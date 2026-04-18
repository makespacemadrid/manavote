# Production Audit - Move to Production

## Overview
This document details security findings and remediation recommendations before deploying to production.

---

## Critical Issues

### 1. Hardcoded Admin Credentials
- **Issue**: Default admin `admin`/`carpediem42` created on first run
- **Status**: NEEDS FIX
- **Remediation**: Require admin to change password on first login, disable default credentials

### 2. Password Hashing
- **Issue**: SHA-256 without salt (`werkzeug.security.generate_password_hash` should be used)
- **Status**: NEEDS FIX
- **Remediation**: Migrate to werkzeug password hashing

### 3. Debug Mode
- **Issue**: `debug=True` in production config
- **Status**: NEEDS FIX
- **Remediation**: Set `debug=False` in production

---

## High Priority Issues

### 4. CSRF Protection
- **Issue**: No CSRF tokens on form POSTs
- **Status**: NEEDS FIX
- **Remediation**: Add Flask-WTF CSRF protection

### 5. Rate Limiting
- **Issue**: No rate limiting on login/API
- **Status**: NEEDS FIX (if API enabled)
- **Remediation**: Add rate limiting middleware

### 6. `/check-overbudget` Unauthenticated
- **Issue**: Public endpoint triggers over-budget processing
- **Status**: NEEDS FIX
- **Remediation**: Add @login_required or remove public access

---

## Medium Priority

### 7. Upload Validation
- **Issue**: Only extension checked, not MIME/content
- **Status**: PARTIAL
- **Remediation**: Add file content validation

### 8. Error Handling
- **Issue**: Broad `except:` blocks hide errors
- **Status**: LOW PRIORITY
- **Remediation**: Add specific exception handling

---

## Production Checklist

- [ ] Change default admin password
- [ ] Set `debug=False`
- [ ] Configure environment variables:
  - [ ] `TELEGRAM_BOT_TOKEN`
  - [ ] `TELEGRAM_CHAT_ID`
  - [ ] `ADMIN_API_KEY` (if using API)
- [ ] Enable HTTPS/TLS
- [ ] Set secure session cookie settings
- [ ] Configure logging
- [ ] Set up monitoring/alerting

---

## Current Test Coverage

Tests passing: **78 tests**

```bash
python3 -m unittest discover -s tests -v
```

---

## Feature Readiness

| Feature | Status | Notes |
|---------|--------|-------|
| Authentication | ⚠️ PARTIAL | Needs password migration |
| Voting | ✅ READY | Auto-process works |
| Budget tracking | ✅ READY | Full history |
| Calendar chart | ✅ READY | Cash flow lines/bars |
| Admin panel | ✅ READY | Full CRUD |
| REST API | ✅ READY | With API key |
| i18n | ✅ READY | EN/ES |
| Notifications | ⚠️ PARTIAL | Telegram opt-in |

---

## Recommendations

1. **Immediate**: Change admin password, disable debug
2. **Before public launch**: Add CSRF, fix password hashing
3. **Optional**: Rate limiting, content validation