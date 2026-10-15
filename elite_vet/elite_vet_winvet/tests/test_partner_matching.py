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
