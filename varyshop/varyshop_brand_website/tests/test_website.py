from odoo.tests import HttpCase, tagged

from odoo.addons.varyshop_brand_website.models.website import (
    ODOO_FAVICON, VARYSHOP_FAVICON, favicon_variants, read_favicon)


@tagged("post_install", "-at_install")
class TestBrandWebsite(HttpCase):

    def test_footer(self):
        html = self.url_open("/").text
        self.assertIn("o_brand_promotion", html)
        self.assertIn("utm_medium=website", html)
        self.assertIn("/varyshop_brand/static/img/logo.svg", html)
        self.assertNotIn("www.odoo.com", html)
        self.assertIn("Business management and process automation", html)
        self.assertNotIn("free website", html)

    def test_footer_czech(self):
        lang = self.env["res.lang"]._activate_lang("cs_CZ")
        self.env["website"].get_current_website().language_ids |= lang
        self.env["ir.module.module"]._load_module_terms(["varyshop_brand_website"], ["cs_CZ"], overwrite=True)
        html = self.url_open("/cs/").text
        self.assertIn("Řízení firmy a automatizace procesů", html)

    def test_new_website_favicon(self):
        website = self.env["website"].create({"name": "Nový web"})
        self.assertIn(website.favicon, favicon_variants(VARYSHOP_FAVICON))

    def test_swap_keeps_own_favicon(self):
        websites = self.env["website"].create([{"name": "Odoo favicon"}, {"name": "Vlastní favicon"}])
        websites[0].favicon = read_favicon(ODOO_FAVICON)
        websites[1].favicon = read_favicon("varyshop_brand/static/img/favicon.png")
        own = websites[1].favicon
        self.env["website"]._varyshop_swap_favicon(ODOO_FAVICON, VARYSHOP_FAVICON)
        self.assertIn(websites[0].favicon, favicon_variants(VARYSHOP_FAVICON))
        self.assertEqual(websites[1].favicon, own)
