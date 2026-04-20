"""Application package and factory."""

from .web.routes.main_routes import *  # noqa: F401,F403
from .web.routes.main_routes import app as flask_app


def create_app():
    """App factory entrypoint for WSGI servers and tests."""
    return flask_app


app = create_app()
