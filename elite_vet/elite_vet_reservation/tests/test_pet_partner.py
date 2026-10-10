from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestPetPartner(ReservationCase):

    def test_find_by_email_case_insensitive(self):
        p = self.env["res.partner"].create({"name": "Jana Nová", "email": "Jana@Example.cz"})
        found = self.env["res.partner"].najit_nebo_zalozit_klienta("J. Nova", "jana@example.cz", "")
        self.assertEqual(found, p)
        self.assertTrue(found.is_vet_client)

    def test_find_by_phone_last_nine_digits(self):
        p = self.env["res.partner"].create({"name": "Petr", "phone": "+420 722 599 699"})
        found = self.env["res.partner"].najit_nebo_zalozit_klienta("Petr", "", "722599699")
        self.assertEqual(found, p)

    def test_create_new_when_unknown(self):
        found = self.env["res.partner"].najit_nebo_zalozit_klienta("Nový Klient", "novy@example.cz", "+420111222333")
        self.assertEqual(found.name, "Nový Klient")
        self.assertEqual(found.email, "novy@example.cz")
        self.assertTrue(found.is_vet_client)

    def test_pet_match_by_owner_and_name(self):
        p = self.env["res.partner"].create({"name": "Majitel"})
        pet = self.env["elite.vet.pet"].create({"name": "Teddy", "partner_id": p.id, "species": "dog"})
        self.assertEqual(self.env["elite.vet.pet"].najit_nebo_zalozit(p, "teddy", "dog"), pet)
        other = self.env["elite.vet.pet"].najit_nebo_zalozit(p, "Micka", "cat")
        self.assertNotEqual(other, pet)
        self.assertEqual(other.species, "cat")

    def test_normalize_phone(self):
        from odoo.addons.elite_vet_reservation.models.pet import normalizuj_telefon
        self.assertEqual(normalizuj_telefon("+420 722-599 699"), "420722599699")
