from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from ..models.expense import add_months
from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestExpense(WinvetCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Expense = cls.env["elite.vet.expense"]
        cls.rent = cls.env.ref("elite_vet_winvet.expense_category_rent")
        cls.drugs = cls.env.ref("elite_vet_winvet.expense_category_drugs")

    def expense(self, **vals):
        base = {"name": "Test výdaj", "date": "2031-05-12", "category_id": self.rent.id, "amount": 300}
        base.update(vals)
        return self.Expense.create(base)

    def test_add_months_keeps_end_of_month(self):
        self.assertEqual(add_months(date(2031, 1, 31), 1), date(2031, 2, 28))
        self.assertEqual(add_months(date(2031, 11, 15), 3), date(2032, 2, 15))

    def test_amount_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self.expense(amount=0)

    def test_monthly_copies(self):
        first = self.expense(name="Nájem", date="2031-01-31", amount=20000, repeat_monthly_until="2031-04-30")
        copies = self.Expense.search([("recurring_origin_id", "=", first.id)], order="date")
        self.assertEqual([str(c.date) for c in copies], ["2031-02-28", "2031-03-31", "2031-04-30"])
        self.assertEqual(set(copies.mapped("amount")), {20000})
        self.assertFalse(first.repeat_monthly_until)
        with self.assertRaises(ValidationError):
            self.expense(date="2031-05-12", repeat_monthly_until="2031-05-01")

    def test_dashboard_expenses_and_profit(self):
        Line, Doc = self.env["elite.vet.sale.line"], self.env["elite.vet.sale.document"]
        item = self.env["elite.vet.winvet.item"].create({"winvet_ref": 9200001, "name": "Úkon", "classification": "service"})
        doc = Doc.create({"winvet_ref": 9200002, "doc_type": "UM", "date": "2031-05-10"})
        Line.create({"winvet_ref": 9200003, "document_id": doc.id, "item_id": item.id, "item_name": "Úkon",
                     "amount": 1000, "quantity": 1, "date": "2031-05-10"})
        self.expense(date="2031-05-10", amount=300)
        self.expense(date="2031-05-11", amount=900, category_id=self.drugs.id, name="Faktura léky")
        self.expense(date="2031-05-03", amount=100)   # comparison period
        data = self.env["elite.vet.winvet.dashboard"].get_data("2031-05-10", "2031-05-16", "2031-05-03", "2031-05-09")
        kpi = data["kpi"]
        self.assertEqual((kpi["revenue"], kpi["expenses"], kpi["profit"], kpi["expense_count"]), (1000, 1200, -200, 2))
        self.assertEqual(data["kpi_previous"]["expenses"], 100)
        self.assertEqual(data["daily"][0]["expense"], 300)
        self.assertEqual(data["daily"][1]["by_category"], {str(self.drugs.id): 900})
        self.assertEqual([c["id"] for c in data["expense_categories"]], [self.drugs.id, self.rent.id])
        self.assertEqual(data["top_expenses"][0]["name"], "Faktura léky")
        self.assertTrue(data["has_expenses"])

    def test_from_the_start_ends_today_despite_future_rent(self):
        self.Expense.search([]).unlink()
        self.env["elite.vet.sale.line"].search([]).unlink()
        self.env["elite.vet.payment"].search([]).unlink()
        self.expense(date="2026-01-01", amount=10, repeat_monthly_until="2040-01-01")
        bounds = self.env["elite.vet.winvet.dashboard"]._data_bounds()
        self.assertEqual(bounds["first"], date(2026, 1, 1))
        self.assertLessEqual(bounds["last"], date.today())
        self.assertFalse(bounds["winvet_last"])

    def test_reception_cannot_see_expenses(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce Výdaje", "login": "expense_reception_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        with self.assertRaises(AccessError):
            self.Expense.with_user(user).search([])

    def test_attachment_filter(self):
        with_doc, without = self.expense(name="S dokladem"), self.expense(name="Bez dokladu")
        self.env["ir.attachment"].create({"name": "uctenka.pdf", "res_model": "elite.vet.expense",
                                          "res_id": with_doc.id, "raw": b"%PDF-1.4"})
        self.assertTrue(with_doc.has_attachment)
        missing = self.Expense.search([("has_attachment", "=", False), ("id", "in", (with_doc | without).ids)])
        self.assertEqual(missing, without)

    def test_views_load(self):
        for view in ("list", "form", "pivot", "graph", "search"):
            self.Expense.get_view(view_type=view)
