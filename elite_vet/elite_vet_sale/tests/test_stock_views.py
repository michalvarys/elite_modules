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
        arch = self.env[model].with_user(self.nurse).get_view(view_id, "search")["arch"]
        filters = {f.get("name"): f.get("domain") for f in etree.fromstring(arch).iter("filter")}
        context = {
            "datetime": safe_eval_module.datetime, "time": safe_eval_module.time,
            "relativedelta": safe_eval_module.dateutil.relativedelta.relativedelta,
            "context_today": date.today, "uid": self.nurse.id,
        }
        return {name: safe_eval(filters[name], context) for name in FILTERS}

    def test_stock_views_load(self):
        action = self.env.ref("elite_vet_sale.action_stock_overview")
        Quant = self.env["stock.quant"].with_user(self.nurse)
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
        Lot = self.env["stock.lot"].with_user(self.nurse)
        lots = self.lot_soon | self.lot_expired | self.lot_far
        self.assertEqual(Lot.search(lot_domains["below_minimum"] + [("id", "in", lots.ids)]), self.lot_soon)
        self.assertEqual(Lot.search(lot_domains["expiring_30_days"] + [("id", "in", lots.ids)]), self.lot_soon)
        self.assertEqual(Lot.search(lot_domains["expired"] + [("id", "in", lots.ids)]), self.lot_expired)

    def test_menu_for_nurse_not_reception(self):
        menu = self.env.ref("elite_vet_sale.menu_stock_overview")
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(self.nurse)._visible_menu_ids())
        self.assertNotIn(menu.id, self.env["ir.ui.menu"].with_user(self.reception)._visible_menu_ids())

    def test_reception_reads_stock_but_cannot_write(self):
        menu = self.env.ref("elite_vet_sale.menu_stock_overview_clinic")
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(self.reception)._visible_menu_ids())
        action = self.env.ref("elite_vet_sale.action_stock_overview")
        Quant = self.env["stock.quant"].with_user(self.reception)
        Lot = self.env["stock.lot"].with_user(self.reception)
        Quant.get_view(action.view_id.id, "list")
        quants = Quant.search([("product_id", "=", self.enough.id), ("location_id", "=", self.stock.id)])
        self.assertEqual(quants.lot_id, self.lot_expired | self.lot_far)
        quants.read(["product_id", "lot_id", "expiration_date", "quantity"])
        self.assertEqual(Lot.search([("id", "=", self.lot_soon.id)]), self.lot_soon)
        with self.assertRaises(AccessError):
            Lot.browse(self.lot_soon.id).write({"name": "PR-CHANGED"})
        with self.assertRaises(AccessError):
            Quant.browse(quants[:1].id).write({"inventory_quantity": 99})
        with self.assertRaises(AccessError):
            Lot.create({"name": "PR-NEW", "product_id": self.low.id})
