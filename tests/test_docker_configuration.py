"""Regression checks for the production container configuration."""

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_compose_uses_writable_named_volume_for_database():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "APP_DB_PATH: \"/data/app.db\"" in compose
    assert "- app_data:/data" in compose
    assert "  app_data:" in compose
    assert "./app.db:/data/app.db" not in compose


def test_quickstart_documents_runtime_port_and_database_migration():
    quickstart = (ROOT / "docs" / "QUICKSTART.md").read_text()

    assert "http://localhost:45000" in quickstart
    assert "cp app.db app.db.backup" in quickstart
    assert "docker compose cp app.db web:/data/app.db" in quickstart
