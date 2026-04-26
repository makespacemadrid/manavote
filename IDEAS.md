# Potential Improvements

## Security
- Enforce real CSRF protection (`CSRFProtect`) and remove the placeholder empty `csrf_token` helper.
- Move `SECRET_KEY` to environment/secret manager and fail fast when missing in production.
- Replace hard-coded default admin bootstrap password with one-time setup flow.
- Add secure-by-default production profile (`SESSION_COOKIE_SECURE=true`, stricter headers).
- Add structured security logging and avoid broad `except Exception: pass` in startup paths.

## Reliability & Architecture
- Split `app/web/routes/main_routes.py` into smaller route modules (auth, proposals, admin, API).
- Introduce an app factory pattern that avoids side effects at import time.
- Replace startup global DB initialization with explicit CLI migration/init commands.
- Add stronger typing (`mypy`/type hints) for service and repository layers.

## Testing
- Add integration tests for REST API endpoints (`/api/register`, `/api/proposals`, edits).
- Add tests for permission boundaries (creator vs admin edit/delete paths).
- Add regression tests for proposal lifecycle transitions (`active` → `approved`/`over_budget` → auto-approve).
- Add backup/scheduler behavior tests with time-freezing.
- Add coverage threshold enforcement in CI.

## Product & UX
- Add explicit timezone controls for all date rendering and exports.
- Improve About page governance copy with maintainable markdown content source.
- Add richer filtering/search on dashboard and calendar activity table.
- Add accessibility pass (labels, contrast, keyboard navigation, ARIA checks).

## DevEx / Operations
- Add CI pipeline with lint + tests + security checks (`bandit`, `pip-audit`).
- Add multi-stage Docker build and non-root runtime user.
- Add healthcheck endpoint and compose healthcheck configuration.
- Add backup restore workflow docs and script.
- Add release/versioning notes and changelog process.
