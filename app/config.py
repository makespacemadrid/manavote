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
