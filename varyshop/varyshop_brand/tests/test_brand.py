import re

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.varyshop_brand.models.mail_mail import rebrand_html


@tagged("post_install", "-at_install")
class TestBrandMail(TransactionCase):

    def test_powered_by_links_in_any_template(self):
        cases = [
            # mail layouts, auth_signup, portal invitation (Czech text around the link stays)
            ('Běží na <a target="_blank" href="https://www.odoo.com?utm_source=db&amp;utm_medium=auth" '
             'style="color: #875A7B;">Odoo</a>', "Běží na <a", ">Varyshop</a>"),
            # digest
            ('Powered by <a href="https://www.odoo.com" target="_blank" class="odoo_link">\n'
             '    <span class="odoo_link_text">Odoo</span></a>', "Powered by", ">Varyshop</span></a>"),
        ]
        for body, *expected in cases:
            result = rebrand_html(body)
            self.assertNotIn("odoo.com", result)
            self.assertIn("https://www.varyshop.eu?utm_source=db&amp;utm_medium=email", result)
            for text in expected:
                self.assertIn(text, result)

    def test_other_links_untouched(self):
        body = ('<a href="https://www.odoo.com/documentation">documentation</a> '
                '<a href="https://example.com">Odoo</a>')
        self.assertEqual(rebrand_html(body), body)

    def test_odoo_purple_in_mail(self):
        body = ('<a style="background-color: #875A7B; color: #fff">Zobrazit</a>'
                '<td style="color:#714b67">x</td><span style="color: #71639E">y</span>'
                '<span style="color: #875A7BFF; background: #a875a7b">z</span>')
        result = rebrand_html(body)
        self.assertEqual(result.count("#3d7bd9"), 3)
        self.assertNotRegex(result, "(?i)#(875a7b|714b67|71639e)\\b")
        self.assertIn("#a875a7b", result)  # other colours stay

    def test_sent_mail_body(self):
        mail = self.env["mail.mail"].create({
            "subject": "Test", "email_to": "test@example.com",
            "body_html": '<p>Ahoj</p><div>Powered by <a href="https://www.odoo.com?utm_source=db&amp;'
                         'utm_medium=email">Odoo</a></div>',
        })
        body = mail._prepare_outgoing_body()
        self.assertIn(">Varyshop</a>", body)
        self.assertNotIn("odoo.com", body)

    def test_backend_colours(self):
        """Top bar and primary buttons in the Varyshop blue, the default website palette untouched."""
        css = self.env["ir.qweb"]._get_asset_bundle("web.assets_backend", js=False).css().raw.decode()
        # the only purple left is Odoo's table picker rule, overridden later in the bundle
        picker = re.findall(r"(?i)\.o-we-tablepicker \.o-we-cell\.active\s*\{background-color:\s*([^;}]+)", css)
        self.assertEqual(picker[-1].strip().lower(), "#3d7bd9")
        self.assertEqual(css.lower().count("#71639e"), 1)
        self.assertRegex(css, "(?i)\\.o_main_navbar\\s*\\{[^}]*#3d7bd9")
        self.assertRegex(css, "(?i)\\.btn-primary\\s*\\{[^}]*--btn-bg:\\s*#3d7bd9")

    def test_mail_layout(self):
        html = self.env["ir.qweb"]._render("mail.mail_notification_light", {
            "company": self.env.company, "message": self.env["mail.message"], "body": "Ahoj",
            "record_name": False, "model_description": False, "subtitles": [],
        })
        self.assertIn("varyshop.eu", html)
        self.assertNotIn("www.odoo.com", html)

    def test_web_app_name(self):
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_param("web.web_app_name"), "Varyshop")


@tagged("post_install", "-at_install")
class TestBrandWeb(HttpCase):

    def test_login_page(self):
        html = self.url_open("/web/login").text
        if "website" in self.env:
            # the website shows the login inside its own layout: favicon of the website and
            # "Powered by" in its footer (varyshop_brand_website)
            self.assertIn("www.varyshop.eu?utm_source=db&amp;utm_medium=website", html)
        else:
            self.assertIn("/varyshop_brand/static/img/favicon.ico", html)
            self.assertIn("Varyshop</span>", html)
            self.assertIn("www.varyshop.eu?utm_source=db&amp;utm_medium=auth", html)
        self.assertNotIn("www.odoo.com", html)
        self.assertNotIn("/web/static/img/favicon.ico", html)

    def test_webmanifest(self):
        manifest = self.url_open("/web/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], "Varyshop")
        self.assertEqual(manifest["theme_color"], "#6ea8fe")
        self.assertEqual({icon["src"] for icon in manifest["icons"]}, {
            "/varyshop_brand/static/img/icon-192x192.png", "/varyshop_brand/static/img/icon-512x512.png"})
        for icon in manifest["icons"]:
            self.assertEqual(self.url_open(icon["src"]).status_code, 200)

    def test_backend_page(self):
        self.authenticate("admin", "admin")
        html = self.url_open("/odoo").text
        self.assertIn("/varyshop_brand/static/img/icon-ios.png", html)
        # session info is JSON in the page, "&" is escaped as \u0026
        self.assertIn('"support_url": "https://www.varyshop.eu?utm_source=db\\u0026utm_medium=support"', html)

    def test_offline_page(self):
        html = self.url_open("/odoo/offline").text
        self.assertIn("Varyshop will load", html)
        self.assertNotIn("Odoo logo", html)
