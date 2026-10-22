from datetime import date, datetime

from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.tests.common import BASE

from .common import SaleCase

ITEM = BASE + 7001          # storable item
SERVICE = BASE + 7002       # service item (not storable)
LOT_A = BASE + 8001         # layer with a lot
NO_LOT = BASE + 8002        # layer without a lot
LOT_B = BASE + 8003
TOTAL = BASE + 9001


@tagged("post_install", "-at_install")
class TestStockMirror(SaleCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env["elite.vet.winvet.sync"]
        cls.Layer = cls.env["elite.vet.winvet.stock.layer"]
        cls.Total = cls.env["elite.vet.winvet.stock.total"]
        cls.env["ir.config_parameter"].sudo().set_param("elite_vet_sale.winvet_master", "1")
        cls.run_no = 0
        cls.push_raw("items", [
            {"id": ITEM, "code": "SK1", "name": "Skladová položka", "classification": "product",
             "stock_tracked": True, "tracked_drug": False, "unit": "ks", "barcode": None,
             "price": 200.0, "price_untaxed": 178.57, "vat_rate": 12.0, "active": True},
            {"id": SERVICE, "code": "SK2", "name": "Služba", "classification": "service",
             "stock_tracked": False, "tracked_drug": False, "unit": "ks", "barcode": None,
             "price": 100.0, "price_untaxed": 82.64, "vat_rate": 21.0, "active": True},
        ], mode="incremental")
        Item = cls.env["elite.vet.winvet.item"].with_context(active_test=False)
        cls.product = Item.search([("winvet_ref", "=", ITEM)]).product_id
        cls.service = Item.search([("winvet_ref", "=", SERVICE)]).product_id
        cls.stock = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1).lot_stock_id

    # helpers --------------------------------------------------------------
    @classmethod
    def push_raw(cls, entity, records, mode="full"):
        cls.run_no += 1
        res = cls.sync.push({"entity": entity, "mode": mode, "records": records, "deleted": [],
                             "batch": 1, "batches": 1, "run_id": "stock-%s" % cls.run_no})
        assert res.get("ok"), res
        return res

    def layer(self, ref, quantity, lot=None, expiry=None, item=ITEM, received="2026-09-01", cost=112.0,
              vat=12.0, incl=True):
        return {"id": ref, "item_id": item, "lot": lot, "expiry": expiry, "received": received,
                "quantity": quantity, "unit_cost": cost, "vat_rate": vat, "cost_includes_vat": incl,
                "supplier": "Dodavatel"}

    def mirror(self, layers, totals):
        """Store layers and totals, then mirror. Incremental pushes keep any other stock rows of
        the database as they are, so the mirror only changes this item (fast on a copy with data)."""
        self.push_raw("stock_lots", layers, mode="incremental")
        self.push_raw("stock_totals", totals, mode="incremental")
        return self.Layer._apply_mirror()

    def full_run(self, layers, totals):
        """A full run as the bridge sends it: stock_lots first, then stock_totals (mirror after it)."""
        self.push_raw("stock_lots", layers)
        return self.push_raw("stock_totals", totals)

    def warnings(self, result):
        return [w for w in result["warnings"] if "SK1" in w]

    def total(self, value, item=ITEM, ref=TOTAL):
        return {"id": ref, "item_id": item, "total": value}

    def default_layers(self):
        return [self.layer(LOT_A, 3.0, lot="A", expiry="2027-01-31"),
                self.layer(NO_LOT, 2.0, expiry="2026-12-31")]

    def quants(self, product=None):
        quants = self.env["stock.quant"].search([("product_id", "=", (product or self.product).id),
                                                 ("location_id", "=", self.stock.id)])
        out = {}
        for quant in quants:
            out[quant.lot_id.name] = out.get(quant.lot_id.name, 0.0) + quant.quantity
        return out

    def last_error(self):
        return self.env["elite.vet.winvet.status"].get_status().last_error or ""

    def setUp(self):
        super().setUp()
        self.env["elite.vet.winvet.status"].get_status().last_error = False

    # tests ----------------------------------------------------------------
    def test_models_store_payload(self):
        self.mirror(self.default_layers(), [self.total(5.0)])
        layer = self.Layer.search([("winvet_ref", "=", LOT_A)])
        self.assertEqual(layer.item_id.winvet_ref, ITEM)
        self.assertEqual(layer.lot_name, "A")
        self.assertEqual(layer.expiry, date(2027, 1, 31))
        self.assertEqual(layer.received, date(2026, 9, 1))
        self.assertEqual(layer.quantity, 3.0)
        self.assertEqual(layer.unit_cost, 112.0)
        self.assertEqual(layer.vat_rate, 12.0)
        self.assertTrue(layer.cost_includes_vat)
        self.assertEqual(layer.supplier, "Dodavatel")
        total = self.Total.search([("winvet_ref", "=", TOTAL)])
        self.assertEqual(total.item_id.winvet_ref, ITEM)
        self.assertEqual(total.total, 5.0)

    def test_layers_become_lots(self):
        result = self.mirror(self.default_layers(), [self.total(5.0)])
        self.assertEqual(self.quants(), {"A": 3.0, "WV-%d" % NO_LOT: 2.0})
        lot = self.env["stock.lot"].search([("product_id", "=", self.product.id), ("name", "=", "A")])
        self.assertEqual(lot.expiration_date, datetime(2027, 1, 31, 12, 0))
        self.assertEqual(self.warnings(result), [])
        # a second run changes nothing
        self.assertEqual(self.Layer._apply_mirror()["adjusted"], 0)

    def test_full_run_mirrors_and_reports(self):
        self.full_run(self.default_layers(), [self.total(6.0)])
        # the surplus goes to the lot with the latest expiry
        self.assertEqual(self.quants(), {"A": 4.0, "WV-%d" % NO_LOT: 2.0})
        self.assertIn("Položka SK1: rozdíl 1 proti stavu WinVetu", self.last_error())
        self.assertNotIn("záporn", self.last_error())

    def test_incremental_totals_do_not_mirror(self):
        self.push_raw("stock_lots", self.default_layers())
        self.push_raw("stock_totals", [self.total(5.0)], mode="incremental")
        self.assertEqual(self.quants(), {})

    def test_shortage_reduces_latest_expiry_with_warning(self):
        result = self.mirror(self.default_layers(), [self.total(4.0)])
        self.assertEqual(self.quants(), {"A": 2.0, "WV-%d" % NO_LOT: 2.0})
        self.assertEqual(self.warnings(result), ["Položka SK1: rozdíl -1 proti stavu WinVetu"])

    def test_shortage_larger_than_latest_lot(self):
        # the rest of the shortage comes from the lot with the next latest expiry
        result = self.mirror([self.layer(LOT_A, 1.0, lot="A", expiry="2027-01-31"),
                              self.layer(NO_LOT, 2.0, expiry="2026-12-31")], [self.total(1.5)])
        quants = self.quants()
        self.assertEqual(quants.get("A", 0.0), 0.0)
        self.assertEqual(quants["WV-%d" % NO_LOT], 1.5)
        self.assertEqual(self.warnings(result), ["Položka SK1: rozdíl -1.5 proti stavu WinVetu"])

    def test_negative_total_clipped_to_zero(self):
        result = self.mirror([self.layer(LOT_A, 1.0, lot="A", expiry="2027-01-31"),
                              self.layer(NO_LOT, 2.0, expiry="2026-12-31")], [self.total(-1.0)])
        quants = self.quants()
        self.assertEqual(quants.get("A", 0.0), 0.0)
        self.assertEqual(quants.get("WV-%d" % NO_LOT, 0.0), 0.0)
        self.assertIn("Položka SK1: záporný stav WinVetu -1 oříznut na 0", result["warnings"])

    def test_total_without_layers_gets_own_lot(self):
        self.mirror([], [self.total(2.0)])
        self.assertEqual(self.quants(), {"WV-P%d" % ITEM: 2.0})

    def test_missing_layer_zeroes_its_quant(self):
        self.mirror(self.default_layers(), [self.total(5.0)])
        self.full_run([self.layer(LOT_A, 3.0, lot="A", expiry="2027-01-31")], [self.total(3.0)])
        quants = self.quants()
        self.assertEqual(quants["A"], 3.0)
        self.assertEqual(quants.get("WV-%d" % NO_LOT, 0.0), 0.0)
        self.assertFalse(self.Layer.search([("winvet_ref", "=", NO_LOT)]))

    def test_odoo_master_keeps_quants(self):
        self.mirror(self.default_layers(), [self.total(5.0)])
        self.env["ir.config_parameter"].sudo().set_param("elite_vet_sale.winvet_master", "0")
        self.full_run([self.layer(LOT_A, 10.0, lot="A", expiry="2027-01-31")], [self.total(10.0)])
        self.assertEqual(self.quants(), {"A": 3.0, "WV-%d" % NO_LOT: 2.0})
        self.assertEqual(self.Layer.search([("winvet_ref", "=", LOT_A)]).quantity, 10.0)
        self.assertEqual(self.Total.search([("winvet_ref", "=", TOTAL)]).total, 10.0)

    def test_standard_price_from_newest_layer(self):
        self.mirror([self.layer(LOT_A, 3.0, lot="A", expiry="2027-01-31", received="2026-10-01", cost=112.0),
                     self.layer(NO_LOT, 2.0, expiry="2026-12-31", received="2026-01-01", cost=50.0, incl=False)],
                    [self.total(5.0)])
        self.assertAlmostEqual(self.product.standard_price, 100.0, places=2)

    def test_standard_price_without_vat(self):
        self.mirror([self.layer(LOT_A, 3.0, lot="A", expiry="2027-01-31", cost=80.0, incl=False)],
                    [self.total(3.0)])
        self.assertAlmostEqual(self.product.standard_price, 80.0, places=2)

    def test_rows_without_item_skipped(self):
        res = self.push_raw("stock_lots", [self.layer(LOT_B, 1.0, item=None)], mode="incremental")
        self.assertEqual(res["skipped"], 1)
        res = self.push_raw("stock_totals", [self.total(5.0), self.total(7.0, item=None, ref=TOTAL + 1)],
                            mode="incremental")
        self.assertEqual(res["skipped"], 1)
        self.assertFalse(self.Total.search([("winvet_ref", "=", TOTAL + 1)]))
        self.assertFalse(self.Layer.search([("winvet_ref", "=", LOT_B)]))

    def test_negative_layer_counts_as_zero(self):
        # over-issued receipt B: WinVet total 1 = 3 - 2; B stays at 0, its excess comes off lot A
        result = self.mirror([self.layer(LOT_A, 3.0, lot="A", expiry="2027-01-31"),
                              self.layer(LOT_B, -2.0, lot="B", expiry="2026-11-30")], [self.total(1.0)])
        self.assertEqual(self.Layer.search([("winvet_ref", "=", LOT_B)]).quantity, -2.0)
        quants = self.quants()
        self.assertEqual(quants["A"], 1.0)
        self.assertEqual(quants.get("B", 0.0), 0.0)
        self.assertEqual(self.warnings(result), [])

    def test_layers_of_service_skipped(self):
        self.mirror(self.default_layers() + [self.layer(LOT_B, 4.0, lot="S", item=SERVICE)],
                    [self.total(5.0), self.total(4.0, item=SERVICE, ref=TOTAL + 2)])
        self.assertFalse(self.env["stock.quant"].search([("product_id", "=", self.service.id)]))
        self.assertEqual(self.quants(), {"A": 3.0, "WV-%d" % NO_LOT: 2.0})
