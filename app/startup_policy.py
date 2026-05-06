"""Startup environment policy checks."""

from __future__ import annotations


def validate_startup_policy(
    app_env: str, secret_key: str | None, secure_cookies_enabled: bool | None = None
) -> None:
    """Validate minimum startup requirements by environment."""
    normalized_env = (app_env or "").strip().lower()
    is_production = normalized_env == "production"

    if is_production and (not secret_key or secret_key == "dev-insecure-secret-change-me"):
        raise RuntimeError(
            "SECRET_KEY must be set to a non-default value when FLASK_ENV=production"
        )
    if is_production and secure_cookies_enabled is False:
        raise RuntimeError(
            "FLASK_SECURE_COOKIES must remain enabled when FLASK_ENV=production"
        )


def get_startup_runtime_policy(app_env: str) -> dict:
    """Return runtime startup behavior flags by environment."""
    normalized_env = (app_env or "").strip().lower()
    if normalized_env == "test":
        return {"run_scheduler": False, "run_auto_backup": False}
    return {"run_scheduler": True, "run_auto_backup": True}
