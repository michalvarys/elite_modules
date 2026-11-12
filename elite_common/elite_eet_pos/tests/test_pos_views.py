from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosEetViews(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = cls.env.ref("base.group_user")
        cls.pos_user = cls.env["res.users"].create({
            "name": "Pokladní", "login": "eet_pos_user",
            "groups_id": [(6, 0, [base.id, cls.env.ref("point_of_sale.group_pos_user").id])],
        })
        cls.pos_manager = cls.env["res.users"].create({
            "name": "Vedoucí", "login": "eet_pos_manager",
            "groups_id": [(6, 0, [base.id, cls.env.ref("point_of_sale.group_pos_manager").id])],
        })
        cls.device = cls.env["elite.eet.device"].create({"pos_config_id": cls.basic_config.id})

    def test_pos_views_load(self):
        for model, needle in [
            ("pos.order", "eet_pok"),
            ("pos.config", "eet_device_id"),
            ("pos.payment.method", "eet_register"),
            ("product.template", "eet_prepaid_voucher"),
        ]:
            arch = self.env(user=self.pos_manager)[model].get_views([(False, "form")])["views"]["form"]["arch"]
            self.assertIn(needle, arch, model)
        self.env(user=self.pos_user)["pos.order"].get_views([(False, "form")])

    def test_menus(self):
        sales_menu = self.env.ref("elite_eet_pos.menu_eet_sales")
        devices_menu = self.env.ref("elite_eet_pos.menu_eet_devices")
        self.assertEqual(sales_menu.parent_id.parent_id, self.env.ref("point_of_sale.menu_point_root"))
        self.assertIn(sales_menu, self.env["ir.ui.menu"].with_user(self.pos_user).search([("id", "=", sales_menu.id)]))
        self.assertFalse(self.env["ir.ui.menu"].with_user(self.pos_user).search([("id", "=", devices_menu.id)]))

    def test_rights(self):
        self.assertTrue(self.pos_user.has_group("elite_eet.group_eet_user"))
        self.assertFalse(self.pos_user.has_group("elite_eet.group_eet_manager"))
        self.assertTrue(self.pos_manager.has_group("elite_eet.group_eet_manager"))
        self.env["elite.eet.sale"].with_user(self.pos_user).search([])
        with self.assertRaises(AccessError):
            self.device.with_user(self.pos_user).write({"name": "x"})
        with self.assertRaises(AccessError):
            self.env["elite.eet.sale"].with_user(self.pos_manager).create({
                "device_id": self.device.id, "porad_cis": "V0", "dat_trzby": "2027-01-15 08:00:00", "celk_trzba": 1,
            })
        sale = self.env["elite.eet.sale"].sudo().create({
            "device_id": self.device.id, "porad_cis": "V1", "dat_trzby": "2027-01-15 08:00:00", "celk_trzba": 1,
        })
        with patch.object(type(self.env["elite.eet.sale"]), "_eet_send", lambda s, first_send=None: {}):
            action = sale.with_user(self.pos_manager).action_send_to_eet()
        self.assertEqual(action["tag"], "display_notification")
