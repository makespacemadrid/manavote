import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestProductionConfig(unittest.TestCase):
    def test_app_setup_fails_with_default_secret_in_production(self):
        env = os.environ.copy()
        env["FLASK_ENV"] = "production"
        env.pop("SECRET_KEY", None)

        result = subprocess.run(
            ["python", "-c", "import app.web.app_setup"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be set to a non-default value", result.stderr)

    def test_init_db_fails_without_bootstrap_password_in_production(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        env = os.environ.copy()
        env["FLASK_ENV"] = "production"
        env["SECRET_KEY"] = "prod-secret-for-test"
        env["APP_DB_PATH"] = db_path
        env.pop("ADMIN_BOOTSTRAP_PASSWORD", None)

        try:
            result = subprocess.run(
                ["python", "-c", "from app.web.routes import main_routes; main_routes.init_db()"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ADMIN_BOOTSTRAP_PASSWORD must be set before first startup in production", result.stderr)


if __name__ == "__main__":
    unittest.main()
