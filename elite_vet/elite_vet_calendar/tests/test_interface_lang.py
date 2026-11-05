"""Accounts on English (US) see the English interface, which only exists as en_GB."""
import odoo
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestInterfaceLang(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("en_GB")
        cls.env["res.lang"]._activate_lang("cs_CZ")
        cls.english = new_test_user(cls.env, login="english_t", lang="en_US", groups="base.group_user")
        cls.czech = new_test_user(cls.env, login="czech_t", lang="cs_CZ", groups="base.group_user")

    def _client_lang(self):
        return self.make_jsonrpc_request("/web/session/get_session_info")["user_context"]["lang"]

    def test_english_account_gets_uk_interface(self):
        self.authenticate("english_t", "english_t")
        self.assertEqual(self._client_lang(), "en_GB")
        self.assertIn('"lang": "en_GB"', self.url_open("/odoo").text)
        self.assertEqual(self.english.lang, "en_US", "the account itself stays as it was")

    def test_other_languages_stay(self):
        self.authenticate("czech_t", "czech_t")
        self.assertEqual(self._client_lang(), "cs_CZ")

    def test_stays_en_us_without_en_gb(self):
        self.env["res.users"].search([("lang", "=", "en_GB")]).lang = "cs_CZ"
        self.env["res.lang"]._lang_get("en_GB").active = False
        self.authenticate("english_t", "english_t")
        self.assertEqual(self._client_lang(), "en_US")

    def test_running_session_switches_without_new_login(self):
        session = self.authenticate("english_t", "english_t")
        session.context["lang"] = "en_US"
        odoo.http.root.session_store.save(session)
        self.assertIn('"lang": "en_GB"', self.url_open("/odoo").text)

    def test_outside_a_request_nothing_changes(self):
        """Crons run outside a request and write Czech texts on en_US accounts."""
        context = self.env["res.users"].with_user(self.english).context_get()
        self.assertEqual(context["lang"], "en_US")
