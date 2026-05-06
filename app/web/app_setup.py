import os
import logging
from flask import Flask

from app.config import Config
from app.extensions import limiter, csrf
from app.startup_policy import validate_startup_policy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config.from_object(Config)

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
