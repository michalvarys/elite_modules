from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import WinvetCase


@tagged("post_install", "-at_install")
class TestPartnerMatching(WinvetCase):

    def contacts(self, owner_n, *items, start=100):
        recs = []
        for i, (ctype, value) in enumerate(items):
            recs.append({"id": self.ref(start + owner_n * 10 + i), "owner_id": self.ref(owner_n), "type": ctype,
                         "value": value, "label": None})
        return recs

    def test_link_to_web_client_by_email(self):
        client = self.env["res.partner"].find_or_create_client(
            "Jana z webu", "jana.winvet-test@example.invalid", "+420 600 111 001")
        self.push("owners", [self.owner(1)])
        created = self.find("res.partner", 1)
        self.assertNotEqual(created, client)
        self.assertTrue(created.winvet_merge_pending)
        self.push("contacts", self.contacts(1, (-4, "Jana.Winvet-Test@example.invalid"), (-1, "777 000 001")),
                  mode="full")
        self.assertEqual(self.find("res.partner", 1), client)
        self.assertFalse(created.exists())
        self.assertEqual(client.name, "Testová Jana 1")
        self.assertEqual(client.mobile, "777 000 001")
        self.assertEqual(client.email, "Jana.Winvet-Test@example.invalid")
        self.assertFalse(client.winvet_merge_pending)
        self.assertEqual(len(client.winvet_contact_ids), 2)
        # patients arriving later go to the linked client
        self.push("patients", [self.patient(10, 1)])
        self.assertEqual(self.find("elite.vet.pet", 10).partner_id, client)

    def test_link_by_phone(self):
        client = self.env["res.partner"].find_or_create_client("Petr z webu", "", "+420 600 111 002")
        self.push("owners", [self.owner(2)])
        self.push("contacts", self.contacts(2, (-2, "600111002")), mode="full")
        self.assertEqual(self.find("res.partner", 2), client)
        self.assertEqual(client.phone, "600111002")

    def test_no_link_when_client_has_other_winvet_ref(self):
        client = self.env["res.partner"].find_or_create_client(
            "Jiná", "jina.winvet-test@example.invalid", "")
        client.winvet_ref = str(self.ref(99))
        self.push("owners", [self.owner(3)])
        self.push("contacts", self.contacts(3, (-4, "jina.winvet-test@example.invalid")), mode="full")
        partner = self.find("res.partner", 3)
        self.assertNotEqual(partner, client)
        self.assertEqual(client.winvet_ref, str(self.ref(99)))
        self.assertEqual(partner.email, "jina.winvet-test@example.invalid")

    def test_no_link_for_non_client_partner(self):
        other = self.env["res.partner"].create({"name": "Dodavatel", "email": "dodavatel.winvet-test@example.invalid"})
        self.push("owners", [self.owner(4)])
        self.push("contacts", self.contacts(4, (-4, "dodavatel.winvet-test@example.invalid")), mode="full")
        self.assertNotEqual(self.find("res.partner", 4), other)
        self.assertFalse(other.winvet_ref)

    def test_matching_only_in_the_creating_run(self):
        self.push("owners", [self.owner(5)])
        self.push("contacts", self.contacts(5, (-1, "+420 600 111 005")), mode="full", run_id="r1")
        partner = self.find("res.partner", 5)
        self.assertFalse(partner.winvet_merge_pending)
        client = self.env["res.partner"].find_or_create_client("Pozdější", "pozdejsi.winvet-test@example.invalid", "")
        self.push("contacts", self.contacts(5, (-1, "+420 600 111 005"), (-4, "pozdejsi.winvet-test@example.invalid")),
                  mode="full", run_id="r2")
        self.assertEqual(self.find("res.partner", 5), partner)
        self.assertFalse(client.winvet_ref)

    def test_contacts_overwrite_but_do_not_clear(self):
        self.push("owners", [self.owner(6)])
        self.push("contacts", self.contacts(6, (-4, "a.winvet-test@example.invalid"), (-4, "b.winvet-test@example.invalid"),
                                            (-2, "353 000 006"), (-5, "www.example.invalid")), mode="full")
        partner = self.find("res.partner", 6)
        self.assertEqual(partner.email, "a.winvet-test@example.invalid")
        self.assertEqual(partner.phone, "353 000 006")
        self.assertFalse(partner.mobile)
        partner.mobile = "+420 600 999 006"
        self.push("contacts", self.contacts(6, (-4, "a.winvet-test@example.invalid")), mode="full", run_id="r3")
        self.assertEqual(partner.mobile, "+420 600 999 006")
        self.assertEqual(partner.phone, "353 000 006", "missing WinVet value does not clear Odoo")
        types = partner.with_context(active_test=False).winvet_contact_ids.filtered("active").mapped("type")
        self.assertEqual(types, ["email"], "contacts missing from the full run are archived")


@tagged("post_install", "-at_install")
class TestClientInWinvet(WinvetCase):
    """Reception marks a client as "Je ve WinVetu": no contact, the sync pairs them later."""

    def setUp(self):
        super().setUp()
        self.today = fields.Date.to_string(fields.Date.today())
        self.Partner = self.env["res.partner"]

    def waiting(self, name="Jana Testová"):
        return self.Partner.client_in_winvet(name, "", "")

    def new_owner(self, n=1, name="Testová Jana", **over):
        return self.owner(n, name=name, created=self.today, **over)

    def pair(self, owner=None, contacts=()):
        self.push("owners", [owner or self.new_owner()])
        self.push("contacts", list(contacts))

    def test_paired_by_name_and_contact_filled_in(self):
        client = self.waiting()
        self.assertTrue(client.winvet_pairing_pending)
        res = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "partner_id": client.id, "contact_name": client.name,
            "room_id": self.env["elite.vet.room"].create({"name": "Pár T"}).id,
            "start": fields.Datetime.now() + timedelta(days=3)})
        self.pair(contacts=[{"id": self.ref(100), "owner_id": self.ref(1), "type": -4, "label": None,
                             "value": "jana.par@example.invalid"}])
        owner = self.find("res.partner", 1)
        self.assertFalse(client.exists())
        self.assertEqual(res.partner_id, owner)
        self.assertEqual(res.contact_email, "jana.par@example.invalid")
        self.assertFalse(owner.winvet_pairing_pending)

    def test_second_booking_finds_the_waiting_client(self):
        self.assertEqual(self.waiting(), self.waiting("Testová Jana"))

    def test_same_names_stay_waiting(self):
        client = self.waiting()
        self.push("owners", [self.new_owner(1), self.new_owner(2)])
        self.push("contacts", [])
        self.assertTrue(client.exists() and client.winvet_pairing_pending)

    def test_old_owner_of_the_name_needs_the_pet(self):
        client = self.waiting()
        self.env["elite.vet.pet"].create({"name": "Bella", "partner_id": client.id, "species": "dog"})
        self.pair(self.owner(1, name="Testová Jana", created="2020-01-02"))
        self.push("patients", [self.patient(10, 1, name="Azor")])
        self.assertTrue(client.exists(), "an old namesake with another pet is someone else")
        self.push("patients", [self.patient(11, 1, name="Bella")])
        self.assertFalse(client.exists())

    def test_pet_created_here_takes_the_winvet_id(self):
        client = self.waiting()
        pet = self.env["elite.vet.pet"].create({"name": "Bella", "partner_id": client.id, "species": "dog"})
        self.pair()
        self.push("patients", [self.patient(10, 1, name="BELLA")])
        self.assertEqual(self.find("elite.vet.pet", 10), pet)
        self.assertEqual(pet.partner_id, self.find("res.partner", 1))

    def test_pet_already_synced_replaces_the_one_created_here(self):
        self.push("owners", [self.new_owner()])
        self.push("patients", [self.patient(10, 1, name="Bella")])
        twin = self.find("elite.vet.pet", 10)
        client = self.waiting()
        pet = self.env["elite.vet.pet"].create({"name": "Bella", "partner_id": client.id, "species": "dog"})
        res = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "partner_id": client.id, "pet_id": pet.id,
            "contact_name": client.name, "room_id": self.env["elite.vet.room"].create({"name": "Pár T2"}).id,
            "start": fields.Datetime.now() + timedelta(days=3)})
        self.push("contacts", [])
        self.assertFalse(pet.exists())
        self.assertEqual(res.pet_id, twin)

    def test_unmarked_client_is_not_paired_by_name(self):
        client = self.Partner.find_or_create_client("Testová Jana", "jina.par@example.invalid", "")
        self.pair()
        self.assertTrue(client.exists())
