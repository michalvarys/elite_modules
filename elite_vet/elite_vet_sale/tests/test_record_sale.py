from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestRecordSale(SaleCase):
    """Finished visit record -> quotation for the till (spec section 4)."""

    # helpers --------------------------------------------------------------
    def nurse_api(self):
        return self.as_user(self.nurse)

    def doctor_api(self):
        return self.as_user(self.doctor_user)

    def new_record(self, free=True):
        api = self.nurse_api()
        data = api.open_today_record(self.pet.id, force_new=True)
        data = api.add_item(data["id"], self.exam.id)
        if free:
            data = api.add_free_line(data["id"], "Stříhání drápků", 100.0)
        return self.Record.browse(data["id"])

    def done(self, record):
        return self.nurse_api().mark_done(record.id)

    # tests ----------------------------------------------------------------
    def test_done_creates_quotation(self):
        record = self.new_record()
        data = self.done(record)
        order = record.sale_order_id
        self.assertTrue(order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.owner)
        self.assertIn(self.pet.name, order.client_order_ref)
        day = record.date
        self.assertEqual(order.client_order_ref, "%s – %d. %d. %d" % (self.pet.name, day.day, day.month, day.year))
        self.assertEqual(order.clinical_record_id, record)
        self.assertEqual(order.pet_id, self.pet)
        self.assertEqual(order.doctor_id, record.doctor_id)
        self.assertEqual(len(order.order_line), 2)
        exam_line, free_line = order.order_line.sorted("sequence")
        self.assertEqual(exam_line.product_id, self.exam.product_id)
        self.assertAlmostEqual(exam_line.price_total, 450.0, places=2)
        self.assertEqual(free_line.product_id, self.setup.free_product())
        self.assertEqual(free_line.name, "Stříhání drápků")
        self.assertAlmostEqual(free_line.price_total, 100.0, places=2)
        self.assertAlmostEqual(order.amount_total, 550.0, places=2)
        self.assertEqual(record.payment_state, "waiting")
        self.assertEqual(data["payment_state"], "waiting")
        self.assertEqual(data["payment_state_label"], "Čeká na platbu")
        self.assertEqual(data["sale_order_name"], order.name)

    def test_record_without_lines(self):
        data = self.nurse_api().open_today_record(self.pet.id, force_new=True)
        data = self.nurse_api().mark_done(data["id"])
        record = self.Record.browse(data["id"])
        self.assertEqual(record.state, "done")
        self.assertFalse(record.sale_order_id)
        self.assertEqual(record.payment_state, "none")
        self.assertEqual(data["payment_state_label"], "Bez účtu")
        self.assertIsNone(data["sale_order_name"])

    def test_reopen_and_done_again_rewrites_quotation(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        self.doctor_api().reopen_record(record.id)
        exam_line = record.line_ids.filtered(lambda l: l.item_id == self.exam)
        self.nurse_api().update_line(exam_line.id, {"quantity": 2})
        self.done(record)
        self.assertEqual(record.sale_order_id, order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(len(order.order_line), 2)
        self.assertAlmostEqual(order.amount_total, 1000.0, places=2)
        self.assertEqual(order.order_line.filtered(lambda l: l.product_id == self.exam.product_id).product_uom_qty, 2)

    def test_doctor_price_change_wins(self):
        record = self.new_record(free=False)
        self.nurse_api().update_line(record.line_ids.id, {"price_unit": 399.0})
        self.done(record)
        self.assertAlmostEqual(record.sale_order_id.amount_total, 399.0, places=2)

    def test_lines_removed_drops_quotation(self):
        record = self.new_record(free=False)
        self.done(record)
        self.doctor_api().reopen_record(record.id)
        self.nurse_api().remove_line(record.line_ids.id)
        data = self.done(record)
        self.assertFalse(record.sale_order_id)
        self.assertEqual(data["payment_state"], "none")

    def test_archived_item_keeps_product(self):
        record = self.new_record(free=False)
        product = self.exam.product_id
        self.exam.write({"active": False})
        self.assertFalse(product.active)
        self.done(record)
        self.assertEqual(record.sale_order_id.order_line.product_id, product)

    def test_paid_record_cannot_be_reopened(self):
        record = self.new_record()
        self.done(record)
        pos_order = self.settle(record.sale_order_id)
        self.assertIn(pos_order.state, ("paid", "done", "invoiced"))
        self.assertEqual(record.payment_state, "paid")
        self.assertEqual(self.nurse_api().get_record(record.id)["payment_state_label"], "Zaplaceno")
        with self.assertRaisesRegex(UserError, "vratku"):
            self.doctor_api().reopen_record(record.id)
        self.assertEqual(record.state, "done")

    def test_cancel_record_cancels_quotation(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        record.with_user(self.nurse).action_cancel()
        self.assertEqual(order.state, "cancel")
        self.assertEqual(record.payment_state, "cancelled")
        self.assertEqual(self.nurse_api().get_record(record.id)["payment_state_label"], "Zrušeno")

    def test_card_data_has_payment_state(self):
        record = self.new_record()
        self.done(record)
        card = self.as_user(self.reception).card_data(self.pet.id)
        self.assertEqual(card["today_record"]["payment_state"], "waiting")
        data = self.as_user(self.reception).get_record(record.id)
        self.assertEqual(data["payment_state"], "waiting")
        self.assertEqual(data["sale_order_name"], record.sale_order_id.name)
