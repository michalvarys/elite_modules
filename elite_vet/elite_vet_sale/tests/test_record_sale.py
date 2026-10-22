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

    # fix round 1 ------------------------------------------------------------
    def test_paid_while_reopened_done_keeps_quotation(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        self.doctor_api().reopen_record(record.id)
        self.settle(order)
        lines_before = order.order_line
        exam_line = record.line_ids.filtered(lambda l: l.item_id == self.exam)
        exam_line.with_user(self.nurse).quantity = 3
        data = self.done(record)
        self.assertEqual(record.state, "done")
        self.assertEqual(data["payment_state"], "paid")
        self.assertEqual(record.sale_order_id, order)
        self.assertEqual(order.order_line, lines_before)
        self.assertAlmostEqual(order.amount_total, 550.0, places=2)
        self.assertIn("Účet už byl zaplacen v pokladně", record.message_ids[:1].body)

    def test_confirmed_unpaid_quotation_rewritten(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.doctor_api().reopen_record(record.id)
        self.nurse_api().remove_line(record.line_ids.filtered(lambda l: not l.item_id).id)
        self.done(record)
        self.assertEqual(record.sale_order_id, order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(len(order.order_line), 1)
        self.assertAlmostEqual(order.amount_total, 450.0, places=2)
        self.assertEqual(record.payment_state, "waiting")

    def test_partial_settlement_is_partial(self):
        # Simplest realistic partial payment: reception settles only one line of the quotation.
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        exam_line = order.order_line.filtered(lambda l: l.product_id == self.exam.product_id)
        pos_order = self.settle(order, order_lines=exam_line)
        self.assertIn(pos_order.state, ("paid", "done", "invoiced"))
        self.assertEqual(record.payment_state, "partial")
        self.assertEqual(self.nurse_api().get_record(record.id)["payment_state_label"], "Částečně zaplaceno")
        with self.assertRaisesRegex(UserError, "záloha"):
            self.doctor_api().reopen_record(record.id)
        with self.assertRaisesRegex(UserError, "záloha"):
            record.with_user(self.nurse).action_cancel()
        self.settle(order, order_lines=order.order_line - exam_line)
        self.assertEqual(record.payment_state, "paid")

    def test_cancel_paid_record_blocked(self):
        record = self.new_record()
        self.done(record)
        self.settle(record.sale_order_id, method="cash")
        with self.assertRaisesRegex(UserError, "vratku"):
            record.with_user(self.nurse).action_cancel()
        self.assertEqual(record.state, "done")

    def test_cancelled_quotation_back_to_draft(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        order._action_cancel()
        self.assertEqual(record.payment_state, "cancelled")
        self.doctor_api().reopen_record(record.id)
        self.done(record)
        self.assertEqual(record.sale_order_id, order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(record.payment_state, "waiting")

    def test_settle_with_invoice(self):
        record = self.new_record()
        self.done(record)
        pos_order = self.settle(record.sale_order_id, method="transfer", invoice=True)
        self.assertEqual(pos_order.state, "invoiced")
        self.assertTrue(pos_order.account_move)
        self.assertEqual(pos_order.account_move.state, "posted")
        self.assertEqual(pos_order.account_move.partner_id, self.owner)
        self.assertEqual(record.payment_state, "paid")

    # final review (Ruling R15) --------------------------------------------
    def test_refinish_updates_lines_in_place(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        exam_sol = order.order_line.filtered(lambda l: l.product_id == self.exam.product_id)
        free_sol = order.order_line - exam_sol
        self.doctor_api().reopen_record(record.id)
        exam_line = record.line_ids.filtered(lambda l: l.item_id == self.exam)
        self.nurse_api().update_line(exam_line.id, {"quantity": 2})
        self.nurse_api().add_free_line(record.id, "Výplach uší", 80.0)
        self.done(record)
        self.assertEqual(len(order.order_line), 3)
        self.assertIn(exam_sol, order.order_line)
        self.assertIn(free_sol, order.order_line)
        self.assertEqual(exam_sol.product_uom_qty, 2)
        self.assertEqual(free_sol.name, "Stříhání drápků")
        self.assertAlmostEqual(order.amount_total, 1080.0, places=2)
        # removing a line drops only its quotation line
        self.doctor_api().reopen_record(record.id)
        self.nurse_api().remove_line(record.line_ids.filtered(lambda l: l.name == "Stříhání drápků").id)
        self.done(record)
        self.assertFalse(free_sol.exists())
        self.assertIn(exam_sol, order.order_line)
        self.assertEqual(len(order.order_line), 2)
        self.assertAlmostEqual(order.amount_total, 980.0, places=2)

    def test_refinish_refused_while_till_holds_the_bill(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        pos_order = self.settle(order, draft=True)
        self.assertEqual(pos_order.state, "draft")
        self.assertEqual(record.payment_state, "waiting")
        self.doctor_api().reopen_record(record.id)
        with self.assertRaisesRegex(UserError, "Recepce účet právě vyřizuje v pokladně"):
            self.done(record)

    def test_payment_detected_by_quotation_link_only(self):
        record = self.new_record()
        self.done(record)
        order = record.sale_order_id
        pos_order = self.settle(order, link_lines=False)
        self.assertIn(pos_order.state, ("paid", "done", "invoiced"))
        self.assertFalse(order.order_line.pos_order_line_ids)
        self.assertTrue(record._has_pos_payment())
        self.assertEqual(record.payment_state, "paid")
        with self.assertRaisesRegex(UserError, "vratku"):
            self.doctor_api().reopen_record(record.id)
