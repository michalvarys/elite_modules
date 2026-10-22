from datetime import datetime

from odoo.tests import tagged

from odoo.addons.elite_vet_reservation.models.live import PRECOMMIT_KEY

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestPosSettlement(SaleCase):
    """Settling a visit bill in the Recepce till (spec section 5)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id

    def product(self, name, storable=True):
        vals = {"name": name, "type": "consu", "list_price": 121.0, "available_in_pos": True,
                "taxes_id": [(6, 0, self.tax21.ids)]}
        if storable:
            vals.update({"is_storable": True, "tracking": "lot", "use_expiration_date": True})
        return self.env["product.product"].create(vals)

    def lot(self, product, name, expiry, qty):
        lot = self.env["stock.lot"].create({
            "name": name, "product_id": product.id, "expiration_date": expiry})
        self.env["stock.quant"]._update_available_quantity(product, self.stock_location, qty, lot_id=lot)
        return lot

    def quotation(self, product, qty):
        return self.env["sale.order"].create({
            "partner_id": self.owner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": qty, "price_unit": 121.0})]})

    def test_fefo_takes_earliest_lot_first(self):
        product = self.product("FEFO vakcína")
        early = self.lot(product, "E", datetime(2026, 11, 30, 12, 0), 2)
        late = self.lot(product, "L", datetime(2027, 5, 31, 12, 0), 5)
        pos_order = self.settle(self.quotation(product, 3))
        picking = pos_order.picking_ids
        self.assertEqual(picking.state, "done")
        used = {ml.lot_id: ml.quantity for ml in picking.move_line_ids}
        self.assertEqual(used, {early: 2.0, late: 1.0})

    def test_invoice_tax_split(self):
        product = self.product("Fakturovaná věc", storable=False)
        pos_order = self.settle(self.quotation(product, 1), invoice=True)
        move = pos_order.account_move
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.amount_untaxed, 100.0)
        self.assertEqual(move.amount_tax, 21.0)
        tax_line = move.line_ids.filtered(lambda l: l.tax_line_id)
        self.assertEqual(tax_line.tax_line_id, self.tax21)
        self.assertEqual(tax_line.balance, -21.0)

    def test_product_without_stock_settles_negative(self):
        product = self.product("Bez skladu")
        pos_order = self.settle(self.quotation(product, 1))
        self.assertEqual(pos_order.state, "paid")
        quant = self.env["stock.quant"].search([("product_id", "=", product.id),
                                                ("location_id", "child_of", self.stock_location.id)])
        self.assertEqual(sum(quant.mapped("quantity")), -1.0)

    def test_session_close_with_cash_balances(self):
        product = self.product("Hotovost", storable=False)
        pos_order = self.settle(self.quotation(product, 1), method="cash")
        session = pos_order.session_id
        self.assertEqual(session.state, "opened")
        counted = session.cash_register_balance_start + 121.0
        session.post_closing_cash_details(counted)
        result = session.close_session_from_ui()
        self.assertTrue(result.get("successful"), result)
        self.assertEqual(session.state, "closed")

    def test_settling_a_record_bill_notifies_board(self):
        api = self.as_user(self.nurse)
        data = api.open_today_record(self.pet.id, force_new=True)
        data = api.add_free_line(data["id"], "Stříhání drápků", 100.0)
        api.mark_done(data["id"])
        record = self.Record.browse(data["id"])
        self.env.cr.precommit.data.pop(PRECOMMIT_KEY, None)
        self.settle(record.sale_order_id)
        self.assertIn(PRECOMMIT_KEY, self.env.cr.precommit.data)
        self.assertEqual(record.payment_state, "paid")

    def test_settling_a_bill_without_record_does_not_notify(self):
        product = self.product("Bez karty", storable=False)
        self.env.cr.precommit.data.pop(PRECOMMIT_KEY, None)
        self.settle(self.quotation(product, 1))
        self.assertNotIn(PRECOMMIT_KEY, self.env.cr.precommit.data)
