"""Request 25. 10.: Nedorazil in the till (Kartotéka owner card, Objednat warning)."""
from datetime import timedelta

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestNoShowInTheTill(ReceptionCase):

    def test_owner_card_and_booking_warning(self):
        owner = self.env["res.partner"].create({"name": "Zapomnětlivý T22", "phone": "+420 777 222 333"})
        pet = self.new_pet("Zapomenutý", owner=owner)
        res = self.reservation(9, 0, pet=pet, start=self.today_utc(9) - timedelta(days=7),
                               stop=self.today_utc(9, 20) - timedelta(days=7))
        res.action_no_show()
        reception = self.api(self.reception)
        data = reception.owner_data(owner.id)
        self.assertEqual(data["no_shows"]["count"], 1)
        self.assertTrue(data["no_shows"]["text"].startswith("Klient 1× nedorazil, naposledy "))
        self.assertEqual(data["no_shows"]["items"][0]["pet"], "Zapomenutý")
        self.assertEqual([p["no_show_count"] for p in data["pets"] if p["id"] == pet.id], [1])
        self.assertEqual(reception.client_no_shows(owner.id)["count"], 1)
        self.assertEqual(reception.client_no_shows(self.owner.id)["count"], 0)
        # task 33: the WinVet deposit balance of the client (reception sees only the sum)
        self.assertIsNone(data["owner"]["deposit_text"])
        self.env["elite.vet.deposit"].sudo().create({"winvet_ref": 9_330_002, "partner_id": owner.id,
                                                     "amount": 2000, "used": 500, "balance": 1500})
        self.assertEqual(reception.owner_data(owner.id)["owner"]["deposit_text"], "1\u00a0500,00\u00a0Kč")
        outsider = self.env["res.users"].create({
            "name": "Bez recepce T22 NS", "login": "t22_no_reception_ns",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.api(outsider).client_no_shows(owner.id)
