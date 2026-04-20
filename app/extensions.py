from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "100 per hour"], storage_uri="memory://")


def init_extensions(app):
    limiter.init_app(app)
