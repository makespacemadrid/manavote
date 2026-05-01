# Ideas for Improving This Codebase

This document captures concrete, incremental improvements identified during a detailed review.

## 1) Reliability / Startup

1. **Move app wiring out of `main_routes.py`**
   - Route module currently owns app creation, configuration, DB setup, limiter/CSRF wiring, and route definitions.
   - Split into:
     - `app/factory.py` for app initialization and extension wiring.
     - `app/web/routes/*.py` for blueprints only.
   - Benefit: cleaner imports, fewer side effects, easier testing.

2. **Avoid broad `except Exception` in startup paths**
   - Several startup operations swallow all exceptions and log warnings.
   - Prefer narrower exception classes and fail-fast for critical services.
   - Add startup health summary so misconfiguration is visible.

3. **Add explicit startup mode policy**
   - Document and enforce behavior matrix for `development`, `test`, `production`:
     - DB bootstrap behavior
     - scheduler behavior
     - debug mode
     - secret requirements

## 2) Security

4. **Replace static fallback bootstrap password with one-time random secret (non-prod only)**
   - Current non-production fallback is a fixed known string.
   - Better: generate random one-time secret at first boot, log once, require immediate change.

5. **Add audit logging for API calls**
   - Log endpoint, caller key fingerprint (not raw key), status, and latency.
   - Useful for abuse detection and incident analysis.

6. **Introduce API key rotation support**
   - Allow multiple valid keys temporarily (active + next), then revoke old key.
   - Simplifies safe credential rotation.

7. **Harden file upload validation**
   - `imghdr` is deprecated; migrate to Pillow or python-magic MIME validation.
   - Enforce max dimensions and content-type/extension agreement.

## 3) Data / Domain

8. **Add repository/service boundaries for API routes**
   - Some API endpoints still use direct SQL in route handlers.
   - Move DB logic into repositories/services for consistency and testability.

9. **Normalize statuses and transitions**
   - Centralize proposal lifecycle transitions in one state machine utility.
   - Validate illegal transitions early.

10. **Create DB indexes for common query paths**
    - Add indexes for proposal status/date filters and votes lookups.
    - Measure via `EXPLAIN QUERY PLAN` and benchmark before/after.

## 4) API Quality

11. **Add OpenAPI spec + schema validation**
    - Define endpoints and JSON schemas (`pydantic`/`marshmallow` or hand-rolled checks).
    - Auto-generate docs and request/response examples.

12. **Standardize error response format**
    - Return consistent shape, e.g. `{ "error": { "code": "...", "message": "..." } }`.
    - Helps clients implement stable error handling.

13. **Add list/search endpoint for proposals**
    - `GET /api/proposals?status=active&page=1&page_size=20`.
    - Useful for admin tooling and integrations.

## 5) Internationalization (i18n)

14. **Add i18n completeness checks**
    - Test that all keys used by templates exist in both `en` and `es`.
    - Fail CI on missing keys.

15. **Clean duplicated translation entries**
    - Translation file has repeated keys and mixed casing patterns.
    - Normalize keys and enforce a style guide.

## 6) Testing

16. **Add dedicated integration test DB fixture**
    - Current `APP_DB_PATH` session override is good; extend with transactional fixtures for isolation speed.

17. **Add production-mode configuration tests**
    - Assert startup failures for missing `SECRET_KEY` and missing bootstrap password when `FLASK_ENV=production`.

18. **Add API contract tests**
    - Verify status codes, payload schema, and edge cases for all API endpoints.

19. **Add regression tests for import-time side effects**
    - Ensure importing modules does not mutate DB or schedule jobs unexpectedly.

## 7) Observability / Operations

20. **Structured logging**
    - JSON logs with request id/user id where available.

21. **Metrics endpoint / instrumentation**
    - Request latency, DB timings, error rates, proposal throughput.

22. **Backup validation job**
    - Periodically verify backups are readable and recent.

## 8) Developer Experience

23. **Pre-commit checks**
    - `ruff`/`black`/`isort` + simple static checks for translation keys.

24. **Architecture notes**
    - Add short ADRs for key decisions:
      - bootstrap strategy
      - API auth model
      - budget/committed calculation semantics

25. **Document environment variable matrix**
    - One table showing defaults and behavior by environment (dev/test/prod).

---

## Suggested priority order

1. Security/compatibility quick wins:
   - Replace `imghdr`
   - API key rotation support
   - production-mode config tests
2. Structural cleanup:
   - app factory / blueprint split
   - service/repository extraction for API routes
3. API maturity:
   - OpenAPI + standardized errors + list/search endpoint
4. Observability and ops:
   - structured logs + metrics + backup verification
