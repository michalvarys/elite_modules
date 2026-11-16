"""Requests of 16. 11. (Lucie): shift type by time, a doctor hidden on the website, the month
published only when finished, overview by person and a PDF that opens."""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.elite_vet_planning.models.planner import row_short
from odoo.addons.elite_vet_reservation.tests.common import ReservationCase


@tagged("post_install", "-at_install")
class TestFeedback1611(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["elite.vet.planning.row"].search([]).write({"active": False})
        Type = cls.env["elite.vet.shift.type"]
        Type.search([("is_note", "=", False)]).write({"active": False})
        cls.t_full = Type.create({"name": "T Celodenní", "time_from": 8, "time_to": 20, "sequence": 1})
        cls.t_am = Type.create({"name": "T Ranní 8–14", "time_from": 8, "time_to": 14})
        cls.t_pm = Type.create({"name": "T Odpolední 14–20", "time_from": 14, "time_to": 20})
        # the clinic's slots all point to the full-day type: the planner must not copy it blindly
        cls.ord1 = cls.env["elite.vet.planning.row"].create({"name": "Ord 1", "room_id": cls.room1.id, "slot_ids": [
            (0, 0, {"name": "Ranní", "type_id": cls.t_full.id, "hour_from": 8, "hour_to": 16, "days": "all"}),
            (0, 0, {"name": "Odpolední", "type_id": cls.t_full.id, "hour_from": 12, "hour_to": 20, "days": "all"}),
        ]})
        cls.morning, cls.afternoon = cls.ord1.slot_ids.sorted("id")
        cls.nurse = cls.env["elite.vet.doctor"].create({"name": "Sestra Plánová", "staff_role": "nurse"})
        # a weekday ten or more days ahead (the "C · 12h" item is for weekdays)
        day = fields.Date.context_today(cls.env.user) + timedelta(days=10)
        cls.day = day + timedelta(days=max(0, day.weekday() - 4) and 7 - day.weekday())
        cls.month = cls.day.replace(day=1)
        cls.P = cls.env["elite.vet.planner"]
        cls.Shift = cls.env["elite.vet.shift"]

    def assignments(self, doctor):
        return self.env["elite.vet.doctor.assignment"].search([("doctor_id", "=", doctor.id), ("date", "=", self.day)])

    def planned(self, slot, member=None):
        return self.Shift.search([("planning_slot_id", "=", slot.id), ("date", "=", self.day),
                                  ("doctor_id", "=", (member or self.dr_a).id)])

    def test_shift_type_follows_the_time(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.add_shift(self.month, self.afternoon.id, self.day, self.dr_a.id)
        self.assertEqual(self.planned(self.morning).type_id, self.t_am)
        self.assertEqual(self.planned(self.afternoon).type_id, self.t_pm)
        shift = self.planned(self.morning)
        self.P.update_shift(self.month, shift.id, 8, 20)
        self.assertEqual(shift.type_id, self.t_full)

    def test_hide_doctor_on_website(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.set_published(self.month, True)
        shift = self.planned(self.morning)
        self.assertEqual(shift.website_shifts(), shift)
        data = self.P.set_shift_web(self.month, shift.id, False)
        self.assertTrue(shift.hide_on_web)
        self.assertFalse(shift.web_visible)
        self.assertFalse(shift.website_shifts())
        self.assertTrue(next(s for s in data["shifts"] if s["id"] == shift.id)["hide_on_web"])
        # still the doctor's service in the reservation calendar
        self.assertTrue(self.assignments(self.dr_a))
        self.P.set_shift_web(self.month, shift.id, True)
        self.assertTrue(shift.website_shifts())

    def test_merged_service_hidden_when_one_shift_is(self):
        """Morning 8–16 + afternoon 12–20 make one service 8–20; hiding either shift hides the
        whole service from online booking (follow-up 16. 11.: the doctor must not show on the web)."""
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.add_shift(self.month, self.afternoon.id, self.day, self.dr_a.id)
        service = self.assignments(self.dr_a)
        self.assertEqual((len(service), service.hour_from, service.hour_to), (1, 8, 20))
        self.assertFalse(service.hide_on_web)
        self.P.set_shift_web(self.month, self.planned(self.afternoon).id, False)
        self.assertTrue(self.assignments(self.dr_a).hide_on_web)
        self.P.set_shift_web(self.month, self.planned(self.afternoon).id, True)
        self.assertFalse(self.assignments(self.dr_a).hide_on_web)

    def test_month_on_website_only_when_published(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        shift = self.planned(self.morning)
        hand = self.Shift.create({"date": self.day, "doctor_id": self.dr_b.id, "type_id": self.t_am.id})
        self.assertFalse(self.P.load_month(self.month)["published"])
        self.assertEqual((shift | hand).website_shifts(), hand)   # hand-entered shifts as before
        data = self.P.set_published(self.month, True)
        self.assertTrue(data["published"])
        self.assertEqual((shift | hand).website_shifts(), shift | hand)
        self.P.set_published(self.month, False)
        self.assertEqual((shift | hand).website_shifts(), hand)

    def test_people_overview(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.add_shift(self.month, self.afternoon.id, self.day, self.nurse.id, False, 10, 18)
        self.P.set_request(self.month, self.dr_b.id, self.day, "NV")
        self.P.add_shift(self.month, self.afternoon.id, self.day, self.dr_a.id)
        people = self.P.load_month(self.month)["people"]
        day = str(self.day)
        self.assertEqual(people[self.dr_a.id][day], [{"label": "C · 12h", "sub": "Ord", "kind": "full"}])
        self.assertEqual(people[self.nurse.id][day], [{"label": "Ord", "sub": "10–18", "kind": "other"}])
        self.assertEqual(people[self.dr_b.id][day][0]["label"], "NV")
        self.assertEqual((row_short("Ordinace 2"), row_short("Recepce"), row_short("Sál")), ("Ord2", "Rec", "Sál"))

    def test_people_overview_morning_label(self):
        Row = self.env["elite.vet.planning.row"]
        rec = Row.create({"name": "Recepce", "slot_ids": [
            (0, 0, {"name": "Odpolední", "type_id": self.t_pm.id, "hour_from": 12, "hour_to": 20, "days": "all"})]})
        self.P.add_shift(self.month, rec.slot_ids.id, self.day, self.nurse.id)
        people = self.P.load_month(self.month)["people"]
        self.assertEqual(people[self.nurse.id][str(self.day)], [{"label": "O-Rec", "sub": "", "kind": "afternoon"}])

    def test_pdf_template(self):
        self.P.add_shift(self.month, self.morning.id, self.day, self.dr_a.id)
        self.P.add_shift(self.month, self.morning.id, self.day, self.nurse.id)
        Report = self.env["ir.actions.report"]
        html = Report._render_qweb_html("elite_vet_planning.report_roster", [], data={"month": str(self.month)})[0]
        html = html.decode()
        self.assertIn('class="article evr-roster"', html)
        self.assertIn("Přehled po lidech", html)
        self.assertIn(self.dr_a.initials, html)
        # doctors on the first line of the cell, the nurse on the second
        self.assertLess(html.index(">%s<" % self.dr_a.initials), html.index(">%s<" % self.nurse.initials))
        # The PDF itself is made by wkhtmltopdf, which loads the report assets from the server:
        # inside a test that server is blocked, so the conversion is checked by hand (README).
