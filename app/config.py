import os
from datetime import timedelta


class Config:
    SESSION_COOKIE_SECURE = os.getenv("FLASK_SECURE_COOKIES", "true").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = os.getenv("FLASK_CSRF", "true").lower() == "true"
    WTF_CSRF_TIME_LIMIT = None
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
