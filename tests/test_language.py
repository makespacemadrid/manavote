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
        self.assertIn(b"Budget", response.data)
        self.assertNotIn(b"Presupuesto", response.data)

    def test_switch_to_spanish(self):
        """Can switch to Spanish"""
        response = self.client.get("/set-language/es")
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/dashboard")
        # In Spanish - shows Historial
        self.assertIn(b"Presupuesto", response.data)
        self.assertIn(b"Historial", response.data)
        # Should NOT show English "Budget History"
        self.assertNotIn(b"Budget History", response.data)

    def test_switch_back_to_english(self):
        """Can switch back to English"""
        self.client.get("/set-language/es")
        response = self.client.get("/dashboard")
        self.assertIn(b"Presupuesto", response.data)

        self.client.get("/set-language/en")
        response = self.client.get("/dashboard")
        self.assertIn(b"Budget", response.data)

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
        self.assertIn(b"Budget", response.data)

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

    def test_filter_button_translations_title_case(self):
        """Filter buttons use Title Case translations"""
        en = budget_app.TRANSLATIONS["en"]
        self.assertEqual(en["All"], "All")
        self.assertEqual(en["Active"], "Active")
        self.assertEqual(en["Approved"], "Approved")
        self.assertEqual(en["Pending Budget"], "Pending Budget")
        self.assertEqual(en["Pending Purchase"], "Pending Purchase")
        self.assertEqual(en["Purchased"], "Purchased")
        self.assertEqual(en["Basic"], "Basic")
        self.assertEqual(en["Standard"], "Standard")
        self.assertEqual(en["Expensive"], "Expensive")

    def test_status_tag_translations_lowercase(self):
        """Status tags use lowercase translations"""
        en = budget_app.TRANSLATIONS["en"]
        self.assertEqual(en["active"], "active")
        self.assertEqual(en["approved"], "approved")
        self.assertEqual(en["pending_budget"], "pending_budget")
        self.assertEqual(en["purchased"], "purchased")
        self.assertEqual(en["basic"], "basic")
        self.assertEqual(en["standard"], "standard")
        self.assertEqual(en["expensive"], "expensive")

    def test_spanish_filter_button_translations(self):
        """Spanish filter buttons use Title Case"""
        es = budget_app.TRANSLATIONS["es"]
        self.assertEqual(es["All"], "Todas")
        self.assertEqual(es["Active"], "Activa")
        self.assertEqual(es["Approved"], "Aprobada")
        self.assertEqual(es["Pending Budget"], "Presupuesto Pendiente")
        self.assertEqual(es["Pending Purchase"], "Pendiente Compra")
        self.assertEqual(es["Purchased"], "Compradas")

    def test_spanish_status_tag_translations(self):
        """Spanish status tags use lowercase"""
        es = budget_app.TRANSLATIONS["es"]
        self.assertEqual(es["active"], "activo")
        self.assertEqual(es["approved"], "aprobado")
        self.assertEqual(es["pending_budget"], "pendiente_presupuesto")
        self.assertEqual(es["purchased"], "comprado")


class TestDashboardFiltersAndStatus(unittest.TestCase):
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

    def test_dashboard_filter_buttons_title_case(self):
        """Dashboard filter buttons show Title Case"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("All", html)
        self.assertIn("Active", html)
        self.assertIn("Approved", html)
        self.assertIn("Pending Budget", html)
        self.assertIn("Pending Purchase", html)
        self.assertIn("Purchased", html)
        self.assertIn("Basic", html)
        self.assertIn("Standard", html)
        self.assertIn("Expensive", html)

    def test_dashboard_status_tags_lowercase(self):
        """Dashboard proposal status tags show lowercase"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("status-active", html)

    def test_dashboard_spanish_filter_buttons_title_case(self):
        """Spanish dashboard filter buttons show Title Case"""
        self.client.get("/set-language/es")
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Todas", html)
        self.assertIn("Activa", html)
        self.assertIn("Aprobada", html)
        self.assertIn("Presupuesto Pendiente", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
