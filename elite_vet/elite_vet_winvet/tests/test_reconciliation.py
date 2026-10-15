from odoo.tests import tagged

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestReconciliation(WinvetCase):

    def test_deleted_master_archived(self):
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)])
        self.push("items", [self.item(20)])
        self.assertEqual(self.push("patients", [], deleted=[self.ref(10)])["deleted"], 1)
        self.push("items", [], deleted=[self.ref(20)])
        self.push("owners", [], deleted=[self.ref(1)])
        self.assertFalse(self.find("elite.vet.pet", 10).active)
        self.assertFalse(self.find("elite.vet.winvet.item", 20).active)
        self.assertFalse(self.find("res.partner", 1).active)
        self.assertTrue(self.find("elite.vet.pet", 10), "master data are archived, not deleted")

    def test_deleted_analytics_removed(self):
        self.push("sale_documents", [{"id": self.ref(50), "type": "UM", "number": "X", "parent_id": None,
                                      "owner_id": None, "date": "2026-01-01", "total": 1, "paid": 1,
                                      "from_deposit": 0, "state": None, "entered_by": None}])
        self.push("payments", [{"id": self.ref(70), "document_id": self.ref(50), "owner_id": None,
                                "date": "2026-01-01", "time": None, "method": "HOT", "amount": 1,
                                "from_deposit": 0, "state": None, "refunded_date": None}])
        self.assertEqual(self.push("payments", [], deleted=[self.ref(70)])["deleted"], 1)
        self.push("sale_documents", [], deleted=[self.ref(50)])
        self.assertFalse(self.find("elite.vet.payment", 70))
        self.assertFalse(self.find("elite.vet.sale.document", 50))

    def test_full_run_archives_missing(self):
        self.push("items", [self.item(1), self.item(2), self.item(3)])
        # existing items of the database outside this test must not disturb the counts
        foreign = self.env["elite.vet.winvet.item"].search([("winvet_ref", "<", self.ref(0))])
        res1 = self.push("items", [self.item(1)], mode="full", batch=1, batches=2, run_id="full-1")
        self.assertEqual(res1["deleted"], 0, "nothing reconciled before the last batch")
        res2 = self.push("items", [self.item(3)], mode="full", batch=2, batches=2, run_id="full-1")
        self.assertEqual(res2["deleted"], 1 + len(foreign))
        self.assertTrue(self.find("elite.vet.winvet.item", 1).active)
        self.assertFalse(self.find("elite.vet.winvet.item", 2).active)
        self.assertTrue(self.find("elite.vet.winvet.item", 3).active)
        self.assertFalse(self.env["elite.vet.winvet.run"].search([("run_id", "=", "full-1")]))

    def test_full_run_with_missing_batch_skips_reconciliation(self):
        self.push("items", [self.item(1), self.item(2)])
        res = self.push("items", [self.item(1)], mode="full", batch=2, batches=2, run_id="full-2")
        self.assertEqual(res["deleted"], 0)
        self.assertTrue(self.find("elite.vet.winvet.item", 2).active)
        self.assertIn("nemá všechny dávky", self.env["elite.vet.winvet.status"].get_status().last_error)

    def test_full_run_deletes_missing_analytics(self):
        lines = [{"id": self.ref(n), "document_id": None, "visit_id": None, "item_id": None, "item_code": "X",
                  "item_name": "X", "quantity": 1, "unit": None, "unit_price": 1, "amount": 1, "vat_rate": 0,
                  "date": "2026-01-01", "entered_by": None} for n in (60, 61)]
        self.push("sale_lines", lines)
        self.push("sale_lines", lines[:1], mode="full", run_id="full-3")
        self.assertTrue(self.find("elite.vet.sale.line", 60))
        self.assertFalse(self.find("elite.vet.sale.line", 61))

    def test_full_run_ignores_odoo_only_pets(self):
        partner = self.env["res.partner"].create({"name": "Webový klient"})
        own = self.env["elite.vet.pet"].create({"name": "Webový pes", "partner_id": partner.id})
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)], mode="full", run_id="full-4")
        self.assertTrue(own.active)
        self.assertTrue(self.find("elite.vet.pet", 10).active)

    def test_bad_record_is_skipped(self):
        res = self.sync.push({"entity": "items", "mode": "incremental", "records": [{"name": "bez id"}, self.item(1)],
                              "deleted": [], "batch": 1, "batches": 1, "run_id": "x"})
        self.assertEqual((res["created"], res["skipped"]), (1, 1))

    def test_unknown_deleted_ids_ignored(self):
        res = self.push("sale_lines", [], deleted=[self.ref(12345), self.ref(12346)])
        self.assertEqual((res["deleted"], res["skipped"]), (0, 0))

    def test_empty_full_batch_reconciles(self):
        self.push("users", [{"id": self.ref(1), "name": "A B", "code": "AB", "active": True}])
        res = self.push("users", [], mode="full", run_id="empty-run")
        self.assertGreaterEqual(res["deleted"], 1)
        self.assertFalse(self.find("elite.vet.winvet.user", 1).active)
        # repeated full runs with the same data are cheap no-ops
        users = [{"id": self.ref(2), "name": "C D", "code": "CD", "active": True}]
        self.push("users", users, mode="full", run_id="u1")
        res = self.push("users", users, mode="full", run_id="u2")
        self.assertEqual((res["created"], res["updated"], res["deleted"]), (0, 0, 0))
