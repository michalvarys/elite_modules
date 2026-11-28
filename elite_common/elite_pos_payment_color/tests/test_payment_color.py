from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPaymentColor(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def test_colour_is_loaded_in_pos(self):
        self.cash_pm1.pos_button_color = "#2e7d32"
        self.open_new_session()
        data = self.pos_session.load_data(["pos.config", "pos.payment.method"])
        methods = {m["id"]: m for m in data["pos.payment.method"]["data"]}
        self.assertEqual(methods[self.cash_pm1.id]["pos_button_color"], "#2e7d32")
        self.assertFalse(methods[self.bank_pm1.id]["pos_button_color"])

    def test_colour_change_with_open_session(self):
        self.open_new_session()
        self.cash_pm1.pos_button_color = "#1565c0"
        self.assertEqual(self.cash_pm1.pos_button_color, "#1565c0")

    def test_config_setting(self):
        self.assertFalse(self.config.payment_buttons_spread)
        settings = self.env["res.config.settings"].create({"pos_config_id": self.config.id})
        settings.pos_payment_buttons_spread = True
        settings.execute()
        self.assertTrue(self.config.payment_buttons_spread)

    def test_invalid_colour(self):
        for value in ("red", "#12345", "#1234567", "2e7d32"):
            with self.assertRaises(ValidationError, msg=value):
                self.cash_pm1.pos_button_color = value
                self.cash_pm1.flush_recordset()
        self.cash_pm1.pos_button_color = False
        self.cash_pm1.pos_button_color = "#ABCDEF"
