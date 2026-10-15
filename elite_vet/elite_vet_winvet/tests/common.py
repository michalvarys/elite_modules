from odoo.tests import TransactionCase

# WinVet ids far above anything the manual test data in ev_test could contain.
BASE = 9_000_000


class WinvetCase(TransactionCase):
    """Pushes payloads straight into the sync engine (the HTTP layer has its own test)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env["elite.vet.winvet.sync"]
        Doctor = cls.env["elite.vet.doctor"]
        cls.doctor = Doctor.create({"name": "MVDr. Zdenka Testovací-Winvetová"})

    def push(self, entity, records, mode="incremental", deleted=None, batch=1, batches=1, run_id="test-run"):
        res = self.sync.push({"entity": entity, "mode": mode, "records": records, "deleted": deleted or [],
                              "batch": batch, "batches": batches, "run_id": run_id})
        self.assertTrue(res.get("ok"), res)
        return res

    @staticmethod
    def ref(n):
        return BASE + n

    def find(self, model, n):
        key = str(self.ref(n)) if model == "res.partner" else self.ref(n)
        return self.env[model].with_context(active_test=False).search([("winvet_ref", "=", key)])

    def owner(self, n, **over):
        rec = {"id": self.ref(n), "kind": "person", "name": "Testová Jana %s" % n, "first_name": "Jana",
               "last_name": "Testová", "title": None, "street": "Testovací 1", "zip": "36001",
               "city": "Karlovy Vary", "country": "Česká republika", "company_reg": None, "vat": None,
               "note": None, "important_note": False, "active": True,
               "created": "2020-01-02", "modified": "2026-10-01 08:30:00"}
        rec.update(over)
        return rec

    def patient(self, n, owner_n, **over):
        rec = {"id": self.ref(n), "owner_id": self.ref(owner_n), "name": "Rex %s" % n, "species": "pes",
               "breed": "kříženec", "sex": "pes", "color": "černá", "birth_date": "2019-05-01",
               "birth_year": 2019, "chip": "203098100%06d" % n, "tattoo": None, "passport": None,
               "weight": 12.5, "deceased": False, "death_date": None, "active": True,
               "registered": "2019-06-01", "next_vaccination": "2027-01-01", "next_deworming": None,
               "important": None, "note": None, "created": "2019-06-01",
               "modified": "2026-10-01 09:00:00"}
        rec.update(over)
        return rec

    def item(self, n, classification="service", **over):
        rec = {"id": self.ref(n), "code": "K%s" % n, "name": "Položka %s" % n, "classification": classification,
               "stock_tracked": classification == "product", "tracked_drug": False, "unit": "ks",
               "barcode": None, "active": True}
        rec.update(over)
        return rec
