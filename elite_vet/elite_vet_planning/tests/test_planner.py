from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.elite_vet_reservation.tests.common import ReservationCase


@tagged("post_install", "-at_install")
class TestPlanner(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["elite.vet.planning.row"].search([]).write({"active": False})
        Type = cls.env["elite.vet.shift.type"]
        cls.t_morning = Type.create({"name": "T Ranní", "time_from": 8, "time_to": 14})
        Row = cls.env["elite.vet.planning.row"]
        cls.ord1 = Row.create({"name": "Ord 1", "room_id": cls.room1.id, "slot_ids": [
            (0, 0, {"name": "Ranní", "type_id": cls.t_morning.id, "hour_from": 8, "hour_to": 16, "days": "all"}),
            (0, 0, {"name": "Odpolední", "type_id": cls.t_morning.id, "hour_from": 12, "hour_to": 20, "days": "all"}),
        ]})
        cls.helpers = Row.create({"name": "Stáž", "kind": "helpers", "slot_ids": [
            (0, 0, {"name": "Výpomoc", "type_id": cls.t_morning.id, "hour_from": 8, "hour_to": 16, "days": "all"})]})
        cls.morning, cls.afternoon = cls.ord1.slot_ids.sorted("id")
        cls.nurse = cls.env["elite.vet.doctor"].create({"name": "Sestra Plánová", "staff_role": "nurse"})
        cls.day = fields.Date.context_today(cls.env.user) + timedelta(days=10)
        cls.month = cls.day.replace(day=1)
        cls.P = cls.env["elite.vet.planner"]
        cls.Assignment = cls.env["elite.vet.doctor.assignment"]

    def assignments(self, doctor):
        return self.Assignment.search([("doctor_id", "=", doctor.id), ("date", "=", self.day)])

    def test_doctor_shift_goes_to_reservations(self):
        data = self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        a = self.assignments(self.dr_a)
        self.assertEqual((a.room_id, a.hour_from, a.hour_to), (self.room1, 8, 16))
        self.assertTrue(a.shift_id.web_visible)
        self.assertIn(a.shift_id.id, [s["id"] for s in data["shifts"]])

    def test_morning_and_afternoon_merge_into_one_service(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.add_shift(self.month, self.afternoon.id, self.day, self.dr_a.id)
        a = self.assignments(self.dr_a)
        self.assertEqual(len(a), 1)
        self.assertEqual((a.hour_from, a.hour_to), (8, 20))
        # removing the morning leaves the afternoon as its own service
        morning = self.env["elite.vet.shift"].search([("planning_slot_id", "=", self.morning.id),
                                                      ("date", "=", self.day)])
        self.P.remove_shift(self.month, morning.id)
        a = self.assignments(self.dr_a)
        self.assertEqual((len(a), a.hour_from, a.hour_to), (1, 12, 20))
        data = self.P.load_month(self.month)
        self.assertEqual(data["balance"][self.dr_a.id]["shift_hours"], 8)

    def test_nurse_and_helper_not_in_reservations_nor_web(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.nurse.id)
        self.P.add_shift(self.month, self.helpers.slot_ids.id, self.day, False, "Praktikantka Eva")
        shifts = self.env["elite.vet.shift"].search([("date", "=", self.day), ("planning_slot_id", "!=", False)])
        self.assertEqual(len(shifts), 2)
        self.assertFalse(any(shifts.mapped("web_visible")))
        self.assertFalse(shifts.mapped("room_id"))
        self.assertFalse(self.assignments(self.nurse))
        with self.assertRaises(UserError):
            self.P.add_shift(self.month, self.morning.id, self.day, False, "Někdo")

    def test_requests_and_self_service(self):
        user = new_test_user(self.env, "sestra_planova", groups="base.group_user")
        self.nurse.user_id = user
        P = self.P.with_user(user)
        P.set_my_request(self.month, self.day, "morning", "do 14")
        req = self.env["elite.vet.staff.request"].search([("member_id", "=", self.nurse.id)])
        self.assertEqual((req.code, req.note, req.entered_by_member), ("morning", "do 14", True))
        with self.assertRaises(UserError):
            P.set_my_request(self.month, self.day, "D")
        with self.assertRaises(UserError):
            P.set_my_request(self.month, fields.Date.context_today(user) - timedelta(days=1), "can")
        with self.assertRaises(AccessError):
            P.load_month(self.month)
        # an absence from the management locks the day for her
        self.P.set_request(self.month, self.nurse.id, self.day, "D")
        with self.assertRaises(UserError):
            P.set_my_request(self.month, self.day, "can")
        mine = P.my_month(self.month)
        self.assertTrue(mine["requests"][fields.Date.to_string(self.day)]["locked"])

    def test_copy_previous_week_skips_absence(self):
        monday = self.day - timedelta(days=self.day.weekday())
        month = monday.replace(day=1)
        prev = monday - timedelta(days=7)
        self.P.add_shift(prev.replace(day=1), self.morning.id, prev, self.dr_a.id)
        self.P.add_shift(prev.replace(day=1), self.morning.id, prev, self.nurse.id)
        self.P.set_request(month, self.nurse.id, monday, "PN")
        result = self.P.copy_previous_week(month, monday)
        copied = self.env["elite.vet.shift"].search([("date", "=", monday), ("planning_slot_id", "=", self.morning.id)])
        if monday.month == month.month:
            self.assertEqual(copied.doctor_id, self.dr_a)
            self.assertTrue(self.assignments_on(self.dr_a, monday))
        self.assertIn("message", result)

    def assignments_on(self, doctor, day):
        return self.Assignment.search([("doctor_id", "=", doctor.id), ("date", "=", day)])
