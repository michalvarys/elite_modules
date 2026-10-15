from odoo.tests import tagged

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestContractV2(WinvetCase):
    """Contract v2: item prices, visit notes, vitals, concurrency rule for owners/patients."""

    def visit(self, n, patient_n, **over):
        rec = {"id": self.ref(n), "patient_id": self.ref(patient_n), "date": "2026-10-10", "time": "10:00:00",
               "case_name": None, "diagnosis_code": None, "diagnosis_name": "Kontrola", "entered_by": None,
               "document_id": None, "notes": None}
        rec.update(over)
        return rec

    def vital(self, n, visit_n, **over):
        rec = {"id": self.ref(n), "visit_id": self.ref(visit_n), "time": "10:05:00", "temperature": 38.6,
               "heart_rate": 110.0, "respiratory_rate": 28, "weight": 12.4, "bp_systolic": None,
               "bp_diastolic": None}
        rec.update(over)
        return rec

    def test_unknown_entity_rejected(self):
        res = self.sync.push({"entity": "nonsense", "mode": "full", "records": [], "batch": 1, "batches": 1,
                              "run_id": "x"})
        self.assertEqual(res, {"ok": False, "error": "unknown entity"})
        self.assertIn("vitals", self.sync._winvet_entities())

    def test_item_prices(self):
        self.push("items", [self.item(1, price=450.0, price_untaxed=371.9, vat_rate=21),
                            self.item(2, price=None, price_untaxed=None, vat_rate=None)])
        item, no_price = self.find("elite.vet.winvet.item", 1), self.find("elite.vet.winvet.item", 2)
        self.assertEqual((item.price, item.price_untaxed, item.vat_rate), (450.0, 371.9, 21.0))
        self.assertEqual(item.currency_id, self.env.ref("base.CZK"))
        self.assertEqual(no_price.price, 0.0)
        # unchanged push is a no-op, a price change is written
        self.assertEqual(self.push("items", [self.item(1, price=450.0, price_untaxed=371.9, vat_rate=21)])["updated"], 0)
        self.push("items", [self.item(1, price=500.0, price_untaxed=413.22, vat_rate=21)])
        self.assertEqual(item.price, 500.0)

    def test_visit_notes(self):
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)])
        self.push("visits", [self.visit(40, 10, notes="Klinicky v pořádku.\nKontrola za 14 dní.")])
        visit = self.find("elite.vet.visit", 40)
        self.assertEqual(visit.notes, "Klinicky v pořádku.\nKontrola za 14 dní.")
        self.push("visits", [self.visit(40, 10, notes=None)])
        self.assertFalse(visit.notes)

    def test_vitals(self):
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)])
        # vitals before their visit: stored, linked by the fixup when the visit arrives
        res = self.push("vitals", [self.vital(60, 40), self.vital(61, 40, time="10:30:00", temperature=38.2,
                                                                  heart_rate=None, weight=None,
                                                                  bp_systolic=120, bp_diastolic=80.0)])
        self.assertEqual(res["created"], 2)
        vital = self.find("elite.vet.visit.vital", 60)
        self.assertFalse(vital.visit_id)
        self.push("visits", [self.visit(40, 10)])
        visit = self.find("elite.vet.visit", 40)
        self.assertEqual(vital.visit_id, visit)
        self.assertEqual(len(visit.vital_ids), 2)
        self.assertEqual(vital.pet_id, self.find("elite.vet.pet", 10))
        self.assertEqual((vital.temperature, vital.heart_rate, vital.respiratory_rate, vital.weight),
                         (38.6, 110, 28, 12.4))
        self.assertEqual(vital.summary(), "T 38,6 °C · P 110/min · D 28/min · 12,4 kg")
        self.assertEqual(self.find("elite.vet.visit.vital", 61).summary(), "T 38,2 °C · D 28/min · TK 120/80")
        # idempotent; deleted vitals are removed
        self.assertEqual(self.push("vitals", [self.vital(60, 40)])["updated"], 0)
        self.assertEqual(self.push("vitals", [], deleted=[self.ref(61)])["deleted"], 1)
        self.assertFalse(self.find("elite.vet.visit.vital", 61))
        # full run without the row deletes it
        self.push("vitals", [], mode="full", run_id="vitals-full")
        self.assertFalse(self.find("elite.vet.visit.vital", 60))
        line = self.env["elite.vet.winvet.status"].get_status().entity_ids.filtered(lambda e: e.entity == "vitals")
        self.assertEqual(line.sequence, self.sync._winvet_entities().index("vitals"))

    def test_owner_edit_survives_unchanged_push(self):
        owner = self.owner(1)
        self.push("owners", [owner])
        partner = self.find("res.partner", 1)
        partner.write({"name": "Opraveno v Odoo", "street": "Nová 5"})
        res = self.push("owners", [owner], mode="full", run_id="owners-full-1")
        self.assertEqual(res["updated"], 0)
        self.assertEqual((partner.name, partner.street), ("Opraveno v Odoo", "Nová 5"))
        self.assertTrue(partner.active, "reconciliation still sees the id")
        # changed in WinVet -> WinVet wins
        self.push("owners", [dict(owner, street="Stará 7", modified="2026-10-14 12:00:00")])
        self.assertEqual((partner.name, partner.street), (owner["name"], "Stará 7"))

    def test_patient_edit_survives_unchanged_push(self):
        self.push("owners", [self.owner(1)])
        patient = self.patient(10, 1)
        self.push("patients", [patient])
        pet = self.find("elite.vet.pet", 10)
        pet.write({"breed": "labrador", "weight": 14.0})
        self.assertEqual(self.push("patients", [patient])["updated"], 0)
        self.assertEqual((pet.breed, pet.weight), ("labrador", 14.0))
        self.push("patients", [dict(patient, weight=13.1, modified="2026-10-14 12:00:00")])
        self.assertEqual((pet.breed, pet.weight), ("kříženec", 13.1))
        # still archived when missing in a full run
        self.push("patients", [], mode="full", run_id="patients-full-1")
        self.assertFalse(pet.active)

    def test_missing_modified_compares_values(self):
        self.push("owners", [self.owner(1, modified=None)])
        self.push("owners", [self.owner(1, modified=None, city="Sokolov")])
        self.assertEqual(self.find("res.partner", 1).city, "Sokolov")

    def test_merged_owner_not_recreated(self):
        self.push("owners", [self.owner(1), self.owner(2)])
        self.push("patients", [self.patient(10, 1), self.patient(11, 2)])
        dst, src = self.find("res.partner", 1), self.find("res.partner", 2)
        self.env["base.partner.merge.automatic.wizard"]._merge((dst | src).ids, dst)
        self.assertFalse(src.exists())
        self.assertEqual(dst.winvet_ref, str(self.ref(1)))
        self.assertEqual(dst.winvet_alias_refs, ",%s," % self.ref(2))
        self.assertEqual(self.find("elite.vet.pet", 11).partner_id, dst)
        # WinVet still has both owners: the merged one is neither re-created nor written
        res = self.push("owners", [self.owner(1), self.owner(2, city="Jinde", modified="2026-10-14 12:00:00")])
        self.assertEqual(res["created"], 0)
        self.assertFalse(self.find("res.partner", 2))
        self.assertNotEqual(dst.city, "Jinde")
        self.push("patients", [self.patient(12, 2)])
        self.assertEqual(self.find("elite.vet.pet", 12).partner_id, dst)

    def test_merge_into_partner_without_winvet_id(self):
        web = self.env["res.partner"].create({"name": "Webový klient", "is_vet_client": True})
        self.push("owners", [self.owner(1)])
        src = self.find("res.partner", 1)
        self.env["base.partner.merge.automatic.wizard"]._merge((web | src).ids, web)
        self.assertEqual(web.winvet_ref, str(self.ref(1)))
        self.assertFalse(web.winvet_alias_refs)
        self.assertEqual(self.push("owners", [self.owner(1)])["created"], 0)
