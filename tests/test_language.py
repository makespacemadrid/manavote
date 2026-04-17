import unittest
import sys

sys.path.insert(0, ".")

import app as budget_app


class TestLanguageSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_default_language_is_english(self):
        """Default language is English"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Discretionary Budget", response.data)
        self.assertNotIn(b"Presupuesto Discrecional", response.data)

    def test_switch_to_spanish(self):
        """Can switch to Spanish"""
        response = self.client.get("/set-language/es")
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/dashboard")
        self.assertIn(b"Presupuesto Discrecional", response.data)
        self.assertNotIn(b"Discretionary Budget", response.data)

    def test_switch_back_to_english(self):
        """Can switch back to English"""
        self.client.get("/set-language/es")
        response = self.client.get("/dashboard")
        self.assertIn(b"Presupuesto Discrecional", response.data)

        self.client.get("/set-language/en")
        response = self.client.get("/dashboard")
        self.assertIn(b"Discretionary Budget", response.data)

    def test_language_persists_across_pages(self):
        """Language persists across different pages"""
        self.client.get("/set-language/es")

        response = self.client.get("/dashboard")
        self.assertIn(b"Panel", response.data)

        response = self.client.get("/calendar")
        self.assertIn(b"Calendario de Actividad", response.data)

    def test_calendar_page_translations(self):
        """Calendar page shows correct translations"""
        response = self.client.get("/calendar")
        self.assertIn(b"Activity Calendar", response.data)

        self.client.get("/set-language/es")
        response = self.client.get("/calendar")
        self.assertIn(b"Calendario de Actividad", response.data)

    def test_invalid_language_ignored(self):
        """Invalid language codes are ignored"""
        self.client.get("/set-language/fr")
        response = self.client.get("/dashboard")
        self.assertIn(b"Discretionary Budget", response.data)

    def test_language_in_session(self):
        """Session has correct language after switch"""
        self.client.get("/set-language/es")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["lang"], "es")


class TestTranslations(unittest.TestCase):
    def test_english_translations_exist(self):
        """English translations are defined"""
        self.assertIn("Dashboard", budget_app.TRANSLATIONS["en"])
        self.assertIn("Proposals", budget_app.TRANSLATIONS["en"])
        self.assertIn("Budget", budget_app.TRANSLATIONS["en"])
        self.assertIn("Make Admin", budget_app.TRANSLATIONS["en"])
        self.assertIn("Remove Admin", budget_app.TRANSLATIONS["en"])

    def test_spanish_translations_exist(self):
        """Spanish translations are defined"""
        self.assertIn("Dashboard", budget_app.TRANSLATIONS["es"])
        self.assertIn("Proposals", budget_app.TRANSLATIONS["es"])
        self.assertIn("Budget", budget_app.TRANSLATIONS["es"])
        self.assertIn("Make Admin", budget_app.TRANSLATIONS["es"])
        self.assertIn("Remove Admin", budget_app.TRANSLATIONS["es"])

    def test_spanish_translations_differ(self):
        """Spanish translations differ from English"""
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Dashboard"], "Panel")
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Proposals"], "Propuestas")
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Budget"], "Presupuesto")


if __name__ == "__main__":
    unittest.main(verbosity=2)
