from odoo.tests import tagged

from odoo.addons.elite_restaurant_pos.tests.common import RestaurantPosCase


@tagged("post_install", "-at_install")
class TestImiPos(RestaurantPosCase):
    MODULE = "elite_imi_pos"
    COMPANY = "IMI Restaurant"
    PARENT = "Elite"
    PRODUCTS = 247
    FOOD, ALCOHOL, SOFT = "set_imi", "asahi", "coca_cola"
    SETUP = {"module": MODULE, "company": COMPANY, "parent": PARENT, "pos_name": "IMI Restaurant", "code": "IMI",
             "floor": "1. patro", "tables": 12}

    def test_menu_item(self):
        item = self.product("pad_thai")
        self.assertEqual(item.list_price, 360.0)
        self.assertEqual(item.description_sale, "Alergeny: 2, 3, 6, 7")
        self.assertEqual(item.pos_categ_ids.parent_id.name, "Kuchyně")
        self.assertTrue(self.product("asahi").is_storable)
        self.assertFalse(item.is_storable)
