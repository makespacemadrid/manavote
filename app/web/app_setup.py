import os
import logging
import hashlib
import secrets
from functools import lru_cache
from flask import Flask

from app.config import Config
from app.extensions import limiter, csrf, oauth
from app.startup_policy import validate_startup_policy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config.from_object(Config)


@app.template_global()
def copy_request_key():
    return secrets.token_urlsafe(24)


@lru_cache(maxsize=8)
def _asset_digest(path, modified_ns, size):
    with open(path, 'rb') as asset:
        return hashlib.sha256(asset.read()).hexdigest()[:16]


@app.template_global()
def asset_version(filename):
    path = os.path.join(app.static_folder, filename)
    try:
        stat = os.stat(path)
        return _asset_digest(path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        return 'unavailable'

if not app.debug:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler(),
        ],
    )
else:
    logging.basicConfig(level=logging.DEBUG)

app_env = os.getenv("FLASK_ENV", "").lower()
is_production = app_env == "production"
secret_key = app.config.get("SECRET_KEY")
validate_startup_policy(
    app_env=app_env,
    secret_key=secret_key,
    secure_cookies_enabled=app.config.get("SESSION_COOKIE_SECURE"),
)

app.secret_key = secret_key
app.permanent_session_lifetime = app.config["PERMANENT_SESSION_LIFETIME"]
app.jinja_env.cache = None

limiter.init_app(app)
csrf.init_app(app)
oauth.init_app(app)
oauth.register(
    name="keycloak",
    client_id=app.config["OIDC_CLIENT_ID"],
    client_secret=app.config["OIDC_CLIENT_SECRET"],
    server_metadata_url=app.config["OIDC_DISCOVERY_URL"],
    client_kwargs={
        "scope": app.config["OIDC_SCOPES"],
        "code_challenge_method": "S256",
    },
)

from app.repositories.error_report_repo import ErrorReportRepository
from app.integrations.error_reporting import install_error_reporting

app.extensions['error_reports'] = ErrorReportRepository(os.path.join(
    os.path.dirname(os.getenv('APP_DB_PATH', os.path.join(BASE_DIR, 'app.db'))),
    os.path.basename(os.getenv('APP_DB_PATH', 'app.db')) + '.errors.db',
))
install_error_reporting(app.extensions['error_reports'])
