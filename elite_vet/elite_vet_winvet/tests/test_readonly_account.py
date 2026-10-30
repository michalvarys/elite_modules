"""Read-only API account (group "WinVet data / Jen čtení (API)"): reads all WinVet data, changes nothing."""
from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import WinvetCase

#: everything the bridge stores (elite_vet_sale / elite_vet_clinic models only when installed)
DATA_MODELS = [
    "res.partner", "elite.vet.pet", "elite.vet.winvet.user", "elite.vet.winvet.item", "elite.vet.winvet.contact",
    "elite.vet.vaccination", "elite.vet.visit", "elite.vet.visit.vital", "elite.vet.sale.document",
    "elite.vet.sale.line", "elite.vet.payment", "elite.vet.deposit", "elite.vet.deposit.use", "elite.vet.expense",
    "elite.vet.expense.category", "elite.vet.winvet.calendar.event", "elite.vet.winvet.calendar.resource",
    "elite.vet.winvet.calendar.activity", "elite.vet.winvet.status", "elite.vet.winvet.status.entity",
    "elite.vet.winvet.schema.change", "elite.vet.winvet.stock.layer", "elite.vet.winvet.stock.total",
    "elite.vet.procedure.bundle", "elite.vet.procedure.bundle.line", "elite.vet.text.template",
]


@tagged("post_install", "-at_install")
class TestReadonlyAccount(WinvetCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader = cls.env["res.users"].create({
            "name": "Agent (jen čtení)", "login": "winvet_reader_test",
            "groups_id": [(6, 0, [cls.env.ref("elite_vet_winvet.group_winvet_readonly").id])]})

    def test_reads_every_data_model(self):
        for name in DATA_MODELS:
            if name not in self.env:
                continue
            with self.subTest(name):
                Model = self.env[name].with_user(self.reader)
                self.assertTrue(Model.has_access("read"), name)
                # partners carry accounting fields the account must not read: an agent lists the fields
                Model.search_read([], ["name", "winvet_ref"] if name == "res.partner" else None, limit=1)
                for operation in ("write", "create", "unlink"):
                    self.assertFalse(Model.has_access(operation), "%s: %s" % (name, operation))

    def test_no_write_right_on_clinic_data(self):
        groups = self.reader.groups_id
        acl = self.env["ir.model.access"].search([("group_id", "in", groups.ids), "|", "|",
                                                  ("perm_write", "=", True), ("perm_create", "=", True),
                                                  ("perm_unlink", "=", True)])
        writable = {a.model_id.model for a in acl}
        self.assertFalse({m for m in writable if m.startswith("elite.") or m == "res.partner"}, writable)
        self.assertFalse(self.reader.has_group("elite_vet_reservation.group_reservation_reception"))
        # the bridge API key and the run log stay hidden
        for name in ("elite.vet.winvet.config", "elite.vet.winvet.run"):
            self.assertFalse(self.env[name].with_user(self.reader).has_access("read"), name)

    def test_manager_only_fields_and_reports(self):
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(2, 1)])
        self.push("visits", [{"id": self.ref(3), "patient_id": self.ref(2), "date": "2031-03-02", "time": "10:00:00",
                              "case_name": None, "diagnosis_code": None, "diagnosis_name": "Kontrola",
                              "entered_by": None, "document_id": None}])
        visit = self.find("elite.vet.visit", 3).with_user(self.reader)
        visit.read(["document_id", "line_ids", "amount", "diagnosis_name"])
        partner = self.find("res.partner", 1).with_user(self.reader)
        partner.read(["winvet_deposit_ids", "winvet_deposit_balance"])
        with self.assertRaises(AccessError):
            visit.write({"diagnosis_name": "změna"})
        with self.assertRaises(AccessError):
            partner.write({"name": "Jiné jméno"})
        data = self.env["elite.vet.winvet.dashboard"].with_user(self.reader).get_data("2031-03-01", "2031-03-31")
        self.assertTrue(data)
        closure = self.env["elite.vet.cash.closure"].with_user(self.reader).closure_data(date(2031, 3, 1),
                                                                                       date(2031, 3, 31))
        self.assertIn("vat", closure)
