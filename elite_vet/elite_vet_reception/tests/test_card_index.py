from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestCardIndex(ReceptionCase):
    """Card index API for owners and pets (Task 2)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role kartotéka", "login": "card_index_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def owner_by_api(self, **vals):
        vals.setdefault("name", "Kartotéka Majitel-Testový")
        return self.api(self.reception).save_owner(vals)

    # ---------------------------------------------------------------- search
    def test_search_by_phone_digits_and_pet_name(self):
        reception = self.api(self.reception)
        by_phone = reception.card_search("602111987")
        pets = [r for r in by_phone if r["kind"] == "pet"]
        self.assertIn(self.pet.id, [r["id"] for r in pets])
        hit = [r for r in pets if r["id"] == self.pet.id][0]
        self.assertEqual(hit["partner_id"], self.owner.id)
        by_name = reception.card_search("Azor Klin")
        self.assertIn(self.pet.id, [r["id"] for r in by_name if r["kind"] == "pet"])

    def test_search_finds_owner_without_pets(self):
        data = self.owner_by_api(name="Bezzvířecí Kartotéková", phone="+420 731 555 101",
                                 email="bezzvireci.karta@example.invalid")
        partner_id = data["owner"]["id"]
        reception = self.api(self.reception)
        for term in ("Bezzvířecí", "731 555 101", "bezzvireci.karta@"):
            owners = [r for r in reception.card_search(term) if r["kind"] == "owner"]
            self.assertIn(partner_id, [r["partner_id"] for r in owners], term)
        owner = [r for r in reception.card_search("Bezzvířecí") if r["kind"] == "owner"][0]
        self.assertEqual(owner["name"], "Bezzvířecí Kartotéková")
        self.assertEqual(owner["phone"], "+420 731 555 101")
        # an owner shown through a pet is not listed twice
        owner_ids = [r["partner_id"] for r in reception.card_search("602111987") if r["kind"] == "owner"]
        self.assertNotIn(self.owner.id, owner_ids)
        self.assertEqual(reception.card_search("x"), [])

    # ---------------------------------------------------------------- owner_data
    def test_owner_data(self):
        self.env["elite.vet.pet.alert"].create({"pet_id": self.pet.id, "kind": "bites", "note": "náhubek"})
        self.pet.next_vaccination = date(2027, 3, 1)
        nurse = self.as_user(self.nurse)
        record = nurse.open_today_record(self.pet.id, force_new=True)
        nurse.add_item(record["id"], self.exam.id)
        nurse.mark_done(record["id"])

        data = self.api(self.reception).owner_data(self.owner.id)
        owner = data["owner"]
        self.assertEqual((owner["id"], owner["name"], owner["phone"], owner["mobile"], owner["email"]),
                         (self.owner.id, self.owner.name, "+420 602 111 987", "777 654 321",
                          "majitelka.clinic@example.invalid"))
        for key in ("street", "city", "zip"):
            self.assertIn(key, owner)
        pet = [p for p in data["pets"] if p["id"] == self.pet.id][0]
        self.assertEqual((pet["name"], pet["species"], pet["species_label"], pet["breed"], pet["sex"]),
                         ("Azor Klinický", "dog", "Pes", "bígl", "pes"))
        self.assertEqual(pet["chip"], "203 098 100 555 777")
        self.assertEqual(pet["next_vaccination"], "2027-03-01")
        self.assertEqual(pet["birth_date"], self.pet.birth_date.isoformat())
        self.assertFalse(pet["deceased"])
        self.assertEqual(pet["alerts"], "Kouše: náhubek")
        bills = [b for b in data["open_bills"] if b["record_id"] == record["id"]]
        self.assertEqual(len(bills), 1)
        self.assertEqual(bills[0]["payment_state_label"], "Čeká na platbu")
        self.assertGreater(bills[0]["amount"], 0)

    def test_owner_data_unknown_owner(self):
        with self.assertRaises(UserError):
            self.api(self.reception).owner_data(999_999_999)

    # ---------------------------------------------------------------- save_owner / save_pet
    def test_create_owner_and_pet(self):
        reception = self.api(self.reception)
        data = reception.save_owner({"name": "  Nová Klientka Kartotéky ", "phone": "604 222 333",
                                     "email": "nova.karta@example.invalid", "street": "Dlouhá 5",
                                     "city": "Brno", "zip": "60200", "comment": "nepovolený klíč"})
        partner = self.env["res.partner"].browse(data["owner"]["id"])
        self.assertTrue(partner.is_vet_client)
        self.assertEqual((partner.name, partner.phone, partner.city, partner.zip),
                         ("Nová Klientka Kartotéky", "604 222 333", "Brno", "60200"))
        self.assertFalse(partner.comment, "keys outside the allowed list are ignored")
        self.assertEqual(data["pets"], [])

        data = reception.save_pet(partner.id, {"name": "Micka", "species": "cat", "breed": "evropská",
                                               "sex": "fena", "birth_date": "2022-05-04", "chip": "123 456",
                                               "note": "plachá"})
        self.assertEqual(len(data["pets"]), 1)
        pet = self.env["elite.vet.pet"].browse(data["pets"][0]["id"])
        self.assertEqual((pet.partner_id, pet.species, pet.birth_date, pet.note),
                         (partner, "cat", date(2022, 5, 4), "plachá"))

        data = reception.save_pet(partner.id, {"breed": "perská", "birth_date": ""}, pet_id=pet.id)
        self.assertEqual((pet.breed, pet.birth_date, pet.name), ("perská", False, "Micka"))
        self.assertEqual(data["pets"][0]["breed"], "perská")

        data = reception.save_owner({"city": "Praha"}, partner_id=partner.id)
        self.assertEqual((data["owner"]["city"], partner.name), ("Praha", "Nová Klientka Kartotéky"))

    def test_save_validation(self):
        reception = self.api(self.reception)
        with self.assertRaises(UserError):
            reception.save_owner({"name": "  ", "phone": "1"})
        with self.assertRaises(UserError):
            reception.save_owner({"name": ""}, partner_id=self.owner.id)
        with self.assertRaises(UserError):
            reception.save_pet(self.owner.id, {"name": "Bez druhu"})
        with self.assertRaises(UserError):
            reception.save_pet(self.owner.id, {"name": "Divný", "species": "dragon"})
        with self.assertRaises(UserError):
            reception.save_pet(self.owner.id, {"name": "Datum", "species": "dog", "birth_date": "32. 13."})
        other = self.env["res.partner"].create({"name": "Cizí Majitel Kartotéky", "is_vet_client": True})
        with self.assertRaises(UserError):
            reception.save_pet(other.id, {"name": "Únos"}, pet_id=self.pet.id)
        self.assertEqual(self.pet.partner_id, self.owner)

    def test_edit_owner_sharing_phone_and_email(self):
        """Review Focus 3: same phone/e-mail as another owner -> saved, no merge, no crash."""
        other = self.env["res.partner"].create({
            "name": "Druhá Majitelka Kartotéky", "phone": "+420 605 444 555",
            "email": "sdileny.karta@example.invalid", "is_vet_client": True})
        reception = self.api(self.reception)
        data = reception.save_owner({"phone": "605 444 555", "email": "sdileny.karta@example.invalid"},
                                    partner_id=self.owner.id)
        self.assertEqual(data["owner"]["phone"], "605 444 555")
        self.assertEqual(self.owner.email, "sdileny.karta@example.invalid")
        self.assertTrue(other.exists())
        self.assertEqual(other.phone, "+420 605 444 555")
        self.assertIn(self.pet.id, [p["id"] for p in data["pets"]])
        self.assertNotIn(self.pet.id, [p.id for p in other.pet_ids])
        new = reception.save_owner({"name": "Třetí se stejným číslem", "phone": "+420 605 444 555"})
        self.assertNotIn(new["owner"]["id"], (self.owner.id, other.id))

    # ---------------------------------------------------------------- rights
    def test_rights(self):
        outsider = self.api(self.outsider)
        with self.assertRaises(AccessError):
            outsider.card_search("Azor")
        with self.assertRaises(AccessError):
            outsider.owner_data(self.owner.id)
        with self.assertRaises(AccessError):
            outsider.save_owner({"name": "Nepovolený"})
        with self.assertRaises(AccessError):
            outsider.save_pet(self.owner.id, {"name": "Nepovolený", "species": "dog"})
        res = self.reservation(9, 0, contact_name="Web Nespárovaný", pet_name="Rex")
        with self.assertRaises(AccessError):
            outsider.match_reservation(res.id, self.owner.id, self.pet.id)
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            self.assertTrue(self.api(user).card_search("Azor Klin"))
            self.assertEqual(self.api(user).owner_data(self.owner.id)["owner"]["id"], self.owner.id)

    # ---------------------------------------------------------------- match_reservation
    def test_match_reservation_then_check_in(self):
        res = self.reservation(9, 30, contact_name="Webová Kartotéka", pet_name="Bobík Web",
                               contact_email="web.karta@example.invalid")
        reception = self.api(self.reception)
        with self.assertRaises(UserError):
            reception.check_in(res.id)
        other = self.env["res.partner"].create({"name": "Cizí Majitel Párování", "is_vet_client": True})
        with self.assertRaises(UserError):
            reception.match_reservation(res.id, other.id, self.pet.id)
        summary = reception.match_reservation(res.id, self.owner.id, self.pet.id)
        self.assertEqual((res.partner_id, res.pet_id), (self.owner, self.pet))
        self.assertEqual((summary["reservation_id"], summary["partner_id"], summary["pet_id"]),
                         (res.id, self.owner.id, self.pet.id))
        self.assertFalse(summary["needs_match"])
        self.assertEqual(summary["time"], "09:30")
        record = reception.check_in(res.id, employee_name="Jana")
        self.assertEqual((record["pet_id"], record["reservation_id"], record["stage"]),
                         (self.pet.id, res.id, "waiting"))

    def test_pet_options(self):
        data = self.api(self.reception).pet_options()
        self.assertIn({"value": "dog", "label": "Pes"}, data["species"])
        with self.assertRaises(AccessError):
            self.api(self.outsider).pet_options()

    # ---------------------------------------------------------------- fix round 1
    def test_staff_and_company_partners_are_not_owners(self):
        reception = self.api(self.reception)
        for partner in (self.nurse.partner_id, self.env.company.partner_id):
            with self.assertRaises(UserError) as err:
                reception.owner_data(partner.id)
            self.assertEqual(err.exception.args[0], "Tento kontakt není klient kliniky.")
            with self.assertRaises(UserError):
                reception.save_owner({"phone": "111 222 333"}, partner_id=partner.id)
            with self.assertRaises(UserError):
                reception.save_pet(partner.id, {"name": "Služební", "species": "dog"})
        self.assertNotEqual(self.nurse.partner_id.phone, "111 222 333")

    def test_existing_non_client_is_not_upgraded(self):
        partner = self.env["res.partner"].create({"name": "Dodavatel Kartotéky"})
        data = self.api(self.reception).save_owner({"city": "Olomouc"}, partner_id=partner.id)
        self.assertEqual(data["owner"]["city"], "Olomouc")
        self.assertFalse(partner.is_vet_client)

    def test_bad_input(self):
        reception = self.api(self.reception)
        for vals in (["name"], "name"):
            with self.assertRaises(UserError):
                reception.save_owner(vals)
        with self.assertRaises(UserError):
            reception.save_owner({"name": {"cs": "Jméno"}})
        with self.assertRaises(UserError):
            reception.save_pet(self.owner.id, {"name": "Datum", "species": "dog", "birth_date": ["2020"]})
        data = reception.save_owner({"name": "Číselná Kartotéka", "zip": 60200})
        self.assertEqual(self.env["res.partner"].browse(data["owner"]["id"]).zip, "60200")
        with self.assertRaises(UserError):
            reception.owner_data("abc")
        with self.assertRaises(UserError):
            reception.card_search(["name"])

    def test_owner_phone_branch_only_for_numbers(self):
        # "Ulice 1234" has 4 digits but is not a number: no phone match on "1234"
        data = self.owner_by_api(name="Telefonní Kartotéka", phone="604 991 234")
        owner_ids = [r["partner_id"] for r in self.api(self.reception).card_search("Ulice 1234")
                     if r["kind"] == "owner"]
        self.assertNotIn(data["owner"]["id"], owner_ids)
        owner_ids = [r["partner_id"] for r in self.api(self.reception).card_search("991 234")
                     if r["kind"] == "owner"]
        self.assertIn(data["owner"]["id"], owner_ids)

    def test_match_reservation_second_room_and_other_pet(self):
        reception = self.api(self.reception)
        res = self.reservation(10, 0, contact_name="Web Druhá Ordinace", pet_name="Dvojka")
        room2 = self.env["elite.vet.room"].create({"name": "Ordinace 2 test kartotéky"})
        second = res.add_second_room(room2)
        summary = reception.match_reservation(second.id, self.owner.id, self.pet.id)
        self.assertEqual(summary["reservation_id"], res.id)
        self.assertEqual((res.pet_id, second.pet_id), (self.pet, self.pet))

        reception.check_in(res.id)
        other_pet = self.new_pet("Jiné Zvíře Kartotéky")
        with self.assertRaises(UserError) as err:
            reception.match_reservation(res.id, self.owner.id, other_pet.id)
        self.assertEqual(err.exception.args[0], "Rezervace už má návštěvu jiného zvířete.")
        self.assertEqual(res.pet_id, self.pet)
