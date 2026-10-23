"""Shift roster with a room feeds the reservation calendar (Task 13)."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestShiftRooms(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Shift = cls.env["elite.vet.shift"]
        cls.Assignment = cls.env["elite.vet.doctor.assignment"]
        Type = cls.env["elite.vet.shift.type"]
        cls.morning = Type.create({"name": "T Ranní", "time_from": 8.0, "time_to": 14.0})
        cls.afternoon = Type.create({"name": "T Odpolední", "time_from": 14.0, "time_to": 20.0})
        cls.night = Type.create({"name": "T Noční", "time_from": 20.0, "time_to": 8.0})
        cls.closed = Type.create({"name": "T Zavřeno", "is_note": True})
        cls.nurse = cls.env["elite.vet.doctor"].create({"name": "Sestra Testová"})
        cls.dr_a.default_room_id = cls.room1
        cls.day = fields.Date.context_today(cls.Shift) + timedelta(days=7)
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 0.0, 24.0)
            cls.hours(cls, cls.room2, wd, 0.0, 24.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 0, "booking_slot_step": 15})

    def shift(self, doctor=None, shift_type=None, day=None, **vals):
        base = {"date": day or self.day, "type_id": (shift_type or self.morning).id}
        if doctor is not False:
            base["doctor_id"] = (doctor or self.dr_a).id
        base.update(vals)
        return self.Shift.create(base)

    def linked(self, shift):
        return self.Assignment.search([("shift_id", "=", shift.id)])

    # ---------- sync ----------
    def test_create_with_default_room_creates_assignment(self):
        s = self.shift()
        self.assertEqual(s.room_id, self.room1)
        a = self.linked(s)
        self.assertEqual(len(a), 1)
        self.assertEqual((a.doctor_id, a.room_id, a.date, a.hour_from, a.hour_to),
                         (self.dr_a, self.room1, self.day, 8.0, 14.0))
        self.assertTrue(a.from_roster)
        self.assertEqual(s.assignment_ids, a)

    def test_no_room_no_assignment(self):
        s = self.shift(doctor=self.dr_b)   # no default room
        self.assertFalse(s.room_id)
        self.assertFalse(self.linked(s))
        s2 = self.shift(day=self.day + timedelta(days=1), room_id=False)   # explicitly empty
        self.assertFalse(s2.room_id)
        self.assertFalse(self.linked(s2))

    def test_update_room_doctor_date_and_type(self):
        s = self.shift()
        a = self.linked(s)
        s.room_id = self.room2
        self.assertEqual(a.room_id, self.room2)
        s.doctor_id = self.dr_b
        self.assertEqual(a.doctor_id, self.dr_b)
        s.date = self.day + timedelta(days=1)
        self.assertEqual(a.date, self.day + timedelta(days=1))
        s.type_id = self.afternoon
        self.assertEqual((a.hour_from, a.hour_to), (14.0, 20.0))
        self.assertEqual(self.linked(s), a, "still the same assignment, updated in place")

    def test_clear_room_note_and_unlink_delete_assignment(self):
        s1 = self.shift()
        a1 = self.linked(s1)
        s1.room_id = False
        self.assertFalse(a1.exists())
        s2 = self.shift(day=self.day + timedelta(days=1))
        a2 = self.linked(s2)
        s2.write({"type_id": self.closed.id, "doctor_id": False, "room_id": False})
        self.assertFalse(a2.exists())
        s3 = self.shift(day=self.day + timedelta(days=2))
        a3 = self.linked(s3)
        s3.unlink()
        self.assertFalse(a3.exists())

    def test_night_shift_ends_at_midnight(self):
        a = self.linked(self.shift(shift_type=self.night))
        self.assertEqual((a.hour_from, a.hour_to), (20.0, 24.0))

    def test_shift_type_time_change_updates_today_and_later_only(self):
        future = self.shift()
        past = self.shift(day=fields.Date.context_today(self.Shift) - timedelta(days=3))
        a_future, a_past = self.linked(future), self.linked(past)
        self.morning.write({"time_from": 7.0, "time_to": 13.0})
        self.assertEqual((a_future.hour_from, a_future.hour_to), (7.0, 13.0))
        self.assertEqual((a_past.hour_from, a_past.hour_to), (8.0, 14.0))

    def test_takeover_of_overlapping_manual_assignment(self):
        manual = self.assign(self.dr_a, self.room2, self.day, 9.0, 12.0, procedures=self.derm)
        s = self.shift()
        self.assertEqual(self.linked(s), manual, "taken over, no duplicate")
        self.assertEqual((manual.room_id, manual.hour_from, manual.hour_to), (self.room1, 8.0, 14.0))
        self.assertEqual(manual.procedure_ids, self.derm, "Only these procedures survive the takeover")
        self.assertEqual(self.Assignment.search_count([("doctor_id", "=", self.dr_a.id), ("date", "=", self.day)]), 1)

    def test_clash_with_another_roster_shift_is_a_clear_message(self):
        self.shift()
        with self.assertRaises(ValidationError) as cm:
            self.shift(shift_type=self.env["elite.vet.shift.type"].create(
                {"name": "T Dlouhá", "time_from": 10.0, "time_to": 18.0}))
        self.assertIn("nejde propsat do rezervací", str(cm.exception))
        self.assertIn("už v tu dobu slouží", str(cm.exception))

    # ---------- validation ----------
    def test_room_only_for_doctor_shift(self):
        with self.assertRaises(ValidationError):
            self.shift(doctor=False, shift_type=self.closed, room_id=self.room1.id)
        with self.assertRaises(ValidationError):
            self.shift(doctor=self.nurse, room_id=self.room1.id)
        nurse_shift = self.shift(doctor=self.nurse)
        self.assertFalse(nurse_shift.room_id)
        self.assertFalse(self.linked(nurse_shift))

    def test_onchange_default_room(self):
        with Form(self.Shift) as f:
            f.date = self.day
            f.type_id = self.morning
            f.doctor_id = self.dr_a
            self.assertEqual(f.room_id, self.room1)
            f.doctor_id = self.nurse
            self.assertFalse(f.room_id)
            f.doctor_id = self.dr_a
            f.room_id = self.room2      # changeable
        self.assertEqual(self.linked(f.record).room_id, self.room2)

    # ---------- linked assignments are owned by the roster ----------
    def test_linked_assignment_is_protected(self):
        a = self.linked(self.shift())
        msg = "Tato služba je z Rozpisu služeb – upravte ji tam."
        for vals in ({"hour_to": 12.0}, {"room_id": self.room2.id}, {"doctor_id": self.dr_b.id},
                     {"date": self.day + timedelta(days=1)}):
            with self.assertRaises(UserError) as cm:
                a.write(vals)
            self.assertEqual(str(cm.exception), msg)
        with self.assertRaises(UserError):
            a.unlink()
        with self.assertRaises(UserError):
            self.Assignment.create({"doctor_id": self.dr_b.id, "room_id": self.room2.id, "date": self.day,
                                    "shift_id": a.shift_id.id})
        # Only these procedures and the note stay editable here.
        a.write({"procedure_ids": [(6, 0, self.derm.ids)], "note": "jen derma"})
        self.assertEqual(a.procedure_ids, self.derm)

    def test_manual_assignment_still_editable(self):
        a = self.assign(self.dr_b, self.room2, self.day, 9.0, 11.5)
        self.assertFalse(a.from_roster)
        a.write({"hour_to": 12.0, "room_id": self.room1.id})
        self.assertEqual(a.hour_to, 12.0)
        a.unlink()
        self.assertFalse(a.exists())

    def test_copy_week_skips_roster_assignments(self):
        roster = self.linked(self.shift())
        manual = self.assign(self.dr_b, self.room2, self.day, 9.0, 12.0)
        res = (roster | manual).action_copy_week()
        week = self.day + timedelta(days=7)
        copies = self.Assignment.search([("date", "=", week)])
        self.assertEqual(copies.doctor_id, self.dr_b)
        self.assertFalse(copies.shift_id)
        self.assertIn("Zkopírováno 1, přeskočeno 0.", res["params"]["message"])
        self.assertIn("1 služeb je z Rozpisu služeb", res["params"]["message"])

    def test_board_band_shows_roster_flag(self):
        self.shift()
        self.assign(self.dr_b, self.room2, self.day, 9.0, 12.0)
        data = self.env["elite.vet.reservation"].board_data(fields.Date.to_string(self.day))
        flags = {d["doctor_id"]: d["from_roster"] for r in data["rooms"] for d in r["doctors"]}
        self.assertEqual(flags, {self.dr_a.id: True, self.dr_b.id: False})

    def test_calendar_manager_without_reservation_rights_syncs(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Jen rozpis", "login": "jen_rozpis_t13",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_calendar.group_calendar_manager").id])]})
        s = self.Shift.with_user(user).create({"date": self.day, "type_id": self.morning.id,
                                               "doctor_id": self.dr_a.id})
        self.assertEqual(self.linked(s).room_id, self.room1)

    # ---------- import ----------
    def test_import_counts(self):
        dr_c = self.env["elite.vet.doctor"].create({"name": "MVDr. Cecílie Testová", "accepts_bookings": True})
        # existing roster without rooms (entered before the room existed)
        s_ok = self.shift(room_id=False)
        s_no_room = self.shift(doctor=self.dr_b)
        s_past = self.shift(day=fields.Date.context_today(self.Shift) - timedelta(days=1), room_id=False)
        s_nurse = self.shift(doctor=self.nurse)
        # two overlapping roster shifts of dr_c: the second one cannot be propagated (clash)
        dr_c.default_room_id = self.room2
        s_c1 = self.shift(doctor=dr_c, day=self.day + timedelta(days=1))
        long_type = self.env["elite.vet.shift.type"].create({"name": "T Dlouhá", "time_from": 10.0, "time_to": 18.0})
        s_c2 = self.shift(doctor=dr_c, shift_type=long_type, day=self.day + timedelta(days=1), room_id=False)
        self.assertTrue(self.linked(s_c1))
        res = self.Shift.action_roster_to_reservations()
        self.assertEqual(res["params"]["message"], "Propsáno 1. Přeskočeno: bez výchozí ordinace 1, kolize 1.")
        self.assertEqual(s_ok.room_id, self.room1)
        self.assertTrue(self.linked(s_ok))
        self.assertFalse(s_no_room.room_id)
        self.assertFalse(s_past.room_id, "past shifts are left alone")
        self.assertFalse(s_nurse.room_id)
        self.assertFalse(s_c2.room_id, "clash rolled back")
        self.assertFalse(self.linked(s_c2))
        self.assertTrue(self.linked(s_c1).exists())

    def test_import_only_for_reservation_manager(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Jen rozpis 2", "login": "jen_rozpis_t13b",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_calendar.group_calendar_manager").id])]})
        with self.assertRaises(AccessError):
            self.Shift.with_user(user).action_roster_to_reservations()

    # ---------- the doctor on duty is preselected ----------
    def test_wizard_board_click_preselects_roster_doctor(self):
        self.shift()   # dr_a, room1, 8–14 from the roster
        W = self.env["elite.vet.reservation.wizard"]
        with Form(W.with_context(default_date=fields.Date.to_string(self.day), default_minute=600,
                                 default_room_id=self.room1.id)) as f:
            self.assertEqual(f.doctor_id, self.dr_a)
            f.procedure_id = self.vacc
            self.assertEqual(f.doctor_id, self.dr_a)
            f.doctor_id = self.dr_b    # changeable
            self.assertFalse(f.serving_doctor_id)
        w = f.record
        w.doctor_id = self.dr_a
        w.action_step_time()
        self.assertEqual((w.step, w.slot_doctor_id), ("client", self.dr_a))

    def test_wizard_free_times_carry_roster_doctor(self):
        self.shift()
        w = self.env["elite.vet.reservation.wizard"].create({"procedure_id": self.vacc.id, "date": self.day})
        w.action_step_time()
        at_ten = w.slot_ids.filtered(lambda ln: ln.minute == 600 and ln.room_id == self.room1)
        self.assertEqual(at_ten.doctor_id, self.dr_a)
        at_ten.action_select()
        self.assertEqual(w.slot_doctor_id, self.dr_a)
