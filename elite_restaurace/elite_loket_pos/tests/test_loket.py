from odoo.tests import tagged

from odoo.addons.elite_restaurant_pos.tests.common import RestaurantPosCase


@tagged("post_install", "-at_install")
class TestLoketPos(RestaurantPosCase):
    MODULE = "elite_loket_pos"
    COMPANY = "Přírodní Pivní Lázně s.r.o."
    PARENT = False
    PRODUCTS = 82
    FOOD, ALCOHOL, SOFT = "kachna", "stary_hrad_svetle_0_5", "mattoni"
    SETUP = {"module": MODULE, "company": COMPANY, "parent": PARENT, "pos_name": "Staroslovanská kuchyně",
             "code": "LOKET", "floor": "Restaurace", "tables": 12}

    def test_menu_item(self):
        item = self.product("masova_misa")
        self.assertEqual(item.list_price, 1390.0)
        self.assertEqual(item.description_sale, "Alergeny: 1, 3")
        self.assertEqual(self.product("birell").taxes_id, self.tax(self.setup.soft_drink_rate()))
