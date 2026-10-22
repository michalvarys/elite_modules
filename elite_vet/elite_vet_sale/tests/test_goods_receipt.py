from datetime import datetime

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import SaleCase

GS = "\x1d"
GTIN_A = "08595001609991"     # product A has the 13-digit EAN form as barcode


@tagged("post_install", "-at_install")
class TestGoodsReceipt(SaleCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Receipt = cls.env["elite.vet.goods.receipt"]
        # Odoo leads the stock (after the switch from WinVet); the trial run has its own test.
        cls.env["ir.config_parameter"].sudo().set_param("elite_vet_sale.winvet_master", "0")
        cls.supplier = cls.env["res.partner"].create({"name": "Dodavatel Příjmu Test s.r.o.", "is_company": True})
        Product = cls.env["product.product"]
        common = {"type": "consu", "is_storable": True, "tracking": "lot", "use_expiration_date": True}
        cls.product_a = Product.create(dict(common, name="Lék A příjem", default_code="PRA",
                                            barcode=GTIN_A[1:], standard_price=80.0,
                                            taxes_id=[(6, 0, cls.tax12.ids)]))
        cls.product_b = Product.create(dict(common, name="Krmivo B příjem", default_code="PRB",
                                            standard_price=40.0, taxes_id=[(6, 0, cls.tax21.ids)]))
        cls.stock = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1).lot_stock_id

    def receipt(self, user=None):
        return self.Receipt.with_user(user or self.nurse)

    # scan -----------------------------------------------------------------
    def test_scan_gs1_of_a_known_gtin(self):
        res = self.receipt().scan("]d201" + GTIN_A + "17270331" + "10LOT-A1")
        self.assertTrue(res["known"])
        self.assertEqual(res["product"]["id"], self.product_a.id)
        self.assertEqual(res["product"]["name"], "Lék A příjem")
        self.assertEqual(res["product"]["code"], "PRA")
        self.assertEqual(res["product"]["tracking"], "lot")
        self.assertEqual(res["lot"], "LOT-A1")
        self.assertEqual(res["expiry"], "2027-03-31")
        self.assertEqual(res["suggested_cost"], 80.0)
        self.assertEqual(res["vat_rate"], 12.0)

    def test_scan_plain_ean_prefills_lot_from_the_newest_lot(self):
        Lot = self.env["stock.lot"]
        Lot.create({"name": "OLD", "product_id": self.product_a.id, "expiration_date": datetime(2026, 12, 31, 12)})
        Lot.create({"name": "NEW", "product_id": self.product_a.id, "expiration_date": datetime(2027, 6, 30, 12)})
        res = self.receipt().scan(GTIN_A[1:])
        self.assertTrue(res["known"])
        self.assertEqual(res["product"]["id"], self.product_a.id)
        self.assertEqual(res["lot"], "NEW")
        self.assertEqual(res["expiry"], "2027-06-30")
        # the 14-digit form of the barcode is found too
        self.assertEqual(self.receipt().scan(GTIN_A)["product"]["id"], self.product_a.id)

    def test_unknown_code_then_assign_code(self):
        code = "0108595009999999" + "10L-B" + GS + "17280115"
        res = self.receipt().scan(code)
        self.assertFalse(res["known"])
        self.assertIsNone(res["product"])
        self.assertEqual(res["lot"], "L-B")
        self.assertEqual(res["expiry"], "2028-01-15")
        assigned = self.receipt().assign_code(code, self.product_b.id)
        self.assertTrue(assigned["known"])
        self.assertEqual(assigned["product"]["id"], self.product_b.id)
        self.assertEqual(assigned["lot"], "L-B")
        # the GTIN is stored, not the whole string with the lot -> another lot is known as well
        stored = self.env["elite.vet.product.code"].search([("product_id", "=", self.product_b.id)])
        self.assertEqual(stored.mapped("code"), ["08595009999999"])
        again = self.receipt().scan("(01)08595009999999(10)L-C(17)280229")
        self.assertTrue(again["known"])
        self.assertEqual(again["product"]["id"], self.product_b.id)
        self.assertEqual(again["vat_rate"], 21.0)
        # plain code: stored as is
        self.receipt().assign_code("SUPPLIER-77", self.product_a.id)
        self.assertEqual(self.receipt().scan("SUPPLIER-77")["product"]["id"], self.product_a.id)

    # validate -------------------------------------------------------------
    def test_validate_two_lines(self):
        res = self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_a.id, "lot": "RA-1", "expiry": "2027-03-31", "quantity": 2,
             "unit_cost": 100.0},
            {"product_id": self.product_b.id, "lot": "RB-1", "expiry": "2026-12-15", "quantity": 1,
             "unit_cost": 50.0},
        ], "DL-2026-001")
        picking = self.env["stock.picking"].browse(res["picking_id"])
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.picking_type_id.code, "incoming")
        self.assertEqual(picking.partner_id, self.supplier)
        self.assertEqual(picking.origin, "DL-2026-001")
        quant_a = self.env["stock.quant"].search([("product_id", "=", self.product_a.id),
                                                  ("location_id", "=", self.stock.id)])
        self.assertEqual(quant_a.lot_id.name, "RA-1")
        self.assertEqual(quant_a.quantity, 2)
        self.assertEqual(quant_a.lot_id.expiration_date.date().isoformat(), "2027-03-31")
        quant_b = self.env["stock.quant"].search([("product_id", "=", self.product_b.id),
                                                  ("location_id", "=", self.stock.id)])
        self.assertEqual((quant_b.lot_id.name, quant_b.quantity), ("RB-1", 1))
        self.assertEqual(self.product_a.standard_price, 100.0)
        self.assertEqual(self.product_b.standard_price, 50.0)
        expense = self.env["elite.vet.expense"].browse(res["expense_id"])
        self.assertEqual(expense.picking_id, picking)
        self.assertEqual(expense.supplier_id, self.supplier)
        self.assertEqual(expense.category_id, self.env.ref("elite_vet_winvet.expense_category_drugs"))
        self.assertAlmostEqual(expense.amount, 2 * 100 * 1.12 + 50 * 1.21)   # 224 + 60.5
        self.assertEqual(expense.vat_rate, "12")                             # the larger part
        self.assertEqual(expense.document_number, "DL-2026-001")
        self.assertTrue(expense.name.startswith("Příjem zboží Dodavatel Příjmu Test s.r.o."))

    def test_validate_existing_lot_gets_expiry_and_same_lot_lines_add_up(self):
        lot = self.env["stock.lot"].create({"name": "RA-2", "product_id": self.product_a.id})
        res = self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_a.id, "lot": "RA-2", "expiry": "2027-01-31", "quantity": 1, "unit_cost": 90},
            {"product_id": self.product_a.id, "lot": "RA-2", "expiry": "2027-01-31", "quantity": 3, "unit_cost": 90},
        ], None)
        self.assertEqual(lot.expiration_date.date().isoformat(), "2027-01-31")
        self.assertEqual(self.env["stock.lot"].search_count([("product_id", "=", self.product_a.id),
                                                             ("name", "=", "RA-2")]), 1)
        self.assertEqual(lot.product_qty, 4)
        expense = self.env["elite.vet.expense"].browse(res["expense_id"])
        self.assertFalse(expense.document_number)

    def test_validate_requires_lot_supplier_and_lines(self):
        with self.assertRaises(UserError):
            self.receipt().validate(self.supplier.id, [], None)
        with self.assertRaises(UserError):
            self.receipt().validate(False, [{"product_id": self.product_b.id, "lot": "X", "expiry": None,
                                              "quantity": 1, "unit_cost": 1}], None)
        with self.assertRaises(UserError):
            self.receipt().validate(self.supplier.id, [{"product_id": self.product_b.id, "lot": "", "expiry": None,
                                                        "quantity": 1, "unit_cost": 1}], None)

    def test_reception_has_no_access(self):
        with self.assertRaises(AccessError):
            self.receipt(self.reception).scan(GTIN_A)
        with self.assertRaises(AccessError):
            self.receipt(self.reception).validate(self.supplier.id, [
                {"product_id": self.product_b.id, "lot": "X", "expiry": None, "quantity": 1, "unit_cost": 1}], None)

    # suppliers ------------------------------------------------------------
    def test_suppliers_recent_first(self):
        other = self.env["res.partner"].create({"name": "Vrstvový Dodavatel Test s.r.o.", "is_company": True})
        self.env["elite.vet.winvet.stock.layer"].create({"winvet_ref": 99887766, "supplier": other.name.upper()})
        self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_b.id, "lot": "RB-9", "expiry": None, "quantity": 1, "unit_cost": 10}], None)
        names = [s["name"] for s in self.receipt().suppliers("")]
        self.assertEqual(names[0], self.supplier.name)
        self.assertIn(other.name, names)
        found = self.receipt().suppliers("vrstvový dod")
        self.assertEqual([s["id"] for s in found], [other.id])
        created = self.receipt().create_supplier("  Nový Dodavatel Test  ")
        partner = self.env["res.partner"].browse(created["id"])
        self.assertEqual((partner.name, partner.is_company), ("Nový Dodavatel Test", True))

    def test_search_products(self):
        found = self.receipt().search_products("příjem")
        ids = [p["id"] for p in found]
        self.assertIn(self.product_a.id, ids)
        self.assertIn(self.product_b.id, ids)
        self.assertEqual([p["id"] for p in self.receipt().search_products("PRB")], [self.product_b.id])

    # fix round 1 ------------------------------------------------------------
    def test_free_goods_keep_the_purchase_price(self):
        self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_a.id, "lot": "PAID", "expiry": None, "quantity": 2, "unit_cost": 100},
            {"product_id": self.product_a.id, "lot": "FREE", "expiry": None, "quantity": 1, "unit_cost": 0},
        ], None)
        self.assertEqual(self.product_a.standard_price, 100.0)
        # two lots of one product in one receipt: both stocked, no backorder
        picking = self.env["stock.picking"].search([("partner_id", "=", self.supplier.id)], order="id desc", limit=1)
        self.assertEqual(picking.state, "done")
        self.assertFalse(self.env["stock.picking"].search_count([("backorder_id", "=", picking.id)]))
        self.assertEqual(sorted((ml.lot_id.name, ml.quantity) for ml in picking.move_line_ids),
                         [("FREE", 1.0), ("PAID", 2.0)])
        # only free goods: the price stays as it was
        self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_b.id, "lot": "FREE-B", "expiry": None, "quantity": 1, "unit_cost": 0}], None)
        self.assertEqual(self.product_b.standard_price, 40.0)

    def test_trial_run_stocks_in_without_expense(self):
        self.env["ir.config_parameter"].sudo().set_param("elite_vet_sale.winvet_master", "1")
        self.assertTrue(self.receipt().init_data()["winvet_master"])
        expenses = self.env["elite.vet.expense"].search_count([])
        res = self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_b.id, "lot": "TR-1", "expiry": None, "quantity": 3, "unit_cost": 20}], None)
        self.assertEqual(self.env["stock.picking"].browse(res["picking_id"]).state, "done")
        self.assertFalse(res["expense_id"])
        self.assertTrue(res["winvet_master"])
        self.assertEqual(self.env["elite.vet.expense"].search_count([]), expenses)

    def test_odoo_master_flag_and_expense(self):
        self.assertFalse(self.receipt().init_data()["winvet_master"])
        res = self.receipt().validate(self.supplier.id, [
            {"product_id": self.product_b.id, "lot": "OM-1", "expiry": None, "quantity": 1, "unit_cost": 20}], None)
        self.assertTrue(res["expense_id"])
        self.assertFalse(res["winvet_master"])

    def test_expired_flag(self):
        self.assertTrue(self.receipt().scan("01" + GTIN_A + "17200131" + "10OLD")["expired"])
        self.assertFalse(self.receipt().scan("01" + GTIN_A + "17991231" + "10NEW")["expired"])
