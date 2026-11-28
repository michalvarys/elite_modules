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
             "code": "LOKET", "floors": True}
    TABLES = 25

    def test_menu_item(self):
        item = self.product("masova_misa")
        self.assertEqual(item.list_price, 1390.0)
        self.assertEqual(item.description_sale, "Alergeny: 1, 3")
        self.assertEqual(self.product("birell").taxes_id, self.tax(self.setup.soft_drink_rate()))

    def test_floors(self):
        floors = self.config.floor_ids.sorted("sequence")
        self.assertEqual(floors.mapped("name"), ["1. patro", "2. patro"])
        first, second = floors
        self.assertEqual(sorted(first.table_ids.mapped("table_number")),
                         [1, 2, 3, 4, 5, 6, 7, 8, 21, 22, 23, 24, 25, 26, 31, 32, 33, 34, 35])
        self.assertEqual(sorted(second.table_ids.mapped("table_number")), [11, 12, 13, 14, 15, 16])
        for floor in floors:
            self.assertTrue(floor.floor_background_image, floor.name)
        big = second.table_ids.filtered(lambda t: t.table_number == 14)
        self.assertEqual(big.seats, 10)
        self.assertEqual((big.width, big.height), (280, 80))
