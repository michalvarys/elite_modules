from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_reservation.models.reservation import RECEPTION_HORIZON_DAYS
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
        self.assertTrue(data["slots"])
        self.assertIsNone(data["next_free_day"], "searched only when the day has no free time")
        # the whole day blocked for all rooms: nothing free, the next free day is the day after
        A = self.env["elite.vet.availability"]
        self.env["elite.vet.reservation"].create({
            "kind": "block", "block_reason": "Celý den test recepce", "block_scope": "full", "room_id": False,
            "state": "confirmed", "start": A.local_to_utc(self.day, 0), "stop": A.local_to_utc(self.day, 1440)})
        data = reception.free_slots(self.book_proc.id, self.day.isoformat())
        self.assertEqual(data["slots"], [])
        self.assertEqual(data["next_free_day"], (self.day + timedelta(days=1)).isoformat())
        # a procedure whose only room has no opening hours: nothing free, no next free day
        closed = self.env["elite.vet.room"].create({"name": "Zavřená ordinace test recepce"})
        proc = self.env["elite.vet.procedure"].create({
            "name": "Nikdy test recepce", "duration": 20, "symbol": "N", "color": "red",
            "room_ids": [(6, 0, [closed.id])]})
        data = reception.free_slots(proc.id, self.day.isoformat())
        self.assertEqual((data["slots"], data["next_free_day"]), ([], None))

    def test_free_slots_beyond_the_horizon(self):
        far = clinic_today() + timedelta(days=RECEPTION_HORIZON_DAYS + 1)
        with patch.object(ReservationWizard, "_load_slots", side_effect=AssertionError("wizard used")):
            data = self.api(self.reception).free_slots(self.book_proc.id, far.isoformat())
        self.assertEqual(data, {"day": far.isoformat(), "slots": [], "next_free_day": None})

    def test_free_slots_bad_input(self):
        reception = self.api(self.reception)
        with self.assertRaises(UserError):
            reception.free_slots(self.book_proc.id, "zítra")
        with self.assertRaises(UserError):
            reception.free_slots(0, self.day.isoformat())
        with self.assertRaises(AccessError):
            self.api(self.outsider).free_slots(self.book_proc.id, self.day.isoformat())

    def test_free_days_counts_times_of_the_wizard(self):
        reception = self.api(self.reception)
        start = self.day - timedelta(days=1)
        data = reception.free_days(self.book_proc.id, start.isoformat())
        self.assertEqual([d["day"] for d in data], [(start + timedelta(days=i)).isoformat() for i in range(7)])
        times = {m for m, _room, _doc in self.wizard_lines(self.book_proc, self.day)}
        self.assertEqual(data[1], {"day": self.day.isoformat(), "count": len(times), "closed": False})
        self.assertTrue(data[1]["count"])
        # the doctor filter is passed on (she has a shift only on self.day)
        mine = reception.free_days(self.book_proc.id, start.isoformat(), self.doctor.id)
        self.assertEqual([d["count"] for d in mine][1], len({m for m, _r, _d in
                                                             self.wizard_lines(self.book_proc, self.day, self.doctor)}))

    def test_free_days_past_and_beyond_the_horizon(self):
        reception = self.api(self.reception)
        yesterday = clinic_today() - timedelta(days=1)
        data = reception.free_days(self.book_proc.id, yesterday.isoformat(), days=2)
        self.assertIsNone(data[0]["count"])
        self.assertIsNotNone(data[1]["count"])
        far = clinic_today() + timedelta(days=RECEPTION_HORIZON_DAYS + 1)
        self.assertEqual(reception.free_days(self.book_proc.id, far.isoformat(), days=1),
                         [{"day": far.isoformat(), "count": None, "closed": False}])
        with self.assertRaises(AccessError):
            self.api(self.outsider).free_days(self.book_proc.id, far.isoformat())

    def test_free_days_closed_or_fully_booked(self):
        """Task 12: `closed` = the day cannot have a free time at all; a fully booked open day is
        not closed ("nic volného")."""
        A = self.env["elite.vet.availability"]
        Res = self.env["elite.vet.reservation"]
        reception = self.api(self.reception)
        proc = self.env["elite.vet.procedure"].create({
            "name": "Zavřeno test recepce", "duration": 20, "symbol": "Z", "color": "blue",
            "room_ids": [(6, 0, [self.room.id])]})
        booked, blocked, exception = (self.day + timedelta(days=i) for i in (1, 2, 3))
        # the whole opening time of the only room booked
        Res.create({"kind": "reservation", "state": "confirmed", "room_id": self.room.id,
                    "procedure_id": proc.id, "doctor_id": self.doctor.id,
                    "start": A.local_to_utc(booked, 8 * 60), "stop": A.local_to_utc(booked, 12 * 60)})
        Res.create({"kind": "block", "block_reason": "Celý den zavřeno test", "block_scope": "full",
                    "room_id": False, "state": "confirmed",
                    "start": A.local_to_utc(blocked, 0), "stop": A.local_to_utc(blocked, 1440)})
        self.env["elite.vet.room.exception"].create({"room_id": self.room.id, "date": exception, "closed": True})
        data = {d["day"]: d for d in reception.free_days(proc.id, self.day.isoformat(), days=5)}
        self.assertEqual(data[self.day.isoformat()]["closed"], False)
        self.assertTrue(data[self.day.isoformat()]["count"])
        self.assertEqual(data[booked.isoformat()], {"day": booked.isoformat(), "count": 0, "closed": False})
        self.assertEqual(data[blocked.isoformat()], {"day": blocked.isoformat(), "count": 0, "closed": True})
        self.assertEqual(data[exception.isoformat()], {"day": exception.isoformat(), "count": 0, "closed": True})
        # a web-only block does not close the day for reception
        web_only = self.day + timedelta(days=4)
        Res.create({"kind": "block", "block_reason": "Jen web test", "block_scope": "web", "room_id": False,
                    "state": "confirmed", "start": A.local_to_utc(web_only, 0), "stop": A.local_to_utc(web_only, 1440)})
        day = reception.free_days(proc.id, web_only.isoformat(), days=1)[0]
        self.assertFalse(day["closed"])
        self.assertTrue(day["count"])
        # a doctor required: a day without any shift is closed, the day with her shift is not
        self.env["elite.vet.setting"].nastaveni().booking_require_doctor = True
        data = reception.free_days(self.book_proc.id, self.day.isoformat(), days=2)
        self.assertEqual([(d["closed"], bool(d["count"])) for d in data], [(False, True), (True, False)])
        # the doctor filter likewise (a day without her shift)
        self.env["elite.vet.setting"].nastaveni().booking_require_doctor = False
        data = reception.free_days(self.book_proc.id, self.day.isoformat(), self.doctor.id, days=2)
        self.assertEqual([(d["closed"], bool(d["count"])) for d in data], [(False, True), (True, False)])
        # a procedure whose only room has no opening hours at all
        closed_room = self.env["elite.vet.room"].create({"name": "Bez hodin test recepce"})
        never = self.env["elite.vet.procedure"].create({
            "name": "Nikdy zavřeno test", "duration": 20, "symbol": "N", "color": "red",
            "room_ids": [(6, 0, [closed_room.id])]})
        self.assertTrue(all(d["closed"] for d in reception.free_days(never.id, self.day.isoformat())))

    # ---------------------------------------------------------------- frequent procedures
    def test_booking_options_frequent(self):
        """Task 12: up to 6 procedures by the reservations of the last 30 days, else the first ones."""
        A = self.env["elite.vet.availability"]
        Res = self.env["elite.vet.reservation"]
        today = clinic_today()
        # nothing else counted in this test: reservations already in the window are cancelled
        self.env.cr.execute("UPDATE elite_vet_reservation SET state = 'cancelled' WHERE kind = 'reservation'")
        Res.invalidate_model(["state"])
        procs = [self.env["elite.vet.procedure"].create({
            "name": "Častý %s test recepce" % i, "duration": 15, "symbol": "C", "color": "green",
            "room_ids": [(6, 0, [self.room.id])]}) for i in range(3)]
        slot = iter(range(8 * 60, 20 * 60, 15))

        def reserve(proc, day, state="confirmed"):
            minute = next(slot)
            Res.with_context(ev_no_mail=True).create({
                "kind": "reservation", "state": state, "room_id": self.room.id, "procedure_id": proc.id,
                "doctor_id": self.doctor.id,
                "start": A.local_to_utc(day, minute), "stop": A.local_to_utc(day, minute + 15)})

        for _i in range(3):
            reserve(procs[2], today)
        for _i in range(2):
            reserve(procs[1], today - timedelta(days=29))
        reserve(procs[0], today - timedelta(days=31))  # too old
        reserve(procs[0], today, state="cancelled")  # cancelled
        reserve(procs[0], today + timedelta(days=1))  # future, not yet a fact
        reserve(procs[0], today, state="no_show")  # booked, the client did not come: counts
        reception = self.api(self.reception)
        self.assertEqual(reception.booking_options()["frequent"], [procs[2].id, procs[1].id, procs[0].id])
        # more than six: only the six most booked
        extra = [self.env["elite.vet.procedure"].create({
            "name": "Další častý %s test" % i, "duration": 15, "symbol": "D", "color": "blue",
            "room_ids": [(6, 0, [self.room.id])]}) for i in range(5)]
        for proc in extra:
            reserve(proc, today)
            reserve(proc, today)
        frequent = reception.booking_options()["frequent"]
        self.assertEqual(len(frequent), 6)
        self.assertEqual(frequent[0], procs[2].id)
        self.assertNotIn(procs[0].id, frequent)
        # no data at all: the first procedures in their normal order
        self.env.cr.execute("UPDATE elite_vet_reservation SET state = 'cancelled' WHERE kind = 'reservation'")
        Res.invalidate_model(["state"])
        options = reception.booking_options()
        self.assertEqual(options["frequent"], [p["id"] for p in options["procedures"][:6]])

    # ---------------------------------------------------------------- nearest free time
    def test_nearest_free(self):
        """Task 12: the earliest free time from today; rooms at the same minute in natural order."""
        self.room.name = "Ordinace 10 test recepce"
        self.room2.name = "Ordinace 9 test recepce"
        reception = self.api(self.reception)
        day = clinic_today()
        while not reception.free_slots(self.book_proc.id, day.isoformat())["slots"]:
            day += timedelta(days=1)
        slots = reception.free_slots(self.book_proc.id, day.isoformat())["slots"]
        first = min(s["minute"] for s in slots)
        expected = [s for s in slots if s["minute"] == first and s["room_id"] == self.room2.id][0]
        self.assertEqual(reception.nearest_free(self.book_proc.id), dict(expected, day=day.isoformat()))
        # the doctor filter: her only shift (self.day, room 1, from 8:00)
        mine = reception.nearest_free(self.book_proc.id, self.doctor.id)
        self.assertEqual(mine, {"day": self.day.isoformat(), "time": "8:00", "minute": 480,
                                "room_id": self.room.id, "room": self.room.name,
                                "doctor_id": self.doctor.id, "doctor": self.doctor.name})
        with self.assertRaises(AccessError):
            self.api(self.outsider).nearest_free(self.book_proc.id)

    def test_nearest_free_nothing_and_horizon(self):
        reception = self.api(self.reception)
        room = self.env["elite.vet.room"].create({"name": "Výjimečná ordinace test recepce"})
        proc = self.env["elite.vet.procedure"].create({
            "name": "Výjimečný test recepce", "duration": 20, "symbol": "V", "color": "red",
            "room_ids": [(6, 0, [room.id])]})
        horizon = clinic_today() + timedelta(days=RECEPTION_HORIZON_DAYS)
        # open only the day after the horizon: never searched, nothing found
        self.env["elite.vet.room.exception"].create({
            "room_id": room.id, "date": horizon + timedelta(days=1), "hour_from": 8.0, "hour_to": 12.0})
        searched = []
        original = ReservationWizard._free_slots

        def spy(wizard, day):
            searched.append(day)
            return original(wizard, day)

        with patch.object(ReservationWizard, "_free_slots", spy):
            self.assertIsNone(reception.nearest_free(proc.id))
        self.assertEqual((min(searched), max(searched)), (clinic_today(), horizon))
        # open on the last day of the horizon: found there
        self.env["elite.vet.room.exception"].create({
            "room_id": room.id, "date": horizon, "hour_from": 9.0, "hour_to": 12.0})
        found = reception.nearest_free(proc.id)
        self.assertEqual((found["day"], found["minute"], found["room_id"]), (horizon.isoformat(), 540, room.id))
        with self.assertRaises(UserError):
            reception.nearest_free(0)

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

    def test_book_refuses_deceased_pet(self):
        """Ruling R8."""
        pet = self.new_pet("Uhynulý objednaný")
        pet.deceased = True
        with self.assertRaisesRegex(UserError, "Zvíře je vedené jako uhynulé."):
            self.api(self.reception).book(pet.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)
        self.assertFalse(self.booked(self.owner))

    def test_book_refuses_staff_owner(self):
        """The card index owner rule applies to booking too."""
        pet = self.new_pet("Služební objednaný", self.nurse.partner_id)
        with self.assertRaisesRegex(UserError, "Tento kontakt není klient kliniky."):
            self.api(self.reception).book(pet.id, self.book_proc.id, self.day.isoformat(), 540, self.room.id)

    def test_book_reservation_not_found_after_save(self):
        """Never return reservation_id False: a save that leaves no reservation is an error."""
        with patch.object(ReservationWizard, "action_save", lambda w: True), \
                self.assertRaisesRegex(UserError, "Rezervaci se nepodařilo uložit"):
            self.api(self.reception).book(self.pet.id, self.book_proc.id, self.day.isoformat(), 540,
                                          self.room.id)
