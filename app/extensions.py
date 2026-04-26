from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "100 per hour"], storage_uri="memory://")
csrf = CSRFProtect()


def init_extensions(app):
    limiter.init_app(app)
    csrf.init_app(app)
