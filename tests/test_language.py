import unittest
import sys
import inspect
from pathlib import Path

sys.path.insert(0, ".")

import app as budget_app
from app.web.routes import main_routes, proposal_routes
from app.web import app_setup


class TestLanguageSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
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

    def test_about_page_translations(self):
        """About page content changes with language selection"""
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Transparency and tracking", response.data)

        self.client.get("/set-language/es")
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Transparencia y seguimiento", response.data)

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
        self.assertIn("Funding", budget_app.TRANSLATIONS["en"])
        self.assertIn("Transparency and tracking", budget_app.TRANSLATIONS["en"])
        self.assertIn("Make Admin", budget_app.TRANSLATIONS["en"])
        self.assertIn("Remove Admin", budget_app.TRANSLATIONS["en"])

    def test_spanish_translations_exist(self):
        """Spanish translations are defined"""
        self.assertIn("Dashboard", budget_app.TRANSLATIONS["es"])
        self.assertIn("Proposals", budget_app.TRANSLATIONS["es"])
        self.assertIn("Budget", budget_app.TRANSLATIONS["es"])
        self.assertIn("Funding", budget_app.TRANSLATIONS["es"])
        self.assertIn("Transparency and tracking", budget_app.TRANSLATIONS["es"])
        self.assertIn("Make Admin", budget_app.TRANSLATIONS["es"])
        self.assertIn("Remove Admin", budget_app.TRANSLATIONS["es"])

    def test_spanish_translations_differ(self):
        """Spanish translations differ from English"""
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Dashboard"], "Panel")
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Proposals"], "Propuestas")
        self.assertEqual(budget_app.TRANSLATIONS["es"]["Budget"], "Presupuesto")

    def test_about_page_translation_keys_are_complete(self):
        """About-page specific keys exist and are non-empty in both locales"""
        about_keys = [
            "Funding",
            "Transparency and tracking",
            "About intro 1",
            "About intro 2",
            "About flow submit vote",
            "About flow approved",
            "About flow undo",
            "About funding 1",
            "About funding 2",
            "About tracking 1",
            "About tracking 2",
            "About tracking 3",
            "About governance",
        ]
        for locale in ("en", "es"):
            translations = budget_app.TRANSLATIONS[locale]
            for key in about_keys:
                with self.subTest(locale=locale, key=key):
                    self.assertIn(key, translations)
                    self.assertTrue(str(translations[key]).strip())


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

    def test_proposal_detail_translation_keys_exist(self):
        """Proposal detail confirm/button labels exist in both locales"""
        keys = ("Delete proposal confirm", "Undo approval confirm", "Undo Approval", "of")
        for locale in ("en", "es"):
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    self.assertIn(key, budget_app.TRANSLATIONS[locale])

    def test_translation_locales_have_same_keyset(self):
        """English and Spanish translations should define the same keys."""
        en_keys = set(budget_app.TRANSLATIONS["en"].keys())
        es_keys = set(budget_app.TRANSLATIONS["es"].keys())
        self.assertSetEqual(en_keys, es_keys)


class TestLoggingConfiguration(unittest.TestCase):
    def test_file_logging_targets_app_log_in_source(self):
        """App logging configuration should target app.log (not budget.log)."""
        source = inspect.getsource(app_setup)
        self.assertIn('logging.FileHandler("app.log")', source)
        self.assertNotIn('logging.FileHandler("budget.log")', source)


class TestDashboardFiltersAndStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
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


class TestCalendarBudgetData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_calendar_budget_data_structure(self):
        """Calendar returns cash_balance and pending for each day"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("cash_balance", html)
        self.assertIn("pending", html)

    def test_calendar_cash_in_out_bars(self):
        """Calendar shows Cash In and Cash Out bars"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("cashInData", html)
        self.assertIn("cashOutData", html)

    def test_calendar_table_uses_budget_in_out_labels(self):
        """Calendar activity table uses Budget In/Out labels, not Income/Expense"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Budget In", html)
        self.assertIn("Budget Out", html)
        self.assertNotIn(">Income<", html)
        self.assertNotIn(">Expense<", html)

    def test_calendar_approved_bar(self):
        """Calendar shows Approved bar for item approvals"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("approvedData", html)

    def test_calendar_approved_query_includes_all_approvals(self):
        """Calendar approved bars include all approved proposals, not only over-budget ones"""
        source = inspect.getsource(proposal_routes.calendar)
        self.assertIn("status = 'approved' AND processed_at IS NOT NULL GROUP BY day", source)
        self.assertIn("status = 'approved' AND processed_at IS NOT NULL AND over_budget_at IS NOT NULL GROUP BY day", source)

    def test_calendar_approved_type_uses_purple_color(self):
        """Calendar template styles approved proposal type in purple"""
        template = Path("templates/calendar.html").read_text(encoding="utf-8")
        self.assertIn("color: #9932CC;", template)

    def test_calendar_amounts_use_status_colors_for_proposals(self):
        """Calendar proposal amounts use purple for approved and blue for active"""
        template = Path("templates/calendar.html").read_text(encoding="utf-8")
        self.assertIn(".amount-approved { color: #9932CC; }", template)
        self.assertIn(".amount-active { color: #00d9ff; }", template)
        self.assertIn("item.item_type == 'proposal' and item.status == 'approved'", template)
        self.assertIn("item.item_type == 'proposal' and item.status == 'active'", template)
        self.assertIn("item.status in ['approved', 'active']", template)
        self.assertIn("item.amount|abs", template)

    def test_calendar_committed_budget_label(self):
        """Calendar shows Pending Budget line label in English"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("label: 'Pending Budget'", html)

    def test_calendar_committed_budget_spanish(self):
        """Calendar shows Pending Budget line label in Spanish"""
        self.client.get("/set-language/es")
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("label: 'Presupuesto Pendiente'", html)

    def test_calendar_table_labels_spanish(self):
        """Calendar table labels are localized in Spanish for budget flows"""
        self.client.get("/set-language/es")
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Entradas", html)
        self.assertIn("Salidas", html)



    def test_calendar_chart_proposal_labels_spanish(self):
        """Calendar chart proposal series labels are localized in Spanish"""
        self.client.get("/set-language/es")
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("label: 'Propuestas (En votación)'", html)
        self.assertIn("label: 'Propuestas (Aprobadas)'", html)

    def test_calendar_pagination_uses_translation_keys(self):
        """Calendar pagination uses localized Previous/Next keys in template"""
        template = Path("templates/calendar.html").read_text(encoding="utf-8")
        self.assertIn("{{ 'Previous'|lang }}", template)
        self.assertIn("{{ 'Next'|lang }}", template)

    def test_calendar_committed_uses_cash_minus_pending_formula(self):
        """Committed series is computed as cash_balance - pending"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("const committedData = cashBalanceData.map((b, i) => b - pendingData[i]);", html)

    def test_calendar_lines_do_not_stack_with_each_other(self):
        """Budget Balance and Committed line datasets have separate stack keys"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("stack: 'line_budget_balance'", html)
        self.assertIn("stack: 'line_committed'", html)

class TestDashboardFilters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_dashboard_shows_all_filter(self):
        """Dashboard shows All filter button"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("All", html)

    def test_dashboard_shows_active_filter(self):
        """Dashboard shows Active filter button"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Active", html)

    def test_dashboard_shows_approved_filter(self):
        """Dashboard shows Approved filter button"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Approved", html)

    def test_dashboard_shows_pending_budget_filter(self):
        """Dashboard shows Pending Budget filter button"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Pending Budget", html)

    def test_dashboard_shows_purchased_filter(self):
        """Dashboard shows Purchased filter button"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Purchased", html)

    def test_dashboard_filter_case_title(self):
        """Filter buttons use Title Case"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("Pending Purchase", html)
        self.assertIn("Basic", html)
        self.assertIn("Standard", html)
        self.assertIn("Expensive", html)


class TestBudgetHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_budget_history_shows_balance(self):
        """Budget history shows balance column"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Balance", html)

    def test_budget_history_shows_amount(self):
        """Budget history shows amount column"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Amount", html)

    def test_budget_history_shows_description(self):
        """Budget history shows description column"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Description", html)

    def test_budget_history_shows_date(self):
        """Budget history shows date column"""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("Date", html)


class TestProposalStatusTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_status_active_lowercase(self):
        """Active status shows lowercase"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("status-active", html)

    def test_status_approved_lowercase(self):
        """Approved status shows lowercase"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("status-approved", html)

    def test_status_rejected_lowercase(self):
        """Rejected status shows lowercase"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("status-rejected", html)

    def test_status_over_budget_lowercase(self):
        """Over-budget status shows lowercase"""
        response = self.client.get("/dashboard")
        html = response.data.decode("utf-8")
        self.assertIn("status-over-budget", html)


class TestTranslationKeys(unittest.TestCase):
    def test_english_translations_complete(self):
        """All needed English translations exist"""
        t = budget_app.TRANSLATIONS["en"]
        self.assertIn("Dashboard", t)
        self.assertIn("Proposals", t)
        self.assertIn("Budget", t)
        self.assertIn("All", t)
        self.assertIn("Active", t)
        self.assertIn("Approved", t)
        self.assertIn("Pending Budget", t)
        self.assertIn("Purchased", t)
        self.assertIn("active", t)
        self.assertIn("approved", t)
        self.assertIn("pending_budget", t)

    def test_spanish_translations_complete(self):
        """All needed Spanish translations exist"""
        t = budget_app.TRANSLATIONS["es"]
        self.assertIn("Dashboard", t)
        self.assertIn("Proposals", t)
        self.assertIn("Budget", t)
        self.assertIn("All", t)
        self.assertIn("Active", t)
        self.assertIn("Approved", t)
        self.assertIn("Pending Budget", t)
        self.assertIn("Purchased", t)
        self.assertIn("active", t)
        self.assertIn("approved", t)
        self.assertIn("pending_budget", t)

    def test_committed_translation(self):
        """Committed translation exists"""
        en = budget_app.TRANSLATIONS["en"]
        es = budget_app.TRANSLATIONS["es"]
        self.assertEqual(en["Committed"], "Committed")
        self.assertEqual(es["Committed"], "Comprometido")


class TestCalendarChartData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        budget_app.app.config["TESTING"] = True
        budget_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = budget_app.app.test_client()

    def setUp(self):
        with self.client.session_transaction() as session:
            session["member_id"] = 1
            session["username"] = "admin"
            session["is_admin"] = 1
            session["lang"] = "en"

    def test_calendar_has_budget_chart(self):
        """Calendar has budget chart canvas"""
        response = self.client.get("/calendar")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("budgetChart", html)
        self.assertIn("Chart", html)

    def test_calendar_chart_has_balance_line(self):
        """Chart has Budget Balance line"""
        response = self.client.get("/calendar")
        html = response.data.decode("utf-8")
        self.assertIn("cashBalanceData", html)

    def test_calendar_chart_has_committed_line(self):
        """Chart has Committed line"""
        response = self.client.get("/calendar")
        html = response.data.decode("utf-8")
        self.assertIn("committedData", html)

    def test_calendar_chart_has_bars(self):
        """Chart has bars for Cash In/Out and Approved"""
        response = self.client.get("/calendar")
        html = response.data.decode("utf-8")
        self.assertIn("cashInData", html)
        self.assertIn("cashOutData", html)
        self.assertIn("approvedData", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
