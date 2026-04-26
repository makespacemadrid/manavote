# Security Audit Report

Date: 2026-04-26
Scope: Flask web app source code and configuration in this repository.

## Executive Summary

This audit found several high-impact issues that should be addressed before production deployment:

1. **CSRF protection is effectively disabled** even though forms include a `csrf_token` field.
2. **Session secret key rotates on every process start**, invalidating all sessions and preventing safe key management.
3. **A default administrator password is hard-coded** and created automatically if no admin exists.

Additional medium/low risk hardening opportunities are listed below.

## Findings

### 1) CSRF protection not enforced (High)

- `WTF_CSRF_ENABLED` exists in config and defaults to `true`, but no CSRF middleware is initialized.
- A global template helper returns an empty token (`""`) for all forms.

**Evidence**
- `app/config.py`: `WTF_CSRF_ENABLED` configuration is present.
- `app/web/routes/main_routes.py`: `csrf_helper()` returns `dict(csrf_token=lambda: "")`.
- Templates include hidden `csrf_token` inputs, which currently carry empty values.

**Risk**
- Authenticated users can be forced by third-party pages to submit state-changing requests (vote changes, proposal updates, admin actions).

**Recommendation**
- Initialize `flask_wtf.csrf.CSRFProtect(app)`.
- Remove the empty token helper and use framework-generated token values.
- Ensure tests either include valid tokens or set CSRF off only in explicit test config.

---

### 2) Session secret key generated randomly at startup (High)

**Evidence**
- `app/web/routes/main_routes.py`: `app.secret_key = secrets.token_hex(32)`.

**Risk**
- Sessions become invalid after every restart/deploy.
- Key rotation is uncontrolled and non-auditable.
- Multi-instance deployments cannot share session validation unless all instances happen to share startup state.

**Recommendation**
- Load `SECRET_KEY` from environment or secret manager.
- Fail fast in production if secret key is missing.

---

### 3) Hard-coded default admin password (High)

**Evidence**
- `README.md` publishes default credentials (`admin` / `carpediem42`).
- `app/web/routes/main_routes.py`: first-run DB init inserts admin user with `generate_password_hash("carpediem42")` when no admin exists.

**Risk**
- Predictable credentials are widely known.
- Misconfigured deployments are vulnerable to immediate compromise.

**Recommendation**
- Require bootstrap admin password via environment variable at initialization.
- Refuse startup if no secure bootstrap value is set (or generate one-time random password and print to secure startup logs only).

---

### 4) Cookie security defaults are non-production-safe (Medium)

**Evidence**
- `app/config.py`: `SESSION_COOKIE_SECURE` is controlled by `FLASK_SECURE_COOKIES` and defaults to `false`.

**Risk**
- Session cookies can be sent over plaintext HTTP if deployment is misconfigured.

**Recommendation**
- Default secure cookies to `true` for production profiles.
- Add deployment docs for reverse proxy + HTTPS enforcement.

---

### 5) Broad exception swallowing may hide security failures (Low/Medium)

**Evidence**
- `app/__init__.py`: broad `except Exception: pass` around scheduler startup and backup checks.

**Risk**
- Important failures are silently ignored, reducing observability and delaying incident response.

**Recommendation**
- Log exceptions with stack traces.
- Narrow exception handling to expected failure modes.

## Suggested Remediation Order

1. Fix CSRF enforcement.
2. Externalize and stabilize `SECRET_KEY`.
3. Remove hard-coded admin bootstrap password.
4. Tighten secure cookie defaults and deployment guidance.
5. Replace silent exception handling with structured logging.

## Notes

This report is a code-level audit and does not include dependency CVE scanning, dynamic penetration testing, infrastructure review, or cloud/network configuration assessment.
