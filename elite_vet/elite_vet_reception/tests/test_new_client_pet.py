"""Task 31: Nový klient of the Kartotéka dialog has the full pet form – the client and the pet
(every field, alerts) are saved in one call (save_owner with pet_vals), all or nothing.
Synthetic data only."""
from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools.misc import file_open

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_winvet.models.winvet_calendar import PARAM_ENABLED

from .common import ReceptionCase

FULL_PET = {
    "name": "Fretka T31", "species": "other", "species_other": "fretka", "breed": "albín", "sex": "samice",
    "birth_date": "2021-04-03", "birth_year": "2021", "chip": "931 000", "tattoo": "T31", "passport": "CZ-T31",
    "color": "bílá", "weight": "1,25", "next_vaccination": "2027-01-15", "next_deworming": "2026-12-01",
    "important_note": "kouše při odběru", "note": "plachá",
    "alerts": [{"kind": "allergy", "note": "penicilin"}, {"kind": "bites", "note": ""}],
}


@tagged("post_install", "-at_install")
class TestNewClientPet(ReceptionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role T31", "login": "new_client_pet_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def partners(self, name):
        return self.env["res.partner"].with_context(active_test=False).search([("name", "=", name)])

    def test_owner_and_pet_with_every_field_in_one_save(self):
        data = self.api(self.reception).save_owner(
            {"name": "Klientka T31 Úplná", "phone": "604 931 000", "city": "Brno"}, False, dict(FULL_PET))
        partner = self.env["res.partner"].browse(data["owner"]["id"])
        self.assertEqual((partner.name, partner.phone, partner.city, partner.is_vet_client),
                         ("Klientka T31 Úplná", "604 931 000", "Brno", True))
        self.assertEqual(len(data["pets"]), 1)
        pet = self.env["elite.vet.pet"].browse(data["new_pet_id"])
        self.assertEqual(data["pets"][0]["id"], pet.id)
        self.assertEqual(
            (pet.partner_id, pet.species, pet.species_other, pet.breed, pet.sex, pet.birth_date, pet.birth_year,
             pet.chip, pet.tattoo, pet.passport, pet.color, pet.weight, pet.next_vaccination, pet.next_deworming,
             pet.important_note, pet.note, pet.deceased),
            (partner, "other", "fretka", "albín", "samice", date(2021, 4, 3), 2021, "931 000", "T31", "CZ-T31",
             "bílá", 1.25, date(2027, 1, 15), date(2026, 12, 1), "kouše při odběru", "plachá", False))
        self.assertEqual(sorted(pet.alert_ids.mapped("kind")), ["allergy", "bites"])
        self.assertIn("Alergie: penicilin", data["pets"][0]["alerts"])
        # only name and species of the pet; without pet_vals the old behaviour (owner only)
        data = self.api(self.reception).save_owner({"name": "Klient T31 Krátký"}, False,
                                                   {"name": "Rex T31", "species": "dog"})
        self.assertEqual([p["name"] for p in data["pets"]], ["Rex T31"])
        data = self.api(self.reception).save_owner({"name": "Klient T31 Bez zvířete"})
        self.assertEqual(data["pets"], [])
        self.assertNotIn("new_pet_id", data)

    def test_refused_pet_creates_nothing(self):
        today = clinic_today()
        bad = (
            {"name": "", "species": "dog"},                                        # no name
            {"name": "Bez druhu T31"},                                              # no species
            {"name": "Drak T31", "species": "dragon"},                              # unknown species
            {"name": "Těžký T31", "species": "dog", "weight": "hodně"},             # weight
            {"name": "Starý T31", "species": "dog", "birth_year": "1800"},          # year
            {"name": "Budoucí T31", "species": "dog", "birth_date": (today + timedelta(days=1)).isoformat()},
            {"name": "Uhynulý T31", "species": "dog", "deceased": True},            # never on registration
            {"name": "Úhyn T31", "species": "dog", "death_date": today.isoformat()},
            {"name": "Alergie T31", "species": "dog", "alerts": [{"kind": "nonsense"}]},
            {"name": "Alergie T31", "species": "dog", "alerts": "penicilin"},
        )
        pets_before = self.env["elite.vet.pet"].search_count([])
        for index, pet_vals in enumerate(bad):
            name = "Klient T31 Odmítnutý %s" % index
            with self.subTest(pet=pet_vals), self.assertRaises(UserError):
                self.api(self.reception).save_owner({"name": name, "phone": "604 931 999"}, False, pet_vals)
            self.assertFalse(self.partners(name), "the owner is rolled back with the refused pet")
        self.assertEqual(self.env["elite.vet.pet"].search_count([]), pets_before)
        # the owner itself refused: nothing either
        with self.assertRaises(UserError):
            self.api(self.reception).save_owner({"name": "  "}, False, {"name": "Sirotek T31", "species": "dog"})
        self.assertFalse(self.env["elite.vet.pet"].search([("name", "=", "Sirotek T31")]))
        # pet values only with a new owner
        with self.assertRaises(UserError):
            self.api(self.reception).save_owner({"city": "Praha"}, self.owner.id, {"name": "X T31", "species": "dog"})
        with self.assertRaises(UserError):
            self.api(self.reception).save_owner({"name": "Klient T31 Divný"}, False, "Rex")
        self.assertFalse(self.partners("Klient T31 Divný"))
        # the transaction goes on normally after a refusal
        data = self.api(self.reception).save_owner({"name": "Klient T31 Po chybě"}, False,
                                                   {"name": "Opravený T31", "species": "cat"})
        self.assertEqual(data["pets"][0]["name"], "Opravený T31")

    def test_rights(self):
        with self.assertRaises(AccessError):
            self.api(self.outsider).save_owner({"name": "Nepovolený T31"}, False, {"name": "Nic", "species": "dog"})
        self.assertFalse(self.partners("Nepovolený T31"))
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            data = self.api(user).save_owner({"name": "Klient T31 %s" % user.login}, False,
                                             {"name": "Pes T31 %s" % user.login, "species": "dog"})
            self.assertTrue(data["new_pet_id"])

    def test_every_mode_after_the_combined_save(self):
        """What each mode of the dialog does next works with the client and pet of one save."""
        api = self.api(self.reception)

        def new(tag):
            data = api.save_owner({"name": "Klient T31 %s" % tag}, False,
                                  {"name": "Zvíře T31 %s" % tag, "species": "dog", "alerts": [{"kind": "bites"}]})
            return data["owner"]["id"], data["new_pet_id"]

        # browse / order: the owner card (order: the partner of the open order)
        partner_id, pet_id = new("browse")
        self.assertEqual(api.owner_data(partner_id)["pets"][0]["id"], pet_id)
        self.assertTrue(self.env["res.partner"].browse(partner_id).is_vet_client)
        # booking: the pet is offered by the inline search and is bookable
        partner_id, pet_id = new("booking")
        self.assertIn(pet_id, [r["id"] for r in api.booking_search("Zvíře T31 booking") if r["kind"] == "pet"])
        api._check_bookable_pet(self.env["elite.vet.pet"].browse(pet_id))
        # reservation: Přiřadit k rezervaci
        partner_id, pet_id = new("reservation")
        res = self.reservation(9, 0, contact_name="Web T31", pet_name="Zvíře T31 reservation")
        api.match_reservation(res.id, partner_id, pet_id)
        self.assertEqual((res.partner_id.id, res.pet_id.id), (partner_id, pet_id))
        # walk_in: Přijmout
        partner_id, pet_id = new("walk_in")
        record = self.env["elite.vet.clinical.record"].browse(api.walk_in(pet_id)["record_id"])
        self.assertEqual((record.pet_id.id, record.visit_stage), (pet_id, "waiting"))
        # winvet: Uložit a přiřadit k objednávce = save_owner + pair_winvet
        self.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1")
        resource = self.env["elite.vet.winvet.calendar.resource"].create({
            "winvet_ref": 9_310_001, "name": "Synthetic calendar T31", "visible": True, "room_id": self.room.id})
        start = self.today_utc(10)
        event = self.env["elite.vet.winvet.calendar.event"].create({
            "key": "t31-1", "start": start, "stop": start + timedelta(minutes=30),
            "resource_ids": [(6, 0, resource.ids)], "title": "Klient T31 winvet - pes - očkování"})
        partner_id, pet_id = new("winvet")
        api.pair_winvet(event.id, partner_id, pet_id)
        self.assertEqual(event.effective_pet_id.id, pet_id)

    def test_dialog_reuses_the_pet_form(self):
        with file_open("elite_vet_reception/static/src/pos/card_index_dialog/card_index_dialog.xml") as f:
            xml = f.read()
        self.assertEqual(xml.count('t-call="elite_vet_reception.CardIndexPetFields"'), 2)
        fields = xml.split('t-name="elite_vet_reception.CardIndexPetFields"')[1].split("</t>\n\n")[0]
        self.assertIn("Další údaje", fields)
        self.assertIn("Upozornění", fields)
        self.assertNotIn("Uhynulý", fields)   # Uhynulý only when editing a pet
        self.assertIn("Uložit klienta", xml)
        self.assertNotIn("firstPet", xml)
        with file_open("elite_vet_reception/static/src/pos/card_index_dialog/card_index_dialog.js") as f:
            js = f.read()
        self.assertIn("Uložit a přiřadit k objednávce", js)
        self.assertIn('"save_owner", args', js)
