from odoo.tests import tagged

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestAnalytics(WinvetCase):

    def setUp(self):
        super().setUp()
        self.push("users", [{"id": self.ref(1), "name": "Testovací-Winvetová Zdenka", "code": "ZT", "active": True}])
        self.push("items", [self.item(20, "service", name="Vyšetření"), self.item(21, "product", name="Amoxiclav")])
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1, species="kočka")])
        self.push("visits", [{"id": self.ref(40), "patient_id": self.ref(10), "date": "2026-09-10", "time": "09:00:00",
                              "case_name": None, "diagnosis_code": None, "diagnosis_name": None,
                              "entered_by": self.ref(1), "document_id": self.ref(50)}])

    def line(self, n, item_n, amount, **over):
        rec = {"id": self.ref(n), "document_id": self.ref(50), "visit_id": self.ref(40), "item_id": self.ref(item_n),
               "item_code": "K%s" % item_n, "item_name": "Položka %s" % item_n, "quantity": 1, "unit": "ks",
               "unit_price": amount, "amount": amount, "vat_rate": 0, "date": "2026-09-10", "entered_by": self.ref(1)}
        rec.update(over)
        return rec

    def test_lines_before_document_and_kind(self):
        self.push("sale_lines", [self.line(60, 20, 600), self.line(61, 21, 250.5, quantity=2),
                                 self.line(62, 999, 10)])
        lines = {n: self.find("elite.vet.sale.line", n) for n in (60, 61, 62)}
        self.assertEqual(lines[60].kind, "service")
        self.assertEqual(lines[61].kind, "product")
        self.assertEqual(lines[62].kind, "other", "unknown item -> other")
        self.assertEqual(lines[60].pet_id, self.find("elite.vet.pet", 10))
        self.assertEqual(lines[60].species, "cat")
        self.assertEqual(lines[60].doctor_id, self.doctor)
        self.assertFalse(lines[60].document_id)
        self.push("sale_documents", [{"id": self.ref(50), "type": "UM", "number": "UM-50", "parent_id": None,
                                      "owner_id": self.ref(1), "date": "2026-09-10", "total": 860.5, "paid": 860.5,
                                      "from_deposit": 0, "state": "1", "entered_by": self.ref(1)}])
        doc = self.find("elite.vet.sale.document", 50)
        self.assertEqual(lines[60].document_id, doc)
        self.assertEqual(lines[60].partner_id, self.find("res.partner", 1))
        self.assertEqual(doc.doc_type_name, "Účet majitele")
        self.assertEqual(doc.currency_id, self.env.ref("base.CZK"))
        # item arriving later fixes the kind
        self.push("items", [self.item(999, "operation")])
        self.assertEqual(lines[62].kind, "service")
        groups = self.env["elite.vet.sale.line"].read_group(
            [("id", "in", [l.id for l in lines.values()])], ["amount:sum"], ["date:month", "kind"], lazy=False)
        self.assertEqual(sum(g["amount"] for g in groups), 860.5)

    def test_payments(self):
        self.push("sale_documents", [{"id": self.ref(50), "type": "FAV", "number": "F1", "parent_id": None,
                                      "owner_id": self.ref(1), "date": "2026-09-10", "total": 100, "paid": 100,
                                      "from_deposit": 0, "state": None, "entered_by": None}])
        self.push("payments", [
            {"id": self.ref(70), "document_id": self.ref(50), "owner_id": self.ref(1), "date": "2026-09-10",
             "time": "09:30:00", "method": "HOT", "amount": 60, "from_deposit": 0, "state": None, "refunded_date": None},
            {"id": self.ref(71), "document_id": self.ref(50), "owner_id": self.ref(1), "date": "2026-09-10",
             "time": "09:31:00", "method": "card", "amount": 30, "from_deposit": 0, "state": None, "refunded_date": None},
            {"id": self.ref(72), "document_id": self.ref(50), "owner_id": self.ref(1), "date": "2026-09-10",
             "time": "09:32:00", "method": "dob", "amount": 10, "from_deposit": 0, "state": None, "refunded_date": None},
        ])
        methods = [self.find("elite.vet.payment", n).method for n in (70, 71, 72)]
        self.assertEqual(methods, ["cash", "card", "other"])
        self.assertEqual(self.find("elite.vet.payment", 72).method_code, "dob")
        self.assertEqual(self.find("elite.vet.sale.document", 50).payment_ids.mapped("amount"), [60, 30, 10])

    def test_payment_method_of_account_and_lines(self):
        """The owner account (UM) gets the payment method of its receipt (PODP); lines follow."""
        doc = {"owner_id": self.ref(1), "date": "2026-09-10", "from_deposit": 0, "state": "U", "entered_by": None}
        self.push("sale_documents", [
            dict(doc, id=self.ref(50), type="UM", number="UM-50", parent_id=None, total=850, paid=850),
            dict(doc, id=self.ref(51), type="UM", number="UM-51", parent_id=None, total=99, paid=0),
        ])
        self.push("sale_lines", [self.line(60, 20, 600), self.line(61, 21, 250),
                                 self.line(62, 20, 99, document_id=self.ref(51))])
        account, unpaid = self.find("elite.vet.sale.document", 50), self.find("elite.vet.sale.document", 51)
        self.assertEqual((account.payment_method, unpaid.payment_method), ("unpaid", "unpaid"))
        self.push("sale_documents", [
            dict(doc, id=self.ref(52), type="PODP", number="P-52", parent_id=self.ref(50), total=850, paid=850),
            dict(doc, id=self.ref(53), type="PODP", number="P-53", parent_id=self.ref(51), total=99, paid=0),
        ])
        pay = {"owner_id": self.ref(1), "date": "2026-09-10", "time": "09:30:00", "from_deposit": 0, "state": "U",
               "refunded_date": None}
        self.push("payments", [dict(pay, id=self.ref(70), document_id=self.ref(52), method="PLATK", amount=850),
                               # a zero payment = recorded method but nothing paid (WinVet "bez úhrady")
                               dict(pay, id=self.ref(71), document_id=self.ref(53), method="HOT", amount=0)])
        self.assertEqual(account.payment_method, "card")
        self.assertEqual(self.find("elite.vet.sale.document", 52).payment_method, "card")
        self.assertEqual(unpaid.payment_method, "unpaid")
        self.assertEqual(self.find("elite.vet.sale.line", 60).payment_method, "card")
        self.assertEqual(self.find("elite.vet.sale.line", 62).payment_method, "unpaid")
        self.push("payments", [dict(pay, id=self.ref(72), document_id=self.ref(52), method="HOT", amount=1)])
        self.assertEqual(account.payment_method, "mixed")
        groups = self.env["elite.vet.sale.line"].read_group(
            [("id", "in", [self.find("elite.vet.sale.line", n).id for n in (60, 61, 62)])],
            ["amount:sum"], ["payment_method"], lazy=False)
        self.assertEqual({g["payment_method"]: g["amount"] for g in groups}, {"mixed": 850, "unpaid": 99})

    def test_analytics_views_load(self):
        actions = ["action_sale_line", "action_sale_line_services", "action_sale_line_products",
                   "action_sale_document", "action_payment", "action_visit", "action_vaccination",
                   "action_winvet_item", "action_winvet_user", "action_winvet_status", "action_winvet_config"]
        for xmlid in actions:
            action = self.env.ref("elite_vet_winvet.%s" % xmlid)
            modes = [(False, m) for m in action.view_mode.split(",")] + [(False, "search")]
            res = self.env[action.res_model].get_views(modes)
            for mode in action.view_mode.split(","):
                self.assertIn(mode, res["views"], (xmlid, mode))
        res = self.env["elite.vet.sale.line"].get_views([(False, "pivot"), (False, "graph")])
        self.assertIn('interval="month"', res["views"]["pivot"]["arch"])
        for model in ("res.partner", "elite.vet.pet"):
            self.env[model].get_views([(False, "form"), (False, "list")])

    def test_manager_access_and_reception_denied(self):
        from odoo.exceptions import AccessError
        Users = self.env["res.users"].with_context(no_reset_password=True)
        manager = Users.create({"name": "Správce A", "login": "winvet_mgr_a", "groups_id": [(6, 0, [
            self.env.ref("base.group_user").id, self.env.ref("elite_vet_reservation.group_reservation_manager").id])]})
        reception = Users.create({"name": "Recepce A", "login": "winvet_rec_a", "groups_id": [(6, 0, [
            self.env.ref("base.group_user").id, self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        self.push("sale_lines", [self.line(60, 20, 600)])
        self.env["elite.vet.sale.line"].with_user(manager).read_group([], ["amount:sum"], ["kind"])
        self.env["elite.vet.sale.line"].with_user(manager).get_views([(False, "pivot"), (False, "graph")])
        with self.assertRaises(AccessError):
            self.env["elite.vet.sale.line"].with_user(reception).search([])
        self.assertTrue(self.env["elite.vet.visit"].with_user(reception).search([("winvet_ref", "=", self.ref(40))]))
        with self.assertRaises(AccessError):
            self.env["elite.vet.sale.line"].with_user(manager).search([], limit=1).write({"amount": 1})


@tagged("post_install", "-at_install")
class TestDashboard(WinvetCase):

    def test_dashboard_figures(self):
        Line, Doc = self.env["elite.vet.sale.line"], self.env["elite.vet.sale.document"]
        Item = self.env["elite.vet.winvet.item"]
        service = Item.create({"winvet_ref": 9100001, "name": "Test úkon", "classification": "service"})
        product = Item.create({"winvet_ref": 9100002, "name": "Test lék", "classification": "product"})
        doc = Doc.create({"winvet_ref": 9100003, "doc_type": "UM", "date": "2031-05-10"})
        Line.create([
            {"winvet_ref": 9100004, "document_id": doc.id, "item_id": service.id, "item_name": "Test úkon",
             "amount": 1000, "quantity": 1, "date": "2031-05-10"},
            {"winvet_ref": 9100005, "document_id": doc.id, "item_id": product.id, "item_name": "Test lék",
             "amount": 250, "quantity": 2, "date": "2031-05-11"},
            {"winvet_ref": 9100006, "document_id": doc.id, "item_id": service.id, "item_name": "Test úkon",
             "amount": 400, "quantity": 1, "date": "2031-05-03"},
        ])
        data = self.env["elite.vet.winvet.dashboard"].get_data("2031-05-10", "2031-05-16", "2031-05-03", "2031-05-09")
        self.assertEqual(data["kpi"]["revenue"], 1250)
        self.assertEqual((data["kpi"]["services"], data["kpi"]["products"]), (1000, 250))
        self.assertEqual(data["kpi_previous"]["revenue"], 400)
        self.assertEqual(len(data["daily"]), 7)
        self.assertEqual(data["daily"][0], {"date": "2031-05-10", "service": 1000, "product": 0, "other": 0,
                                            "expense": 0, "by_category": {}})
        self.assertEqual(data["top_services"][0]["name"], "Test úkon")
        self.assertEqual(data["top_products"][0]["quantity"], 2)
        no_cmp = self.env["elite.vet.winvet.dashboard"].get_data("2031-05-10", "2031-05-16", compare=False)
        self.assertFalse(no_cmp["kpi_previous"])

    def test_dashboard_only_for_managers(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce Dashboard", "login": "dashboard_reception_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env["elite.vet.winvet.dashboard"].with_user(user).get_data()
