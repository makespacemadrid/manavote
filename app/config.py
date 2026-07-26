import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")
    _secure_cookie_default = "true" if os.getenv("FLASK_ENV", "").strip().lower() == "production" else "false"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_SECURE_COOKIES", _secure_cookie_default).lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = os.getenv("FLASK_CSRF", "true").lower() == "true"
    WTF_CSRF_TIME_LIMIT = None
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    _rate_limit_default = "false" if os.getenv("FLASK_ENV", "").strip().lower() == "test" else "true"
    RATELIMIT_ENABLED = os.getenv("FLASK_RATE_LIMITS", _rate_limit_default).lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    OIDC_ISSUER = os.getenv("OIDC_ISSUER", "https://identity.mksmad.org/realms/Makespace")
    OIDC_DISCOVERY_URL = os.getenv(
        "OIDC_DISCOVERY_URL",
        f"{OIDC_ISSUER}/.well-known/openid-configuration",
    )
    OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "manavote")
    OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
    OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "")
    OIDC_POST_LOGOUT_REDIRECT_URI = os.getenv("OIDC_POST_LOGOUT_REDIRECT_URI", "")
    OIDC_REQUIRED_GROUP = os.getenv("OIDC_REQUIRED_GROUP", "members-active").strip()
    OIDC_SCOPES = "openid profile email"
    OIDC_ENABLED = bool(OIDC_CLIENT_SECRET)
