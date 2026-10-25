from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestPetForm(ReceptionCase):
    """Task 22: every pet field in the Kartotéka pet form (save_pet / owner_data)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role formulář zvířete", "login": "pet_form_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})
        cls.client = cls.env["res.partner"].create({"name": "Formulář Zvířete-Testová", "is_vet_client": True})

    def pet_of(self, data, name):
        return [p for p in data["pets"] if p["name"] == name][0]

    def test_save_and_read_every_field(self):
        reception = self.api(self.reception)
        data = reception.save_pet(self.client.id, {
            "name": "Fretka Úplná", "species": "other", "species_other": " fretka ", "breed": "albín",
            "sex": "samice", "birth_date": "2021-04-03", "birth_year": "2021", "chip": "999 111",
            "tattoo": "AB12", "passport": "CZ-123", "color": "bílá", "weight": "1,25",
            "next_vaccination": "2027-01-15", "next_deworming": "2026-12-01", "important_note": "kouše při odběru",
            "note": "plachá", "alerts": [{"kind": "allergy", "note": "penicilin"}, {"kind": "bites"}],
        })
        pet = self.env["elite.vet.pet"].search([("partner_id", "=", self.client.id)])
        self.assertEqual(len(pet), 1)
        self.assertEqual(
            (pet.species, pet.species_other, pet.breed, pet.sex, pet.birth_date, pet.birth_year, pet.chip,
             pet.tattoo, pet.passport, pet.color, pet.weight, pet.next_vaccination, pet.next_deworming,
             pet.important_note, pet.note, pet.deceased),
            ("other", "fretka", "albín", "samice", date(2021, 4, 3), 2021, "999 111", "AB12", "CZ-123", "bílá",
             1.25, date(2027, 1, 15), date(2026, 12, 1), "kouše při odběru", "plachá", False))
        self.assertEqual(sorted(pet.alert_ids.mapped("kind")), ["allergy", "bites"])
        row = self.pet_of(data, "Fretka Úplná")
        self.assertEqual(
            (row["species_label"], row["species_other"], row["birth_year"], row["tattoo"], row["passport"],
             row["color"], row["weight"], row["next_deworming"], row["important_note"], row["death_date"]),
            ("fretka", "fretka", 2021, "AB12", "CZ-123", "bílá", 1.25, "2026-12-01", "kouše při odběru", None))
        self.assertEqual(sorted((a["kind"], a["kind_label"], a["note"]) for a in row["alert_list"]),
                         [("allergy", "Alergie", "penicilin"), ("bites", "Kouše", None)])
        self.assertIn("Alergie: penicilin", row["alerts"])

        # weight with a dot, as a number, and with spaces
        for value, expected in (("2.5", 2.5), (3, 3.0), (" 4,75 ", 4.75)):
            reception.save_pet(self.client.id, {"weight": value}, pet_id=pet.id)
            self.assertEqual(pet.weight, expected)
        # species other than Jiné drops Jiný druh
        reception.save_pet(self.client.id, {"species": "cat"}, pet_id=pet.id)
        self.assertEqual((pet.species, pet.species_other), ("cat", False))

    def test_empty_values_allowed(self):
        reception = self.api(self.reception)
        data = reception.save_pet(self.client.id, {
            "name": "Prázdný", "species": "dog", "species_other": "", "breed": "", "sex": "", "birth_date": "",
            "birth_year": "", "chip": "", "tattoo": "", "passport": "", "color": "", "weight": "",
            "next_vaccination": "", "next_deworming": "", "important_note": "", "note": "", "alerts": [],
        })
        row = self.pet_of(data, "Prázdný")
        for key in ("birth_date", "birth_year", "tattoo", "passport", "color", "weight", "next_vaccination",
                    "next_deworming", "important_note", "note", "alerts"):
            self.assertIsNone(row[key], key)
        self.assertEqual(row["alert_list"], [])
        pet = self.env["elite.vet.pet"].browse(row["id"])
        pet.write({"color": "černá", "weight": 7.5, "birth_year": 2018, "next_deworming": date(2027, 2, 2)})
        reception.save_pet(self.client.id, {"color": "", "weight": "", "birth_year": "", "next_deworming": None},
                           pet_id=pet.id)
        self.assertEqual((pet.color, pet.weight, pet.birth_year, pet.next_deworming), (False, 0.0, 0, False))
        # only name and species are required
        reception.save_pet(self.client.id, {"name": "Jen jméno", "species": "rabbit"})
        self.assertIn("Jen jméno", [p["name"] for p in reception.owner_data(self.client.id)["pets"]])

    def test_validation(self):
        reception = self.api(self.reception)
        base = {"name": "Validace", "species": "dog"}
        next_year = clinic_today().year + 1
        bad = [
            {"weight": "-1"}, {"weight": "těžký"}, {"weight": "nan"}, {"weight": "inf"},
            {"birth_year": "1900"}, {"birth_year": str(next_year)}, {"birth_year": "loni"},
            {"next_vaccination": "1. 2. 2027"}, {"next_deworming": "zítra"},
            {"birth_date": "%s-01-01" % next_year},
            {"alerts": [{"kind": "dragon"}]}, {"alerts": "kouše"}, {"alerts": [{"kind": "other", "note": 5}]},
        ]
        for extra in bad:
            with self.assertRaises(UserError, msg=str(extra)):
                reception.save_pet(self.client.id, dict(base, **extra))
        self.assertFalse(self.env["elite.vet.pet"].search([("partner_id", "=", self.client.id)]))
        reception.save_pet(self.client.id, dict(base, weight="0", birth_year=str(clinic_today().year)))
        pet = self.env["elite.vet.pet"].search([("partner_id", "=", self.client.id)])
        self.assertEqual((pet.weight, pet.birth_year), (0.0, clinic_today().year))
        # an alert of another pet cannot be edited through this one
        foreign = self.env["elite.vet.pet.alert"].create({"pet_id": self.pet.id, "kind": "bites", "note": "cizí"})
        with self.assertRaises(UserError):
            reception.save_pet(self.client.id, {"alerts": [{"id": foreign.id, "kind": "other"}]}, pet_id=pet.id)
        self.assertEqual((foreign.kind, foreign.note, foreign.active), ("bites", "cizí", True))

    def test_alerts_add_edit_remove(self):
        reception = self.api(self.reception)
        data = reception.save_pet(self.client.id, {"name": "Upozorňovaný", "species": "cat",
                                                   "alerts": [{"kind": "bites", "note": "náhubek"}]})
        pet = self.env["elite.vet.pet"].browse(self.pet_of(data, "Upozorňovaný")["id"])
        first = pet.alert_ids
        self.assertEqual(len(first), 1)
        # keep and edit the first, add a second
        data = reception.save_pet(self.client.id, {"alerts": [
            {"id": first.id, "kind": "bites", "note": "náhubek, kouše"}, {"kind": "allergy", "note": "pyl"}]},
            pet_id=pet.id)
        self.assertEqual(first.note, "náhubek, kouše")
        self.assertEqual(len(pet.alert_ids), 2)
        self.assertEqual(len(self.pet_of(data, "Upozorňovaný")["alert_list"]), 2)
        # remove the first: archived like in the patient card, the other one stays
        data = reception.save_pet(self.client.id, {"alerts": [
            {"id": a.id, "kind": a.kind, "note": a.note} for a in pet.alert_ids if a != first]}, pet_id=pet.id)
        self.assertFalse(first.active)
        self.assertEqual(self.pet_of(data, "Upozorňovaný")["alerts"], "Alergie: pyl")
        # without the key the alerts are left as they are
        reception.save_pet(self.client.id, {"note": "beze změny upozornění"}, pet_id=pet.id)
        self.assertEqual(len(pet.alert_ids.filtered("active")), 1)
        # empty list removes all
        reception.save_pet(self.client.id, {"alerts": []}, pet_id=pet.id)
        self.assertFalse(pet.alert_ids.filtered("active"))
        # an archived alert cannot be revived through its old id
        with self.assertRaises(UserError):
            reception.save_pet(self.client.id, {"alerts": [{"id": first.id, "kind": "bites"}]}, pet_id=pet.id)

    def test_deceased_only_on_edit(self):
        reception = self.api(self.reception)
        for extra in ({"deceased": True}, {"death_date": "2026-01-01"}):
            with self.assertRaises(UserError):
                reception.save_pet(self.client.id, dict({"name": "Hned uhynulý", "species": "dog"}, **extra))
        self.assertFalse(self.env["elite.vet.pet"].search([("partner_id", "=", self.client.id)]))
        # deceased False on registration is harmless
        data = reception.save_pet(self.client.id, {"name": "Živý", "species": "dog", "deceased": False})
        pet = self.env["elite.vet.pet"].browse(self.pet_of(data, "Živý")["id"])
        with self.assertRaises(UserError):
            reception.save_pet(self.client.id, {"deceased": "ano"}, pet_id=pet.id)
        today = clinic_today()
        data = reception.save_pet(self.client.id, {"deceased": True, "death_date": today.isoformat()}, pet_id=pet.id)
        self.assertEqual((pet.deceased, pet.death_date), (True, today))
        row = self.pet_of(data, "Živý")
        self.assertEqual((row["deceased"], row["death_date"]), (True, today.isoformat()))
        # existing rule: a deceased pet cannot be booked / checked in
        with self.assertRaises(UserError):
            reception.walk_in(pet.id)
        self.assertNotIn(pet.id, [r["id"] for r in reception.booking_search("Zvířete-Testová") if r["kind"] == "pet"])
        with self.assertRaises(UserError):
            reception.save_pet(self.client.id, {"death_date": "%s-01-01" % (today.year + 1)}, pet_id=pet.id)
        # back to live: the death date is cleared
        reception.save_pet(self.client.id, {"deceased": False, "death_date": today.isoformat()}, pet_id=pet.id)
        self.assertEqual((pet.deceased, pet.death_date), (False, False))

    def test_rights(self):
        with self.assertRaises(AccessError):
            self.api(self.outsider).save_pet(self.client.id, {"name": "Cizí", "species": "dog",
                                                              "alerts": [{"kind": "bites"}]})
        with self.assertRaises(AccessError):
            self.api(self.outsider).pet_options()
        # reception may only read alerts directly; the checked API writes them
        with self.assertRaises(AccessError):
            self.env["elite.vet.pet.alert"].with_user(self.reception).create({"pet_id": self.pet.id, "kind": "bites"})
        options = self.api(self.reception).pet_options()
        self.assertEqual([k["value"] for k in options["alert_kinds"]], ["bites", "allergy", "other"])
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            name = "Právo %s" % user.login
            data = self.api(user).save_pet(self.client.id, {
                "name": name, "species": "dog", "weight": "3", "important_note": "pozor",
                "alerts": [{"kind": "other", "note": user.login}]})
            row = self.pet_of(data, name)
            self.assertEqual((row["weight"], row["important_note"], len(row["alert_list"])), (3.0, "pozor", 1))
