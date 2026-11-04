from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import translate
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestPosCzech(TransactionCase):

    def web_terms(self, module="point_of_sale"):
        return {m["id"]: m["string"] for m in code_translations.get_web_translations(module, "cs_CZ")["messages"]}

    def test_czech_is_active(self):
        self.assertIn("cs_CZ", dict(self.env["res.lang"].get_installed()))

    def test_terms_odoo_leaves_untranslated(self):
        self.assertEqual(self.web_terms()["Clear Cache"], "Vymazat mezipaměť")
        self.assertTrue(code_translations.get_python_translations("point_of_sale", "cs_CZ")['Email triggered successfully!'])

    def test_terms_of_odoo_are_included(self):
        self.assertEqual(self.web_terms()["Start adding products"], "Přidejte produkty")

    def test_works_when_original_file_is_missing(self):
        """Production case: the till shows English although the terms exist in Odoo."""
        with patch.object(translate, "get_po_paths", lambda *args, **kwargs: iter(())):
            code_translations.web_translations.pop(("point_of_sale", "cs_CZ"), None)
            try:
                self.assertEqual(self.web_terms()["Internal Note"], "Interní poznámka")
            finally:
                code_translations.web_translations.pop(("point_of_sale", "cs_CZ"), None)

    def test_other_languages_untouched(self):
        german = {m["id"]: m["string"] for m in code_translations.get_web_translations("point_of_sale", "de_DE")["messages"]}
        self.assertNotEqual(german.get("Start adding products"), "Přidejte produkty")

    def test_labels_filled(self):
        field = self.env["ir.model.fields"]._get("pos.config", "show_category_images")
        self.assertNotEqual(field.with_context(lang="cs_CZ").field_description, "Show Category Images")

    def test_manual_edit_is_kept(self):
        field = self.env["ir.model.fields"]._get("pos.config", "show_category_images").with_context(lang="cs_CZ")
        field.field_description = "Moje vlastní popiska"
        self.env["ir.module.module"]._load_module_terms(["elite_pos_l10n_cs"], ["cs_CZ"])
        field.invalidate_recordset()
        self.assertEqual(field.field_description, "Moje vlastní popiska")
