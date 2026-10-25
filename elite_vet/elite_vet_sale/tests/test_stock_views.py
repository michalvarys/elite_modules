from datetime import date, datetime, timedelta

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import safe_eval as safe_eval_module
from odoo.tools.safe_eval import safe_eval

from .common import SaleCase

FILTERS = ("below_minimum", "expiring_30_days", "expired")


@tagged("post_install", "-at_install")
class TestStockViews(SaleCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1).lot_stock_id
        common = {"type": "consu", "is_storable": True, "tracking": "lot", "use_expiration_date": True}
        Product = cls.env["product.product"]
        cls.low = Product.create(dict(common, name="Lék dochází přehled"))
        cls.enough = Product.create(dict(common, name="Lék dost přehled"))
        cls.sold_out = Product.create(dict(common, name="Lék záporný přehled", tracking="none"))
        Orderpoint = cls.env["stock.warehouse.orderpoint"]
        for product in (cls.low, cls.enough):
            Orderpoint.create({"product_id": product.id, "location_id": cls.stock.id,
                               "product_min_qty": 5, "product_max_qty": 10})
        now = datetime.now()
        cls.lot_soon = cls.lot(cls.low, "PR-SOON", now + timedelta(days=10), 2)
        cls.lot_expired = cls.lot(cls.enough, "PR-OLD", now - timedelta(days=3), 4)
        cls.lot_far = cls.lot(cls.enough, "PR-FAR", now + timedelta(days=200), 6)
        cls.env["stock.quant"]._update_available_quantity(cls.sold_out, cls.stock, -1)

    @classmethod
    def lot(cls, product, name, expiry, qty):
        lot = cls.env["stock.lot"].create({"name": name, "product_id": product.id,
                                           "expiration_date": expiry})
        cls.env["stock.quant"]._update_available_quantity(product, cls.stock, qty, lot_id=lot)
        return lot

    def filter_domains(self, model, view_id):
        arch = self.env[model].with_user(self.reception).get_view(view_id, "search")["arch"]
        filters = {f.get("name"): f.get("domain") for f in etree.fromstring(arch).iter("filter")}
        context = {
            "datetime": safe_eval_module.datetime, "time": safe_eval_module.time,
            "relativedelta": safe_eval_module.dateutil.relativedelta.relativedelta,
            "context_today": date.today, "uid": self.reception.id,
        }
        return {name: safe_eval(filters[name], context) for name in FILTERS}

    def test_stock_views_load(self):
        action = self.env.ref("elite_vet_sale.action_stock_overview")
        Quant = self.env["stock.quant"].with_user(self.reception)
        Quant.get_view(action.view_id.id, "list")
        domains = self.filter_domains("stock.quant", action.search_view_id.id)
        internal = [("location_id.usage", "=", "internal")]
        ours = [("product_id", "in", (self.low | self.enough | self.sold_out).ids)]

        def quants(name):
            return Quant.search(domains[name] + internal + ours)

        self.assertEqual(set(quants("below_minimum").product_id.ids), {self.low.id, self.sold_out.id})
        self.assertEqual(quants("expiring_30_days").lot_id, self.lot_soon)
        self.assertEqual(quants("expired").lot_id, self.lot_expired)

        lot_domains = self.filter_domains("stock.lot", self.env.ref("stock.search_product_lot_filter").id)
        Lot = self.env["stock.lot"].with_user(self.reception)
        lots = self.lot_soon | self.lot_expired | self.lot_far
        self.assertEqual(Lot.search(lot_domains["below_minimum"] + [("id", "in", lots.ids)]), self.lot_soon)
        self.assertEqual(Lot.search(lot_domains["expiring_30_days"] + [("id", "in", lots.ids)]), self.lot_soon)
        self.assertEqual(Lot.search(lot_domains["expired"] + [("id", "in", lots.ids)]), self.lot_expired)

    def test_menu_for_till_not_nurse(self):
        """Task 14: Přehled skladu is for the till group (Recepce) and Vedení, not for nurses and doctors."""
        Menu = self.env["ir.ui.menu"]
        for xmlid in ("elite_vet_sale.menu_stock_overview", "elite_vet_sale.menu_stock_overview_clinic"):
            menu = self.env.ref(xmlid)
            # the copy under Ordinace: elite_vet_reception (task 15) narrows it to Vedení
            if xmlid == "elite_vet_sale.menu_stock_overview":
                self.assertIn(self.env.ref("elite_vet_sale.group_till_stock"), menu.groups_id)
            for user in (self.nurse, self.doctor_user):
                self.assertNotIn(menu.id, Menu.with_user(user)._visible_menu_ids(), (xmlid, user.login))
        self.assertIn(self.env.ref("elite_vet_sale.menu_stock_overview").id,
                      Menu.with_user(self.reception)._visible_menu_ids())

    def test_reception_reads_stock(self):
        action = self.env.ref("elite_vet_sale.action_stock_overview")
        Quant = self.env["stock.quant"].with_user(self.reception)
        Lot = self.env["stock.lot"].with_user(self.reception)
        Quant.get_view(action.view_id.id, "list")
        quants = Quant.search([("product_id", "=", self.enough.id), ("location_id", "=", self.stock.id)])
        self.assertEqual(quants.lot_id, self.lot_expired | self.lot_far)
        quants.read(["product_id", "lot_id", "expiration_date", "quantity"])
        self.assertEqual(Lot.search([("id", "=", self.lot_soon.id)]), self.lot_soon)
        # no stock manager rights
        with self.assertRaises(AccessError):
            self.env["stock.warehouse.orderpoint"].with_user(self.reception).browse(
                self.env["stock.warehouse.orderpoint"].search([], limit=1).id).unlink()

    def test_nurse_and_doctor_have_no_lots(self):
        for user in (self.nurse, self.doctor_user):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    self.env["stock.lot"].with_user(user).browse(self.lot_soon.id).read(["name"])
