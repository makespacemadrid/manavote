import os
import logging
from flask import Flask

from app.config import Config
from app.extensions import limiter, csrf

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
if is_production and (not secret_key or secret_key == "dev-insecure-secret-change-me"):
    raise RuntimeError("SECRET_KEY must be set to a non-default value when FLASK_ENV=production")

app.secret_key = secret_key
app.permanent_session_lifetime = app.config["PERMANENT_SESSION_LIFETIME"]
app.jinja_env.cache = None

limiter.init_app(app)
csrf.init_app(app)
