import unittest

from app.startup_policy import get_startup_runtime_policy, validate_startup_policy


class TestStartupPolicy(unittest.TestCase):
    def test_production_rejects_default_secret(self):
        with self.assertRaises(RuntimeError):
            validate_startup_policy("production", "dev-insecure-secret-change-me")

    def test_production_rejects_empty_secret(self):
        with self.assertRaises(RuntimeError):
            validate_startup_policy("production", "")

    def test_non_production_allows_default_secret(self):
        validate_startup_policy("development", "dev-insecure-secret-change-me", secure_cookies_enabled=False)
        validate_startup_policy("test", "dev-insecure-secret-change-me", secure_cookies_enabled=False)

    def test_production_rejects_insecure_cookies_setting(self):
        with self.assertRaises(RuntimeError):
            validate_startup_policy("production", "prod-secret", secure_cookies_enabled=False)

    def test_test_env_disables_optional_startup_jobs(self):
        policy = get_startup_runtime_policy("test")
        self.assertFalse(policy["run_scheduler"])
        self.assertFalse(policy["run_auto_backup"])

    def test_non_test_env_keeps_optional_startup_jobs(self):
        self.assertTrue(get_startup_runtime_policy("development")["run_scheduler"])
        self.assertTrue(get_startup_runtime_policy("production")["run_auto_backup"])


if __name__ == "__main__":
    unittest.main()
