from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.elite_eet.eet import fields as eet_fields
from odoo.addons.elite_eet.eet import paths
from odoo.addons.elite_eet.tests.common import p12_b64
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosEet(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.beer = cls.create_product("Pivo", cls.categ_basic, 250)
        cls.voucher = cls.create_product("VOUCHER 500", cls.categ_basic, 500)
        cls.voucher.product_tmpl_id.eet_prepaid_voucher = True
        cls.internal_pm = cls.env["pos.payment.method"].create({
            "name": "Interní",
            "journal_id": cls.company_data["default_journal_bank"].id,
            "receivable_account_id": cls.pos_receivable_bank.id,
            "outstanding_account_id": cls.outstanding_bank.id,
            "eet_register": False,
        })
        cls.redeem_pm = cls.env["pos.payment.method"].create({
            "name": "Čerpání voucheru",
            "journal_id": cls.company_data["default_journal_bank"].id,
            "receivable_account_id": cls.pos_receivable_bank.id,
            "outstanding_account_id": cls.outstanding_bank.id,
            "eet_voucher_redemption": True,
        })
        cls.config.write({"payment_method_ids": [(4, cls.internal_pm.id), (4, cls.redeem_pm.id)]})
        cls.device = cls.env["elite.eet.device"].create({
            "pos_config_id": cls.config.id,
            "eic": "CZ00000019",
            "id_jednotky": "303",
            "start_datetime": fields.Datetime.now() - timedelta(days=1),
            "certificate_file": p12_b64("CZ00000019"),
            "certificate_password": paths.TEST_P12_PASSWORD.decode(),
            "active_eet": True,
        })

    def setUp(self):
        super().setUp()
        self.open_new_session()
        self.sent = []
        sale_model = type(self.env["elite.eet.sale"])
        patcher = patch.object(
            sale_model, "_eet_send_after_commit",
            lambda sale, first_send=None: self.sent.append((sale, first_send)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def sync(self, lines, payments, amount_return=0, date_order=None, **extra):
        data = self.create_ui_order_data(lines, payments=payments)
        data["amount_return"] = amount_return
        if date_order:
            data["date_order"] = fields.Datetime.to_string(date_order)
        data.update(extra)
        result = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(result["pos.order"][0]["id"])

    def test_paid_order_creates_sale(self):
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)])
        sale = order.eet_sale_id
        self.assertTrue(sale)
        self.assertEqual(sale.celk_trzba, 250)
        self.assertEqual(sale.device_id, self.device)
        self.assertEqual(sale.dat_trzby, order.date_order)
        self.assertEqual(sale.source_ref, order.name)
        self.assertTrue(eet_fields.TEXT25_RE.fullmatch(sale.porad_cis))
        self.assertFalse(sale.urceno_cerp_zuct)
        self.assertEqual(self.sent, [(sale, True)])
        self.assertEqual(order.eet_state, "pending")

    def test_change_line(self):
        order = self.sync([(self.beer, 1)], [(self.cash_pm1, 1000)], amount_return=750)
        self.assertTrue(order.payment_ids.filtered("is_change"))
        self.assertEqual(order.eet_sale_id.celk_trzba, 250)

    def test_internal_method_no_sale(self):
        order = self.sync([(self.beer, 1)], [(self.internal_pm, 250)])
        self.assertEqual(order.state, "paid")
        self.assertFalse(order.eet_sale_id)
        self.assertFalse(self.sent)

    def test_mixed_payment(self):
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 100), (self.internal_pm, 150)])
        self.assertEqual(order.eet_sale_id.celk_trzba, 100)

    def test_refund_negative(self):
        order = self.sync([(self.beer, 1)], [(self.cash_pm1, 250)])
        refund_data = self.create_ui_order_data([(self.beer, -1)], payments=[(self.cash_pm1, -250)])
        refund_data["lines"][0][2]["refunded_orderline_id"] = order.lines[0].id
        result = self.env["pos.order"].sync_from_ui([refund_data])
        refund = self.env["pos.order"].browse(result["pos.order"][0]["id"])
        self.assertEqual(refund.eet_sale_id.celk_trzba, -250)
        self.assertNotEqual(refund.eet_sale_id.porad_cis, order.eet_sale_id.porad_cis)

    def test_voucher_sale_and_redemption(self):
        sold = self.sync([(self.voucher, 1)], [(self.cash_pm1, 500)])
        self.assertEqual(sold.eet_sale_id.urceno_cerp_zuct, 500)
        self.assertEqual(sold.eet_sale_id.celk_trzba, 500)
        used = self.sync([(self.beer, 2)], [(self.redeem_pm, 300), (self.cash_pm1, 200)])
        self.assertEqual(used.eet_sale_id.cerp_zuct, 300)
        self.assertEqual(used.eet_sale_id.celk_trzba, 500)

    def test_late_sync_not_first(self):
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)],
                          date_order=fields.Datetime.now() - timedelta(minutes=10))
        self.assertEqual(self.sent, [(order.eet_sale_id, False)])

    def test_before_start_datetime_no_sale(self):
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)],
                          date_order=self.device.start_datetime - timedelta(minutes=1))
        self.assertFalse(order.eet_sale_id)

    def test_disabled_device_no_sale(self):
        self.device.active_eet = False
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)])
        self.assertFalse(order.eet_sale_id)

    def test_config_without_device_unchanged(self):
        self.device.pos_config_id = False
        order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)])
        self.assertEqual(order.state, "paid")
        self.assertFalse(order.eet_sale_id)
        self.assertFalse(self.sent)

    def test_backoffice_order_no_sale(self):
        data = self.create_ui_order_data([(self.beer, 1)], payments=[(self.bank_pm1, 250)])
        data.pop("uuid")
        payments = data.pop("payment_ids")
        data["lines"] = [(0, 0, {k: v for k, v in line[2].items() if k != "id"}) for line in data["lines"]]
        order = self.env["pos.order"].create({k: v for k, v in data.items() if k not in ("name",)})
        for _cmd, _id, vals in payments:
            order.add_payment({**vals, "pos_order_id": order.id, "name": "x"})
        order.action_pos_order_paid()
        self.assertEqual(order.state, "paid")
        self.assertFalse(order.eet_sale_id)

    def test_resync_creates_one_sale(self):
        data = self.create_ui_order_data([(self.beer, 1)], payments=[(self.bank_pm1, 250)])
        self.env["pos.order"].sync_from_ui([dict(data)])
        self.env["pos.order"].sync_from_ui([dict(data)])
        orders = self.env["pos.order"].search([("uuid", "=", data["uuid"])])
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(orders.eet_sale_ids), 1)
        self.assertEqual(len(self.sent), 1)

    def test_id_pokl_default_sanitized(self):
        config = self.config.copy({"name": "Pokladna Bar č. 1"})
        device = self.env["elite.eet.device"].create({"pos_config_id": config.id})
        self.assertEqual(device.id_pokl, "Pokladna Bar c. 1")
        self.assertEqual(device.name, "Pokladna Bar č. 1")
        self.assertEqual(config.eet_device_id, device)

    def test_payment_method_defaults(self):
        self.assertTrue(self.bank_pm1.eet_register)
        self.assertTrue(self.cash_pm1.eet_register)
        self.assertFalse(self.pay_later_pm.eet_register)

    # --- final review fixes -------------------------------------------------

    def refund(self, order, qty, amount):
        data = self.create_ui_order_data([(self.beer, qty)], payments=[(self.cash_pm1, amount)])
        data["lines"][0][2]["refunded_orderline_id"] = order.lines[0].id
        result = self.env["pos.order"].sync_from_ui([data])
        return self.env["pos.order"].browse(result["pos.order"][0]["id"])

    def test_double_refund(self):
        order = self.sync([(self.beer, 2)], [(self.cash_pm1, 500)])
        first = self.refund(order, -1, -250)
        second = self.refund(order, -1, -250)
        self.assertEqual(first.name, second.name)  # Odoo names every refund "<order> REFUND"
        self.assertTrue(first.eet_sale_id and second.eet_sale_id)
        self.assertNotEqual(first.eet_sale_id.porad_cis, second.eet_sale_id.porad_cis)
        for sale in (first | second).eet_sale_ids:
            self.assertTrue(eet_fields.TEXT25_RE.fullmatch(sale.porad_cis), sale.porad_cis)

    def test_long_config_name(self):
        # Order names are "<till name at creation>/0001"; a long till name used to lose the
        # sequence number when truncated to 25 characters, so every order collided.
        orders = [self.sync([(self.beer, 1)], [(self.bank_pm1, 250)]) for _i in range(3)]
        numbers = []
        for i, order in enumerate(orders, 1):
            order.name = "Elite Trafika Pokladna u vchodu/%04d" % i
            numbers.append(order._eet_porad_cis())
        self.assertEqual(len(set(numbers)), 3, numbers)
        for number in numbers:
            self.assertTrue(eet_fields.TEXT25_RE.fullmatch(number), number)

    def test_eet_failure_never_blocks_sync(self):
        order_model = type(self.env["pos.order"])

        def broken(order):
            raise RuntimeError("EET bug")

        with patch.object(order_model, "_eet_create_sale", broken):
            order = self.sync([(self.beer, 1)], [(self.bank_pm1, 250)])
        self.assertEqual(order.state, "paid")
        self.assertFalse(order.eet_sale_id)
        self.assertTrue(self.device.activity_ids.filtered(lambda a: "nevznikla" in (a.summary or "")))
