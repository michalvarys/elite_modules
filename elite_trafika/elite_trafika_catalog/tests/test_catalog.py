import json
import re

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCatalogLikes(TransactionCase):
    def setUp(self):
        super().setUp()
        self.item = self.env.ref("elite_trafika_catalog.item_white_widow_1g")
        self.item.like_ids.unlink()  # the database can hold real likes
        self.likes = self.env["elite.trafika.catalog.like"]

    def test_items(self):
        items = self.env["elite.trafika.catalog.item"].search([])
        self.assertEqual(len(items), 28)
        for item in items:
            self.assertTrue(item.image_1920, item.name)
        self.assertEqual(len(items.filtered("in_store")), 9)
        self.assertFalse(items.filtered(lambda i: "solid" in i.name.lower()))

    def test_app_on_home_screen(self):
        menu = self.env.ref("elite_trafika_catalog.menu_catalog")
        self.assertFalse(menu.parent_id)
        self.assertTrue(menu.web_icon_data)
        self.assertEqual(len(menu.child_id), 3)

    def test_like_and_withdraw(self):
        self.item.set_liked(True, "instagram")
        self.item.set_liked(True, "restaurace")
        self.assertEqual(self.item.like_count, 2)
        self.item.set_liked(False, "instagram")
        self.assertEqual(self.item.like_count, 1)
        self.assertEqual(self.item.like_ids.source, "restaurace")

    def test_withdraw_without_like_does_nothing(self):
        self.item.set_liked(False, "instagram")
        self.assertEqual(self.item.like_count, 0)

    def test_unusable_source_is_web(self):
        for source in (None, "", "a b", "<script>", "x" * 33):
            self.assertEqual(self.likes.clean_source(source), "web")
        self.assertEqual(self.likes.clean_source(" Instagram "), "instagram")


@tagged("post_install", "-at_install")
class TestCatalogPages(HttpCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "elite_trafika_catalog.website", self.env["website"].get_current_website().name)
        self.item = self.env.ref("elite_trafika_catalog.item_white_widow_1g")
        self.item.like_ids.unlink()  # the database can hold real likes
        self.adult = {"Cookie": "elite_trafika_18=1"}

    def _interest(self, headers=None):
        return self.url_open("/katalog/zajem", data=json.dumps({
            "jsonrpc": "2.0", "method": "call", "id": 1,
            "params": {"item_id": self.item.id, "liked": True, "source": "qr"},
        }), headers={"Content-Type": "application/json", **(headers or {})}).json()["result"]

    def test_gate_hides_products(self):
        response = self.url_open("/katalog?zdroj=instagram")
        self.assertIn("Je ti 18?", response.text)
        self.assertNotIn("T9HC", response.text)
        self.assertIn('value="instagram"', response.text)

    def test_confirmed_age_opens_catalog_and_keeps_source(self):
        page = self.url_open("/katalog?zdroj=instagram").text
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        response = self.url_open("/katalog/18", data={"csrf_token": token, "zdroj": "instagram"},
                                 allow_redirects=False)
        self.assertIn("elite_trafika_18=1", response.headers["Set-Cookie"])
        self.assertTrue(response.headers["Location"].endswith("/katalog?zdroj=instagram"))

    def test_catalog_shows_products(self):
        response = self.url_open("/katalog?zdroj=qr", headers=self.adult)
        self.assertIn("T9HC White Widow", response.text)
        self.assertIn('data-source="qr"', response.text)
        self.assertNotIn("Je ti 18?", response.text)

    def test_like_needs_confirmed_age(self):
        self.assertEqual(self._interest(), {"ok": False})
        self.assertEqual(self.item.like_count, 0)
        self.assertEqual(self._interest(self.adult), {"ok": True})
        self.assertEqual(self.item.like_ids.source, "qr")

    def test_hidden_item_takes_no_like(self):
        self.item.active = False
        self.assertEqual(self._interest(self.adult), {"ok": False})

    def test_other_website_has_no_catalog(self):
        self.env["ir.config_parameter"].sudo().set_param("elite_trafika_catalog.website", "Jiný web")
        self.assertEqual(self.url_open("/katalog", headers=self.adult).status_code, 404)
