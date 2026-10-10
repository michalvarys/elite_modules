from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import ReservationCase

D = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestReservation(ReservationCase):
    # Pozn.: soubeh dvou transakci (zamek ordinace pod REPEATABLE READ) tu testovat nejde,
    # testy sdili jeden kurzor pod savepointem a druhy skutecny kurzor by se o zamek zablokoval.

    def test_stop_defaults_to_start_plus_duration(self):
        r = self.reservation(start=self.dt(D, 9, 0))
        self.assertEqual(r.stop, self.dt(D, 9, 15))
        self.assertEqual(r.duration_minutes, 15)

    def test_name_from_contact_pet_procedure(self):
        r = self.reservation(start=self.dt(D, 9, 0))
        self.assertEqual(r.name, "Test Klient / Rex / Vaccination")

    def test_cancel_token_is_unique_and_set(self):
        a = self.reservation(start=self.dt(D, 9, 0))
        b = self.reservation(start=self.dt(D, 10, 0))
        self.assertTrue(a.cancel_token and b.cancel_token)
        self.assertNotEqual(a.cancel_token, b.cancel_token)

    def test_confirmed_overlap_same_room_refused(self):
        self.reservation(start=self.dt(D, 9, 0))
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(D, 9, 10))

    def test_confirmed_overlap_other_room_ok(self):
        self.reservation(start=self.dt(D, 9, 0))
        self.reservation(start=self.dt(D, 9, 0), room_id=self.room2.id)

    def test_web_new_may_overlap_web_new_but_not_confirmed(self):
        self.reservation(start=self.dt(D, 9, 0), state="web_new", source="web", room_id=False)
        self.reservation(start=self.dt(D, 9, 0), state="web_new", source="web", room_id=False)
        self.reservation(start=self.dt(D, 11, 0))
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(D, 11, 0), state="web_new", source="web", room_id=self.room1.id)

    def test_confirm_second_fails(self):
        a = self.reservation(start=self.dt(D, 9, 0), state="web_new", source="web")
        b = self.reservation(start=self.dt(D, 9, 0), state="web_new", source="web")
        a.action_confirm()
        self.assertEqual(a.state, "confirmed")
        with self.assertRaises(ValidationError):
            b.action_confirm()

    def test_confirm_requires_room(self):
        r = self.reservation(start=self.dt(D, 9, 0), state="web_new", source="web", room_id=False)
        with self.assertRaises(UserError):
            r.action_confirm()

    def test_global_block_refuses_existing_reservation(self):
        self.reservation(start=self.dt(D, 12, 0))
        with self.assertRaises(ValidationError):
            self.env["elite.vet.reservation"].create({
                "kind": "block", "block_reason": "Oběd", "room_id": False,
                "start": self.dt(D, 12, 0), "stop": self.dt(D, 13, 0)})

    def test_global_block_blocks_every_room(self):
        self.env["elite.vet.reservation"].create({
            "kind": "block", "block_reason": "Oběd", "room_id": False,
            "start": self.dt(D, 12, 0), "stop": self.dt(D, 13, 0)})
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(D, 12, 30), room_id=self.room2.id)

    def test_cancelled_block_no_longer_blocks(self):
        blk = self.env["elite.vet.reservation"].create({
            "kind": "block", "block_reason": "Oběd", "room_id": self.room1.id,
            "start": self.dt(D, 12, 0), "stop": self.dt(D, 13, 0)})
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(D, 12, 30))
        blk.action_cancel()
        self.reservation(start=self.dt(D, 12, 30))

    def test_block_repeat_weekly(self):
        self.env["elite.vet.reservation"].create({
            "kind": "block", "block_reason": "Oběd", "room_id": self.room1.id,
            "start": self.dt(D, 12, 0), "stop": self.dt(D, 13, 0),
            "repeat_weekly_until": date(2026, 11, 4)})
        copies = self.env["elite.vet.reservation"].search([("block_reason", "=", "Oběd"), ("kind", "=", "block")])
        self.assertEqual(len(copies), 4)   # 14.10, 21.10, 28.10, 4.11
        # 25.10.2026 se meni cas: kopie musi zustat ve 12:00 mistniho casu
        self.assertEqual(copies.sorted("start")[-1].start, self.dt(date(2026, 11, 4), 12, 0))

    def test_cancel_and_reschedule(self):
        r = self.reservation(start=self.dt(D, 9, 0))
        r.action_reschedule(self.dt(D, 10, 0), room_id=self.room2.id)
        self.assertEqual((r.start, r.room_id), (self.dt(D, 10, 0), self.room2))
        r.action_cancel("client")
        self.assertEqual((r.state, r.cancel_reason), ("cancelled", "client"))
        self.reservation(start=self.dt(D, 10, 0), room_id=self.room2.id)   # zrusena uz neblokuje

    def test_sparovat_creates_partner_and_pet(self):
        r = self.reservation(start=self.dt(D, 9, 0), contact_email="novy@example.cz", pet_name="Fík", pet_species="cat")
        r.action_sparovat()
        self.assertTrue(r.partner_id.is_vet_client)
        self.assertEqual(r.partner_id.email, "novy@example.cz")
        self.assertEqual((r.pet_id.name, r.pet_id.species), ("Fík", "cat"))
        self.assertIn(r, r.partner_id.reservation_ids)
