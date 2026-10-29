"""Task 33: deposits from WinVet (contract v5) and the cash closure PDF ("Uzávěrka")."""
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..models.cash_closure import money, money_short, period_label, preset_dates
from .common import WinvetCase

# A period no real (or ev_test) data can fall into.
Y = 2031


def d(day, month=3):
    return "%d-%02d-%02d" % (Y, month, day)


@tagged("post_install", "-at_install")
class TestDeposits(WinvetCase):

    def setUp(self):
        super().setUp()
        self.push("owners", [self.owner(1), self.owner(2, name="Testová Eva 2")])

    def deposit(self, n, owner_n, amount, **over):
        rec = {"id": self.ref(n), "owner_id": self.ref(owner_n), "date": d(2), "amount": amount, "sign": 1,
               "method": "PLATK", "document_id": None, "used": 0, "refunded": 0, "refunded_date": None,
               "balance": amount, "note": None, "state": None}
        rec.update(over)
        return rec

    def test_entities_registered_and_labels(self):
        entities = self.sync._winvet_entities()
        self.assertIn("deposits", entities)
        self.assertEqual(entities.index("deposit_uses"), entities.index("deposits") + 1)
        self.assertEqual(self.sync._winvet_entity_labels()["deposits"], "Zálohy")

    def test_deposits_and_uses_sync(self):
        # a use arriving before its deposit is stored and linked by the fixup
        self.push("deposit_uses", [{"id": self.ref(30), "deposit_id": self.ref(20), "document_id": self.ref(50),
                                    "document_number": "2031000001", "date": d(5), "amount": 1500, "state": "I"}],
                  mode="full", run_id="u1")
        use = self.find("elite.vet.deposit.use", 30)
        self.assertFalse(use.deposit_id)
        res = self.push("deposits", [
            self.deposit(20, 1, 2000, used=1500, balance=500),
            self.deposit(21, 2, 1000, method="HOT", refunded=1000, refunded_date=d(4), balance=0, state="E"),
        ])
        self.assertEqual(res["created"], 2)
        dep, refunded = self.find("elite.vet.deposit", 20), self.find("elite.vet.deposit", 21)
        partner = self.find("res.partner", 1)
        self.assertEqual(dep.partner_id, partner)
        self.assertEqual((dep.method, dep.amount, dep.used, dep.balance), ("card", 2000, 1500, 500))
        self.assertFalse(dep.refund_method)
        self.assertEqual((refunded.method, refunded.refund_method, str(refunded.refunded_date)),
                         ("cash", "cash", d(4)))
        self.assertEqual(use.deposit_id, dep)
        self.assertEqual(use.partner_id, partner)
        self.assertEqual(dep.use_count, 1)
        # the document arrives later and is linked too
        self.push("sale_documents", [{"id": self.ref(50), "type": "PODP", "number": "2031000001", "parent_id": None,
                                      "owner_id": self.ref(1), "date": d(5), "total": 1500, "paid": 1500,
                                      "from_deposit": 1500, "state": "U", "entered_by": None, "method": "PLATK"}])
        self.assertEqual(use.document_id, self.find("elite.vet.sale.document", 50))
        # partner balance (button, patient card, Kartotéka)
        self.assertEqual(partner.winvet_deposit_count, 1)
        self.assertEqual(partner.winvet_deposit_balance, 500)
        self.assertEqual(partner.winvet_deposit_balance_text, "500,00 Kč")
        self.assertFalse(self.find("res.partner", 2).winvet_deposit_balance_text, "zero balance -> no line")
        action = partner.action_view_winvet_deposits()
        self.assertEqual(action["res_model"], "elite.vet.deposit")
        self.assertEqual(action["domain"], [("partner_id", "=", partner.id)])
        # unchanged push writes nothing; a deletion removes the analytic row; a full run of uses reconciles
        self.assertEqual(self.push("deposits", [self.deposit(20, 1, 2000, used=1500, balance=500)])["updated"], 0)
        self.push("deposits", [], deleted=[self.ref(21)])
        self.assertFalse(self.find("elite.vet.deposit", 21))
        self.push("deposit_uses", [], mode="full", run_id="u2")
        self.assertFalse(self.find("elite.vet.deposit.use", 30))

    def test_bad_dates_and_old_bridge_documents(self):
        res = self.push("deposits", [self.deposit(22, 1, 300, date="0226-03-02")])
        self.assertFalse(self.find("elite.vet.deposit", 22).date)
        self.assertIn("neplatná data", self.env["elite.vet.winvet.status"].get_status().last_error or "")
        self.assertEqual(res["created"], 1)
        doc = {"id": self.ref(51), "type": "VRAT", "number": "V1", "parent_id": None, "owner_id": self.ref(1),
               "date": d(5), "total": 100, "paid": 100, "from_deposit": 0, "state": "U", "entered_by": None}
        self.push("sale_documents", [dict(doc, method="HOT")])
        vrat = self.find("elite.vet.sale.document", 51)
        self.assertEqual(vrat.recorded_method, "cash")
        # a bridge < 5.0 does not send "method": the stored value stays
        self.push("sale_documents", [dict(doc, total=120)])
        self.assertEqual((vrat.total, vrat.recorded_method), (120, "cash"))

    def test_owner_link_moves_deposits(self):
        """A WinVet owner linked to an existing web client takes its deposits along."""
        client = self.env["res.partner"].create({"name": "Webová Klientka", "email": "web.t44@example.invalid",
                                                 "is_vet_client": True})
        self.push("owners", [self.owner(3)])
        owner = self.find("res.partner", 3)
        self.push("deposits", [self.deposit(23, 3, 700)])
        self.sync._link_owner_to_client(owner, client)
        self.assertEqual(self.find("elite.vet.deposit", 23).partner_id, client)

    def test_rights(self):
        self.push("deposits", [self.deposit(24, 1, 700)])
        groups = [self.env.ref("base.group_user").id]
        outsider = self.env["res.users"].create({"name": "Outsider T44", "login": "outsider_t44",
                                                 "groups_id": [(6, 0, groups)]})
        reception = self.env["res.users"].create({
            "name": "Recepce T44", "login": "reception_t44",
            "groups_id": [(6, 0, groups + [self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        for user in (outsider, reception):
            with self.assertRaises(AccessError):
                self.env["elite.vet.deposit"].with_user(user).search([]).mapped("amount")
            with self.assertRaises(AccessError):
                self.env["elite.vet.cash.closure.wizard"].with_user(user).create({})
            with self.assertRaises(AccessError):
                self.env["elite.vet.cash.closure"].with_user(user).closure_data(d(1), d(31))
        # the quiet balance line works for reception (sudo), the records do not
        partner = self.find("res.partner", 1).with_user(reception)
        self.assertEqual(partner.winvet_deposit_balance_text, "700,00 Kč")


@tagged("post_install", "-at_install")
class TestCashClosure(WinvetCase):
    """Synthetic month: PODP / FAV / VRAT, payments in three methods, deposits (received, used, refunded),
    a money-unit line and item lines in every method."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.ref
        sync = cls.sync

        def push(entity, records, **kw):
            res = sync.push(dict({"entity": entity, "mode": "incremental", "records": records, "deleted": [],
                                  "batch": 1, "batches": 1, "run_id": "c"}, **kw))
            assert res.get("ok"), res

        push("items", [{"id": ref(1), "code": "VYS", "name": "Vyšetření", "classification": "service",
                        "stock_tracked": False, "tracked_drug": False, "unit": "ks", "barcode": None, "active": True},
                       {"id": ref(2), "code": "AMX", "name": "Amoxiclav", "classification": "product",
                        "stock_tracked": True, "tracked_drug": False, "unit": "tbl", "barcode": None, "active": True}])
        push("owners", [{"id": ref(n), "kind": "person", "name": "Klient T44 %s" % n, "first_name": None,
                         "last_name": None, "title": None, "street": None, "zip": None, "city": None, "country": None,
                         "company_reg": None, "vat": None, "note": None, "important_note": False, "active": True,
                         "created": None, "modified": None} for n in (1, 2, 3)])
        base = {"owner_id": ref(1), "from_deposit": 0, "state": "U", "entered_by": None, "parent_id": None}
        docs = [
            # account + receipt paid in cash (1 000) on the 2nd
            dict(base, id=ref(10), type="UM", number="U10", date=d(2), total=1000, paid=1000),
            dict(base, id=ref(11), type="PODP", number="P11", date=d(2), total=1000, paid=1000, parent_id=ref(10),
                 method="HOT"),
            # card 2 500, of which 500 from a deposit, on the 3rd
            dict(base, id=ref(12), type="UM", number="U12", date=d(3), total=2500, paid=2500, from_deposit=500),
            dict(base, id=ref(13), type="PODP", number="P13", date=d(3), total=2500, paid=2500, from_deposit=500,
                 parent_id=ref(12), method="PLATK"),
            # transfer 300 on the 3rd
            dict(base, id=ref(14), type="UM", number="U14", date=d(3), total=300, paid=300, owner_id=ref(2)),
            dict(base, id=ref(15), type="PODP", number="P15", date=d(3), total=300, paid=300, parent_id=ref(14),
                 owner_id=ref(2), method="PREV"),
            # unpaid receipt (a zero payment carries the chosen method) on the 4th
            dict(base, id=ref(16), type="UM", number="U16", date=d(4), total=884, paid=0, owner_id=ref(3)),
            dict(base, id=ref(17), type="PODP", number="P17", date=d(4), total=884, paid=0, parent_id=ref(16),
                 owner_id=ref(3)),
            # invoice, unpaid, on the 4th
            dict(base, id=ref(18), type="FAV", number="F18", date=d(4), total=609, paid=0, owner_id=ref(2)),
            # refund of 200 in cash on the 4th (VRAT, no payment rows)
            dict(base, id=ref(19), type="VRAT", number="V19", date=d(4), total=200, paid=200, parent_id=ref(11),
                 method="HOT"),
            # a VRAT nothing was paid out for: in sales, not in refunds
            dict(base, id=ref(20), type="VRAT", number="V20", date=d(4), total=50, paid=0, parent_id=ref(11)),
        ]
        push("sale_documents", docs)
        pay = {"owner_id": ref(1), "time": "10:00:00", "state": "U", "refunded_date": None, "from_deposit": 0}
        push("payments", [
            dict(pay, id=ref(30), document_id=ref(11), date=d(2), method="HOT", amount=1000),
            dict(pay, id=ref(31), document_id=ref(13), date=d(3), method="PLATK", amount=2500, from_deposit=500),
            dict(pay, id=ref(32), document_id=ref(15), date=d(3), method="PREV", amount=300, owner_id=ref(2)),
            dict(pay, id=ref(33), document_id=ref(17), date=d(4), method="HOT", amount=0, owner_id=ref(3)),
            # a direct sale (document not synced) paid by card, and a payment with another method
            dict(pay, id=ref(34), document_id=None, date=d(4), method="PLATK", amount=160),
            dict(pay, id=ref(35), document_id=None, date=d(4), method="DOB", amount=40),
        ])
        dep = {"sign": 1, "document_id": None, "note": None, "state": None, "refunded": 0, "refunded_date": None}
        push("deposits", [
            # received by card on the 1st, used 500 on the 3rd, the rest (1 500) still there
            dict(dep, id=ref(40), owner_id=ref(1), date=d(1), amount=2000, method="PLATK", used=1500, balance=500),
            # received in cash on the 2nd and refunded on the 4th
            dict(dep, id=ref(41), owner_id=ref(2), date=d(2), amount=1000, method="HOT", used=0, refunded=1000,
                 refunded_date=d(4), balance=0, state="E"),
        ])
        push("deposit_uses", [
            {"id": ref(45), "deposit_id": ref(40), "document_id": ref(13), "document_number": "P13", "date": d(3),
             "amount": 500, "state": "I"},
            # used again next month: not part of March
            {"id": ref(46), "deposit_id": ref(40), "document_id": None, "document_number": "X", "date": d(5, 4),
             "amount": 1000, "state": "I"},
        ], mode="full", run_id="c")
        line = {"visit_id": None, "quantity": 1, "unit": "ks", "vat_rate": 0, "entered_by": None,
                "item_code": None}
        push("sale_lines", [
            dict(line, id=ref(50), document_id=ref(10), item_id=ref(1), item_name="Vyšetření", unit_price=600,
                 amount=600, date=d(2), vat_rate=21),
            dict(line, id=ref(51), document_id=ref(10), item_id=ref(2), item_name="Amoxiclav", unit_price=400,
                 amount=400, date=d(2), quantity=2, unit="tbl", vat_rate=12),
            dict(line, id=ref(52), document_id=ref(12), item_id=ref(1), item_name="Vyšetření", unit_price=2500,
                 amount=2500, date=d(3)),
            dict(line, id=ref(53), document_id=ref(14), item_id=ref(2), item_name="Amoxiclav", unit_price=300,
                 amount=300, date=d(3)),
            dict(line, id=ref(54), document_id=ref(16), item_id=ref(1), item_name="Vyšetření", unit_price=884,
                 amount=884, date=d(4)),
            # money unit: a transferred unpaid balance, not an item
            dict(line, id=ref(55), document_id=ref(16), item_id=None, item_name="Převod nedoplatku z X",
                 unit_price=100, amount=100, date=d(4), unit="měna"),
            # zero line (discount note): left out
            dict(line, id=ref(56), document_id=ref(10), item_id=None, item_name="Poskytnutá sleva", unit_price=0,
                 amount=0, date=d(2), unit="%"),
        ])
        cls.data = cls.env["elite.vet.cash.closure"].closure_data(date(Y, 3, 1), date(Y, 3, 31))

    def test_presets_and_formatting(self):
        today = date(2026, 10, 27)
        self.assertEqual(preset_dates("this_month", today), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(preset_dates("last_month", today), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(preset_dates("today", today), (today, today))
        self.assertEqual(preset_dates("yesterday", today), (date(2026, 10, 26), date(2026, 10, 26)))
        self.assertEqual(preset_dates("last_month", date(2026, 1, 15)), (date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(money(1234.5), "1 234,50")
        self.assertEqual(money(-500), "-500,00")
        self.assertEqual(money(-0.001), "0,00")
        self.assertEqual(money_short(19000), "19 000")
        self.assertEqual(period_label(date(2026, 9, 1), date(2026, 9, 30)), "1. 9. – 30. 9. 2026")
        wizard = self.env["elite.vet.cash.closure.wizard"].create({})
        first, last = preset_dates("this_month", date.today())
        self.assertEqual(wizard.preset, "this_month")
        with self.subTest("onchange"):
            wizard.preset = "yesterday"
            wizard._onchange_preset()
            self.assertEqual(wizard.date_from, wizard.date_to)
            wizard.date_from = date(2026, 9, 1)
            wizard._onchange_dates()
            self.assertEqual(wizard.preset, "custom")
        self.assertTrue(first <= last)
        wizard.write({"date_from": date(Y, 3, 1), "date_to": date(Y, 3, 31)})
        self.assertEqual(wizard._closure_filename(), "Uzaverka_%d-03-01_%d-03-31" % (Y, Y))
        action = wizard.action_print()
        self.assertEqual(action["report_name"], "elite_vet_winvet.report_cash_closure_document")

    def test_sales_by_documents(self):
        podp = next(r for r in self.data["doc_rows"] if "PODP" in r["label"])
        self.assertEqual((podp["count"], podp["amount"]), (4, 4684))
        fav = next(r for r in self.data["doc_rows"] if "FAV" in r["label"])
        vrat = next(r for r in self.data["doc_rows"] if "VRAT" in r["label"])
        self.assertEqual((fav["count"], fav["amount"]), (1, 609))
        self.assertEqual((vrat["count"], vrat["amount"]), (2, -250), "VRAT counts negative")
        self.assertEqual(self.data["sales_total"], 4684 + 609 - 250)

    def test_payments_deposits_refunds(self):
        rows = {r["key"]: r for r in self.data["method_rows"]}
        self.assertEqual(list(rows), ["cash", "card", "transfer", "other"])
        self.assertEqual((rows["cash"]["new"], rows["cash"]["deposits"], rows["cash"]["refunds"]), (1000, 1000, 1200))
        # card: 2 500 - 500 from the deposit + 160 direct sale; deposit 2 000 received by card
        self.assertEqual((rows["card"]["new"], rows["card"]["deposits"], rows["card"]["refunds"]), (2160, 2000, 0))
        self.assertEqual((rows["transfer"]["new"], rows["other"]["new"]), (300, 40))
        self.assertEqual(rows["cash"]["after"], 1000 + 1000 - 1200)
        totals = self.data["totals"]
        self.assertEqual((totals["new"], totals["deposits"], totals["income"], totals["refunds"], totals["after"]),
                         (3500, 3000, 6500, 1200, 5300))
        self.assertEqual(self.data["from_deposit"], 500)
        self.assertEqual((self.data["refund_docs"], self.data["refund_deposits"]), (200, 1000))
        self.assertIn("Příjmy po evidovaných vráceních: 5 300,00 Kč", self.data["summary"])

    def test_daily_and_unpaid(self):
        days = {r["label"]: r for r in self.data["days"]}
        self.assertEqual(list(days), ["1. 3.", "2. 3.", "3. 3.", "4. 3."])
        self.assertEqual(days["1. 3."]["card"], 2000)
        self.assertEqual((days["2. 3."]["sales"], days["2. 3."]["cash"]), (1000, 2000))
        self.assertEqual(days["4. 3."]["refunded"], 1200)
        self.assertEqual(self.data["day_totals"]["after"], self.data["totals"]["after"])
        self.assertEqual(self.data["day_totals"]["sales"], self.data["sales_total"])
        self.assertTrue(self.data["show_other_day"])
        self.assertEqual([(r["number"], r["amount"]) for r in self.data["invoices"]], [("F18", 609)])
        self.assertEqual([(r["number"], r["method"], r["amount"]) for r in self.data["unpaid_docs"]],
                         [("P17", "Hotově", 884)])
        self.assertEqual(self.data["invoice_unpaid"] + self.data["unpaid_total"], 609 + 884)

    def test_deposit_section(self):
        dep = self.data["deposits"]
        self.assertEqual([(r["amount"], r["used"], r["refunded"], r["balance"]) for r in dep["rows"]],
                         [(2000, 500, 0, 1500), (1000, 0, 1000, 0)])
        self.assertEqual(dep["total"], {"amount": 3000, "used": 500, "refunded": 1000, "balance": 1500})
        self.assertTrue(dep["equation"])
        self.assertTrue(dep["winvet_ok"])
        self.assertEqual([(r["amount"], r["method"], r["received_method"]) for r in dep["refunds"]],
                         [(1000, "Hotově", "Hotově")])
        self.assertEqual([(r["document"], r["amount"]) for r in dep["uses"]], [("P13", 500)])

    def test_items_by_method(self):
        items = self.data["items"]
        self.assertEqual([c[0] for c in items["columns"]], ["cash", "card", "transfer", "unpaid"])
        rows = {r["label"]: r for r in items["rows"]}
        self.assertEqual(list(rows), ["Vyšetření", "Amoxiclav"], "sorted by total desc")
        self.assertEqual(dict(rows["Vyšetření"]["values"]), {"cash": 600, "card": 2500, "unpaid": 884})
        self.assertEqual(rows["Amoxiclav"]["quantity_text"], "3")
        self.assertEqual([(k["label"], k["total"]) for k in items["kinds"]], [("Úkony", 3984), ("Léky a zboží", 700)])
        self.assertEqual(items["totals"]["total"], 4684)
        self.assertEqual([(r["label"], r["amount"]) for r in items["money_rows"]], [("Převod nedoplatku z X", 100)])
        self.assertNotIn("Poskytnutá sleva", rows)

    def test_vat_section(self):
        vat = self.data["vat"]
        self.assertEqual([(r["label"], r["base"], r["vat"], r["total"]) for r in vat["rows"]],
                         [("21 %", 495.87, 104.13, 600), ("12 %", 357.14, 42.86, 400), ("0 %", 3684, 0, 3684)])
        self.assertEqual(vat["rows"][2]["kind_text"], "úkony 3\xa0384 Kč, léky a zboží 300 Kč")
        self.assertEqual(vat["total"]["total"], self.data["items"]["totals"]["total"])
        self.assertAlmostEqual(vat["total"]["base"] + vat["total"]["vat"], vat["total"]["total"])
        self.assertFalse(vat["without_vat"])
        # the same numbers in the sale line pivot, grouped by the rate
        Line = self.env["elite.vet.sale.line"]
        groups = Line._read_group(
            [("date", ">=", date(Y, 3, 1)), ("date", "<=", date(Y, 3, 31)), ("amount", "!=", 0),
             ("unit", "!=", "měna")], ["vat_rate_label"], ["amount_untaxed:sum", "amount_vat:sum"])
        self.assertEqual(sorted(groups), [("0 %", 3684, 0), ("12 %", 357.14, 42.86), ("21 %", 495.87, 104.13)])
        line = self.find("elite.vet.sale.line", 50)
        line.vat_rate = 10.5
        self.assertEqual((line.vat_rate_label, line.amount_untaxed, line.amount_vat), ("10,5 %", 542.99, 57.01))

    def test_report_renders_all_sections(self):
        wizard = self.env["elite.vet.cash.closure.wizard"].create({"preset": "custom", "date_from": date(Y, 3, 1),
                                                                    "date_to": date(Y, 3, 31)})
        html = self.env["ir.actions.report"]._render_qweb_html(
            "elite_vet_winvet.report_cash_closure_document", wizard.ids)[0].decode()
        for text in ("Pokladní uzávěrka", "1. Tržby podle dokladů", "2. Přijaté platby a vratky", "3. Denní rozpis",
                     "4. Faktury a doklady bez úhrady", "5. Zálohy", "6. Tržby podle položek a formy úhrady",
                     "Hotovost", "Platební karty", "Převod", "Jinak", "5 300,00", "-250,00", "F18", "P17",
                     "Kontrola: 3 000 Kč přijato", "Převod nedoplatku z X", "Předal/a", "Převzal/a",
                     "1. 3. – 31. 3. %d" % Y):
            self.assertIn(text, html, text)
        self.assertNotIn("Most zatím zálohy neposílá", html)
        self.assertNotIn("doklady jsou vystavené bez DPH", html)
        # one day: no daily table, sections renumbered
        wizard.write({"date_from": date(Y, 3, 4), "date_to": date(Y, 3, 4)})
        html = self.env["ir.actions.report"]._render_qweb_html(
            "elite_vet_winvet.report_cash_closure_document", wizard.ids)[0].decode()
        self.assertNotIn("Denní rozpis", html)
        self.assertIn("3. Faktury a doklady bez úhrady", html)
        self.assertIn("6. Rozpis DPH", html)
        self.assertIn("doklady jsou vystavené bez DPH", html, "4. 3. has only lines at 0 %")
        self.assertIn("4. 3. %d" % Y, html)

    def test_without_deposit_data(self):
        self.env["elite.vet.deposit.use"].search([]).unlink()
        self.env["elite.vet.deposit"].search([]).unlink()
        data = self.env["elite.vet.cash.closure"].closure_data(date(Y, 3, 1), date(Y, 3, 31))
        self.assertIsNone(data["deposits"])
        self.assertEqual(data["totals"]["deposits"], 0)
        wizard = self.env["elite.vet.cash.closure.wizard"].create({"date_from": date(Y, 3, 1),
                                                                    "date_to": date(Y, 3, 31)})
        html = self.env["ir.actions.report"]._render_qweb_html(
            "elite_vet_winvet.report_cash_closure_document", wizard.ids)[0].decode()
        self.assertIn("Most zatím zálohy neposílá", html)
