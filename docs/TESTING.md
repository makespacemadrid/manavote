# Testing Guide

## Run everything

```bash
pytest -q
```

## Targeted regression packs

```bash
pytest -q tests/test_template_guards.py tests/test_production_config.py tests/test_app_startup.py tests/test_startup_policy.py tests/unit/test_settings_service.py tests/unit/test_vote_repository_contract.py
```

### Coverage summary

- `tests/test_template_guards.py`
  - Admin template uses shared top navigation partial.
  - CSRF hidden input markup is well formed in key templates.
- `tests/test_production_config.py`
  - Startup fails when `FLASK_ENV=production` and `SECRET_KEY` is missing/default.
  - DB bootstrap fails on first startup in production if `ADMIN_BOOTSTRAP_PASSWORD` is missing.
- `tests/test_app_startup.py`
  - App startup sequencing remains deterministic and DB failures are fail-fast.
  - Optional startup jobs (scheduler/auto-backup) remain warning-only and can be skipped in `test` env.
- `tests/test_startup_policy.py`
  - Runtime policy flags are environment-aware (`test` disables optional startup jobs).
- `tests/unit/test_settings_service.py`
  - Enum-like setting reads are normalized with consistent fallback behavior.
- `tests/unit/test_vote_repository_contract.py`
  - Proposal-vote repository invariants (upsert replacement + vote counts) are enforced.


## API-focused checks

```bash
pytest -q tests/test_api_helpers.py tests/test_api_error_envelope.py tests/test_app_functionality.py -k "api or polls"
```

Covers API auth/content-type validation, error envelope consistency, proposal API validation, and poll API flows.

## MCP-focused checks

```bash
pytest -q tests/test_mcp_server.py
```

Covers MCP auth, tool discovery, create-tool happy paths, and key negative-path contracts:
- validation failures (`-32602`)
- conflict class (`-32010`)
- not-found class (`-32004`)
