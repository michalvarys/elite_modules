from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.models.winvet_tools import map_species, name_words

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestMasterData(WinvetCase):

    def test_species_mapping(self):
        cases = {
            "pes": "dog", "Pes": "dog", "kočka": "cat", "KOČKA": "cat", "kocour": "cat", "králík": "rabbit",
            "morče": "rodent", "potkan": "rodent", "křeček": "rodent", "myš": "rodent", "osmák degu": "rodent",
            "činčila": "rodent", "pískomil": "rodent", "had": "reptile", "agama": "reptile",
            "želva": "reptile", "gekon": "reptile", "papoušek": "bird", "andulka": "bird", "korela": "bird",
        }
        for raw, key in cases.items():
            self.assertEqual(map_species(raw), (key, False), raw)
        self.assertEqual(map_species("fretka"), ("other", "fretka"))
        self.assertEqual(map_species(None), ("other", False))

    def test_name_words(self):
        self.assertEqual(name_words("MVDr. Jana Nováková, Ph.D."), {"jana", "novakova"})
        self.assertEqual(name_words("Nováková Jana"), {"jana", "novakova"})

    def test_users_doctor_match(self):
        other = self.env["elite.vet.doctor"].create({"name": "MVDr. Petra Jiná-Winvetová"})
        self.push("users", [
            {"id": self.ref(1), "name": "Testovací-Winvetová Zdenka", "code": "ZT", "active": True},
            {"id": self.ref(2), "name": "Úplně Neznámá", "code": "UN", "active": False},
        ])
        u1, u2 = self.find("elite.vet.winvet.user", 1), self.find("elite.vet.winvet.user", 2)
        self.assertEqual(u1.doctor_id, self.doctor)
        self.assertFalse(u2.doctor_id)
        self.assertFalse(u2.active)
        # a manual link is kept on the next push
        u1.doctor_id = other
        self.push("users", [{"id": self.ref(1), "name": "Testovací-Winvetová Zdenka", "code": "ZT", "active": True}])
        self.assertEqual(u1.doctor_id, other)

    def test_items_kind(self):
        self.push("items", [self.item(1, "service"), self.item(2, "operation"), self.item(3, "product"),
                            self.item(4, "set"), self.item(5, "kit"), self.item(6, "group"), self.item(7, 4),
                            self.item(8, 9)])
        kinds = {n: self.find("elite.vet.winvet.item", n).kind for n in range(1, 9)}
        self.assertEqual(kinds, {1: "service", 2: "service", 3: "product", 4: "product", 5: "product",
                                 6: "other", 7: "service", 8: "other"})
        self.assertEqual(self.find("elite.vet.winvet.item", 8).classification, "other")

    def test_idempotent_push(self):
        owners = [self.owner(1), self.owner(2, kind="company", name="Útulek Test s.r.o.", company_reg="12345678")]
        patients = [self.patient(10, 1), self.patient(11, 2, species="morče", name=None)]
        items = [self.item(20)]
        first = [self.push("owners", owners), self.push("patients", patients), self.push("items", items)]
        self.assertEqual([r["created"] for r in first], [2, 2, 1])
        second = [self.push("owners", owners), self.push("patients", patients), self.push("items", items)]
        for res in second:
            self.assertEqual((res["created"], res["updated"], res["deleted"], res["skipped"]), (0, 0, 0, 0), res)
        # a real change in WinVet (new `modified`) is written
        owners[0].update(city="Cheb", modified="2026-10-02 10:00:00")
        res = self.push("owners", owners)
        self.assertEqual(res["updated"], 1)
        partner = self.find("res.partner", 1)
        self.assertEqual(partner.city, "Cheb")
        self.assertEqual(partner.country_id.code, "CZ")
        self.assertTrue(partner.is_vet_client)
        company = self.find("res.partner", 2)
        self.assertTrue(company.is_company)
        self.assertEqual(company.company_registry, "12345678")
        self.assertTrue(company.is_vet_client, "company with patients is a clinic client")
        pet = self.find("elite.vet.pet", 11)
        self.assertEqual(pet.name, "Bez jména")
        self.assertEqual(pet.species, "rodent")

    def test_patient_fields_and_species_other(self):
        self.push("owners", [self.owner(1)])
        self.push("patients", [
            self.patient(10, 1, species="fretka", deceased=True, death_date="2026-01-05", weight=1.2),
            self.patient(11, 1, active=False, species="kočka"),
        ])
        pet, inactive = self.find("elite.vet.pet", 10), self.find("elite.vet.pet", 11)
        self.assertEqual((pet.species, pet.species_other, pet.winvet_species), ("other", "fretka", "fretka"))
        self.assertTrue(pet.deceased)
        self.assertTrue(pet.active, "deceased pets stay visible, only flagged")
        self.assertEqual(str(pet.death_date), "2026-01-05")
        self.assertEqual(pet.partner_id, self.find("res.partner", 1))
        self.assertEqual(pet.weight, 1.2)
        self.assertFalse(inactive.active)
        self.assertEqual(inactive.species, "cat")

    def test_patient_before_owner_fixup(self):
        self.push("patients", [self.patient(10, 1)])
        pet = self.find("elite.vet.pet", 10)
        self.assertEqual(pet.partner_id, self.env.ref("elite_vet_winvet.partner_unknown_owner"))
        self.assertEqual(pet.winvet_owner_ref, self.ref(1))
        self.push("owners", [self.owner(1, kind="company", name="Firma bez osoby")])
        partner = self.find("res.partner", 1)
        self.assertEqual(pet.partner_id, partner)
        self.assertTrue(partner.is_vet_client)
        # pushing the patient again is a no-op now
        res = self.push("patients", [self.patient(10, 1)])
        self.assertEqual(res["updated"], 0)

    def test_group_owner_not_client(self):
        self.push("owners", [self.owner(1, kind="group", name="Skupina chovatelů")])
        self.assertFalse(self.find("res.partner", 1).is_vet_client)

    def test_vaccinations_and_visits_on_pet(self):
        self.push("users", [{"id": self.ref(1), "name": "Testovací-Winvetová Zdenka", "code": "ZT", "active": True}])
        self.push("items", [self.item(20, "product", name="Nobivac DHPPi")])
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)])
        self.push("vaccinations", [{"id": self.ref(30), "patient_id": self.ref(10), "date": "2026-03-01",
                                    "next_date": "2027-03-01", "item_id": self.ref(20), "item_name": "Nobivac DHPPi",
                                    "quantity": 1, "unit": "dávka", "kind": 1}])
        self.push("visits", [{"id": self.ref(40), "patient_id": self.ref(10), "date": "2026-03-01",
                              "time": "10:15:00", "case_name": "Vakcinace", "diagnosis_code": "Z24",
                              "diagnosis_name": "Očkování", "entered_by": self.ref(1), "document_id": self.ref(50)}])
        pet = self.find("elite.vet.pet", 10)
        self.assertEqual(pet.vaccination_ids.item_id, self.find("elite.vet.winvet.item", 20))
        visit = pet.visit_ids
        self.assertEqual(visit.entered_by_id.doctor_id, self.doctor)
        self.assertEqual(visit.partner_id, pet.partner_id)
        self.assertFalse(visit.document_id)
        self.assertEqual(visit.document_winvet_ref, self.ref(50))
        self.push("sale_documents", [{"id": self.ref(50), "type": "UM", "number": "UM-1", "parent_id": None,
                                      "owner_id": self.ref(1), "date": "2026-03-01", "total": 500, "paid": 500,
                                      "from_deposit": 0, "state": 1, "entered_by": self.ref(1)}])
        self.assertEqual(visit.document_id, self.find("elite.vet.sale.document", 50))

    def test_reception_reads_pet_tabs(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce WinVet Test", "login": "winvet_reception_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        self.push("owners", [self.owner(1)])
        self.push("patients", [self.patient(10, 1)])
        self.push("visits", [{"id": self.ref(40), "patient_id": self.ref(10), "date": "2026-03-01", "time": None,
                              "case_name": None, "diagnosis_code": None, "diagnosis_name": "Kontrola",
                              "entered_by": None, "document_id": None}])
        pet = self.find("elite.vet.pet", 10).with_user(user)
        data = pet.web_read({"visit_ids": {"fields": {"date": {}, "diagnosis_name": {}, "entered_by_id": {}}},
                             "vaccination_ids": {"fields": {"item_name": {}}}, "chip": {}})
        self.assertEqual(data[0]["visit_ids"][0]["diagnosis_name"], "Kontrola")
        self.env["elite.vet.pet"].with_user(user).get_views([(False, "form")])

    def test_bad_dates_become_empty(self):
        self.push("owners", [self.owner(1, created="0218-10-25", modified="3018-01-01 10:00:00")])
        res = self.push("patients", [self.patient(10, 1, birth_date="0218-10-25", next_vaccination="2027-13-45")])
        self.assertEqual(res["created"], 1)
        pet = self.find("elite.vet.pet", 10)
        self.assertFalse(pet.birth_date)
        self.assertFalse(pet.next_vaccination)
        self.assertFalse(self.find("res.partner", 1).winvet_created)
        self.assertFalse(self.find("res.partner", 1).winvet_modified)
        self.assertIn("birth_date=0218-10-25", self.env["elite.vet.winvet.status"].get_status().last_error)
        # idempotent with the bad values too
        self.assertEqual(self.push("patients", [self.patient(10, 1, birth_date="0218-10-25",
                                                             next_vaccination="2027-13-45")])["updated"], 0)

    def test_null_owner_kind_and_null_refs(self):
        self.push("owners", [self.owner(1, kind=None)])
        partner = self.find("res.partner", 1)
        self.assertFalse(partner.winvet_kind)
        self.assertFalse(partner.is_company)
        self.push("patients", [self.patient(10, 1, owner_id=None)])
        pet = self.find("elite.vet.pet", 10)
        self.assertEqual(pet.partner_id, self.env.ref("elite_vet_winvet.partner_unknown_owner"))
        self.assertFalse(pet.winvet_owner_ref)
