from odoo.tests import tagged

from odoo.addons.elite_restaurant_pos.tests.common import RestaurantPosCase


@tagged("post_install", "-at_install")
class TestJackPos(RestaurantPosCase):
    MODULE = "elite_jack_pos"
    COMPANY = "Jackgrillbar s.r.o."
    PARENT = False
    PRODUCTS = 143
    FOOD, ALCOHOL, SOFT = "rib_eye", "jd_no7", "red_bull"
    SETUP = {"module": MODULE, "company": COMPANY, "parent": PARENT, "pos_name": "Jack Grill Bar", "code": "JACK",
             "floor": "Přízemí", "tables": 12}

    def test_menu_item(self):
        item = self.product("t_bone")
        self.assertEqual(item.list_price, 789.0)
        self.assertEqual(item.pos_categ_ids.name, "Steaky")
        self.assertTrue(self.product("jd_sinatra_century").is_storable)
