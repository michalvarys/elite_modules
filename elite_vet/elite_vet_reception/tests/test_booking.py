from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_reservation.wizard.reservation_wizard import ReservationWizard

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestBooking(ReceptionCase):
    """Booking API on top of the reservation wizard (Task 3)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15,
            "booking_block_weekends": False, "booking_block_holidays": False})
        cls.room2 = cls.env["elite.vet.room"].create({"name": "Ordinace test recepce 2"})
        for room in (cls.room, cls.room2):
            for weekday in range(7):
                cls.env["elite.vet.room.hours"].create({
                    "room_id": room.id, "weekday": str(weekday), "hour_from": 8.0, "hour_to": 12.0})
        cls.doctor.accepts_bookings = True
        cls.book_proc = cls.env["elite.vet.procedure"].create({
            "name": "Objednání test recepce", "duration": 20, "symbol": "O", "color": "green",
            "room_ids": [(6, 0, [cls.room.id, cls.room2.id])]})
        cls.day = clinic_today() + timedelta(days=10)
        cls.env["elite.vet.doctor.assignment"].create({
            "doctor_id": cls.doctor.id, "room_id": cls.room.id, "date": cls.day,
            "hour_from": 8.0, "hour_to": 12.0})
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role objednání", "login": "booking_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def wizard_lines(self, procedure, day, doctor=None):
        """The free-time lines the reservation wizard offers for the same input."""
        w = self.env["elite.vet.reservation.wizard"].with_user(self.reception).create({
            "procedure_id": procedure.id, "date": day, "doctor_id": doctor.id if doctor else False})
        w.action_step_time()
        return [(ln.minute, ln.room_id.id, ln.doctor_id.id or False) for ln in w.slot_ids]

    def booked(self, partner):
        return self.env["elite.vet.reservation"].search([
            ("partner_id", "=", partner.id), ("procedure_id", "=", self.book_proc.id),
            ("is_second_room", "=", False)])

    # ---------------------------------------------------------------- options
    def test_booking_options(self):
        data = self.api(self.reception).booking_options()
        proc = [p for p in data["procedures"] if p["id"] == self.book_proc.id]
        self.assertEqual(proc, [{"id": self.book_proc.id, "name": "Objednání test recepce", "duration": 20}])
        self.assertIn({"id": self.doctor.id, "name": self.doctor.name}, data["doctors"])
        with self.assertRaises(AccessError):
            self.api(self.outsider).booking_options()

    # ---------------------------------------------------------------- free slots
    def test_free_slots_match_the_wizard(self):
        reception = self.api(self.reception)
        for doctor in (None, self.doctor):
            data = reception.free_slots(self.book_proc.id, self.day.isoformat(), doctor.id if doctor else False)
            self.assertEqual(data["day"], self.day.isoformat())
            self.assertEqual([(s["minute"], s["room_id"], s["doctor_id"]) for s in data["slots"]],
                             self.wizard_lines(self.book_proc, self.day, doctor))
            self.assertTrue(data["slots"])
        nine = [s for s in reception.free_slots(self.book_proc.id, self.day.isoformat())["slots"]
                if s["minute"] == 9 * 60 and s["room_id"] == self.room.id][0]
        self.assertEqual(nine, {"time": "9:00", "minute": 540, "room_id": self.room.id, "room": self.room.name,
                                "doctor_id": self.doctor.id, "doctor": self.doctor.name})
        # with the doctor filter only her room is offered
        mine = reception.free_slots(self.book_proc.id, self.day.isoformat(), self.doctor.id)["slots"]
        self.assertEqual({s["room_id"] for s in mine}, {self.room.id})

    def test_free_slots_next_free_day(self):
        reception = self.api(self.reception)
        data = reception.free_slots(self.book_proc.id, self.day.isoformat())
        self.assertEqual(data["next_free_day"], (self.day + timedelta(days=1)).isoformat())
        # a procedure whose only room has no opening hours: nothing free, no next free day
        closed = self.env["elite.vet.room"].create({"name": "Zavřená ordinace test recepce"})
        proc = self.env["elite.vet.procedure"].create({
            "name": "Nikdy test recepce", "duration": 20, "symbol": "N", "color": "red",
            "room_ids": [(6, 0, [closed.id])]})
        data = reception.free_slots(proc.id, self.day.isoformat())
        self.assertEqual((data["slots"], data["next_free_day"]), ([], None))

    def test_free_slots_bad_input(self):
        reception = self.api(self.reception)
        with self.assertRaises(UserError):
            reception.free_slots(self.book_proc.id, "zítra")
        with self.assertRaises(UserError):
            reception.free_slots(0, self.day.isoformat())
        with self.assertRaises(AccessError):
            self.api(self.outsider).free_slots(self.book_proc.id, self.day.isoformat())

    # ---------------------------------------------------------------- book
    def test_book_creates_one_confirmed_reservation(self):
        reception = self.api(self.reception)
        result = reception.book(self.pet.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id,
                                self.doctor.id, note="Přinese očkovací průkaz")
        res = self.booked(self.owner)
        self.assertEqual(len(res), 1)
        self.assertEqual(result["reservation_id"], res.id)
        self.assertIn("9:00", result["label"])
        self.assertEqual((res.state, res.kind, res.source), ("confirmed", "reservation", "internal"))
        self.assertEqual((res.partner_id, res.pet_id, res.room_id, res.doctor_id),
                         (self.owner, self.pet, self.room, self.doctor))
        A = self.env["elite.vet.availability"]
        self.assertEqual(res.start, A.local_to_utc(self.day, 540))
        self.assertEqual(res.stop, A.local_to_utc(self.day, 560))
        self.assertEqual((res.contact_name, res.contact_email), (self.owner.name, self.owner.email))
        self.assertEqual(res.note, "Přinese očkovací průkaz")
        # the owner has an e-mail: the wizard's rule sends the confirmation (queued, not sent)
        self.assertTrue(self.env["mail.mail"].search([("email_to", "ilike", self.owner.email)]))
        # the slot is no longer offered
        slots = reception.free_slots(self.book_proc.id, self.day.isoformat())["slots"]
        self.assertNotIn((540, self.room.id), [(s["minute"], s["room_id"]) for s in slots])

    def test_book_without_doctor_takes_the_one_on_duty(self):
        result = self.api(self.reception).book(self.pet.id, self.book_proc.id, self.day.isoformat(), 600,
                                               self.room.id)
        res = self.env["elite.vet.reservation"].browse(result["reservation_id"])
        self.assertEqual(res.doctor_id, self.doctor)

    def test_book_owner_without_email_sends_nothing(self):
        owner = self.env["res.partner"].create({"name": "Bez e-mailu Objednaná", "phone": "+420 731 000 222",
                                                "is_vet_client": True})
        pet = self.new_pet("Bezmailový", owner)
        result = self.api(self.reception).book(pet.id, self.book_proc.id, self.day.isoformat(), 540,
                                               self.room2.id)
        res = self.env["elite.vet.reservation"].browse(result["reservation_id"])
        self.assertEqual((res.partner_id, res.pet_id, res.contact_phone), (owner, pet, "+420 731 000 222"))
        self.assertFalse(res.contact_email)

    def test_double_booking_raises_clear_error(self):
        """Review Focus 4: a slot taken in the meantime -> Czech UserError with the time."""
        reception = self.api(self.reception)
        reception.book(self.pet.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
        other = self.new_pet("Druhý objednaný")
        with self.assertRaisesRegex(UserError, "Termín 9:00 už mezitím někdo obsadil – vyberte jiný."):
            reception.book(other.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
        self.assertEqual(len(self.booked(self.owner)), 1)

    def test_overlap_at_save_time_is_converted(self):
        """The slot looked free, but the reservation's overlap check refused it at save time."""
        reception = self.api(self.reception)
        blocker = self.new_pet("Blokující")
        reception.book(blocker.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
        pair = (self.room.id, self.doctor.id)
        with patch.object(ReservationWizard, "_free_room_doctor", lambda w: pair), \
                self.assertRaisesRegex(UserError, "Termín 9:10 už mezitím někdo obsadil – vyberte jiný."):
            reception.book(self.pet.id, self.book_proc.id, self.day.isoformat(), 550, self.room.id)

    def test_book_bad_input(self):
        reception = self.api(self.reception)
        with self.assertRaises(UserError):
            reception.book(0, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
        with self.assertRaises(UserError):
            reception.book(self.pet.id, self.book_proc.id, self.day.isoformat(), "devět", self.room.id)
        with self.assertRaises(UserError):
            reception.book(self.pet.id, self.book_proc.id, self.day.isoformat(), 540, 0)
        with self.assertRaises(AccessError):
            self.api(self.outsider).book(self.pet.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
