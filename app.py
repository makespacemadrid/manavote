"""Thin startup wrapper for the ManaVote application."""

from app import app, create_app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
