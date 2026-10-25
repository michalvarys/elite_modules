"""Request 25. 10.: Nedorazil recorded on the client and the pet (computed, last 12 months)."""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestNoShow(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["res.partner"].create({"name": "Nechodící Klient T22", "is_vet_client": True})
        cls.pet = cls.env["elite.vet.pet"].create({"name": "Bobík T22", "partner_id": cls.client.id, "species": "dog"})
        cls.other_pet = cls.env["elite.vet.pet"].create({"name": "Micka T22", "partner_id": cls.client.id,
                                                         "species": "cat"})
        cls.today = fields.Date.today()

    def no_show(self, days_ago, pet=None, hour=9):
        r = self.reservation(start=self.dt(self.today - timedelta(days=days_ago), hour, 0),
                             partner_id=self.client.id, pet_id=(pet or self.pet).id)
        r.action_no_show()
        return r

    def test_summary_counts_the_last_12_months(self):
        self.no_show(10)
        self.no_show(40, pet=self.other_pet)
        self.no_show(400)                       # older than 12 months
        ok = self.reservation(start=self.dt(self.today - timedelta(days=5), 9, 0),
                              partner_id=self.client.id, pet_id=self.pet.id)
        ok.action_done()
        R = self.env["elite.vet.reservation"]
        summary = R.no_show_summary(partner=self.client)
        self.assertEqual(summary["count"], 2)
        day = self.today - timedelta(days=10)
        self.assertEqual(summary["last_date"], day.isoformat())
        self.assertEqual(summary["text"], "Klient 2× nedorazil, naposledy %d. %d." % (day.day, day.month))
        self.assertEqual([i["pet"] for i in summary["items"]], ["Bobík T22", "Micka T22"])
        self.assertEqual(summary["items"][0]["procedure"], "Vaccination")
        self.assertEqual(R.no_show_summary(pet=self.other_pet)["count"], 1)
        self.assertEqual(R.no_show_summary()["count"], 0)
        # smart buttons
        self.assertEqual(self.client.no_show_count, 2)
        self.assertEqual((self.pet.no_show_count, self.other_pet.no_show_count), (1, 1))
        action = self.client.action_view_no_shows()
        self.assertEqual(R.search(action["domain"]).mapped("state"), ["no_show", "no_show"])

    def test_second_room_copy_counted_once(self):
        main = self.reservation(start=self.dt(self.today + timedelta(days=1), 9, 0), doctor_id=self.dr_a.id,
                                partner_id=self.client.id, pet_id=self.pet.id)
        main.add_second_room(self.room2, self.dr_b)
        main.write({"start": self.dt(self.today - timedelta(days=2), 9, 0),
                    "stop": self.dt(self.today - timedelta(days=2), 9, 15)})
        main.action_no_show()
        self.assertEqual(main.linked_reservation_id.state, "no_show")
        self.assertEqual(self.env["elite.vet.reservation"].no_show_summary(partner=self.client)["count"], 1)

    def test_wizard_warns(self):
        self.no_show(3)
        wizard = self.env["elite.vet.reservation.wizard"].create({
            "procedure_id": self.vacc.id, "date": self.today + timedelta(days=3)})
        wizard.write({"step": "client", "partner_mode": "existing", "partner_id": self.client.id})
        self.assertIn("Klient 1× nedorazil, naposledy", wizard.no_show_warning)
        wizard.partner_id = self.env["res.partner"].create({"name": "Spolehlivá T22", "is_vet_client": True})
        self.assertFalse(wizard.no_show_warning)
        wizard.write({"partner_mode": "new", "partner_id": self.client.id})
        self.assertFalse(wizard.no_show_warning)   # a new client has no history
        view = self.env.ref("elite_vet_reservation.view_reservation_wizard_form")
        self.assertIn("o_ev_no_show_warning", view.arch)
