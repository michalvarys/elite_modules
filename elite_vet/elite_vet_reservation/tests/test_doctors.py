from datetime import date, datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReservationCase

WED = date(2026, 10, 14)
NOW = datetime(2026, 10, 1, 8, 0)


@tagged("post_install", "-at_install")
class TestDoctors(ReservationCase):
    """Who may receive a reservation and which doctors perform which procedure."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icon = cls.env["elite.vet.team.icon"].search([], limit=1)
        section = cls.env["elite.vet.team.section"].create({"name": "Lékařky test"})
        Spec = cls.env["elite.vet.team.specialization"]
        cls.dentistry = Spec.create({"name": "Test stomatologie", "icon_id": icon.id})
        cls.ophthalmology = Spec.create({"name": "Test oftalmologie", "icon_id": icon.id})
        Member = cls.env["elite.vet.team.member"]
        cls.dr_a.member_id = Member.create({"name": cls.dr_a.name, "section_id": section.id,
                                            "specialization_ids": [(6, 0, cls.dentistry.ids)]})
        cls.dr_b.member_id = Member.create({"name": cls.dr_b.name, "section_id": section.id,
                                            "specialization_ids": [(6, 0, cls.ophthalmology.ids)]})
        cls.nurse = cls.env["elite.vet.doctor"].create({"name": "Sestra Testová"})
        cls.dental = cls.env["elite.vet.procedure"].create({
            "name": "Dental examination", "duration": 30, "specialization_ids": [(6, 0, cls.dentistry.ids)]})
        for wd in range(5):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
            cls.hours(cls, cls.room2, wd, 8.0, 18.0)
        cls.A = cls.env["elite.vet.availability"]

    def times(self, slots):
        return [s["time"] for s in slots]

    def test_nurse_cannot_be_assigned(self):
        with self.assertRaises(ValidationError):
            self.assign(self.nurse, self.room1, WED, 8.0, 12.0)

    def test_doctors_for_booking(self):
        self.assertEqual(self.dental.doctors_for_booking(), self.dr_a)
        self.assertEqual(self.vacc.doctors_for_booking(), self.dr_a | self.dr_b)
        self.assertNotIn(self.nurse, self.vacc.doctors_for_booking())

    def test_specialised_procedure_only_when_qualified_doctor_serves(self):
        self.assign(self.dr_b, self.room1, WED, 8.0, 12.0)   # ophthalmologist, does not do dental
        self.assertEqual(self.A.slots(self.dental, WED, now=NOW), [])
        self.assign(self.dr_a, self.room2, WED, 13.0, 15.0)  # dentist
        slots = self.A.slots(self.dental, WED, now=NOW)
        self.assertEqual(self.times(slots)[0], "13:00")
        self.assertEqual(self.times(slots)[-1], "14:30")
        self.assertEqual({tuple(s["room_ids"]) for s in slots}, {(self.room2.id,)})
        self.assertEqual({tuple(s["doctor_ids"]) for s in slots}, {(self.dr_a.id,)})

    def test_general_procedure_lists_only_doctors_on_duty(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, WED, 8.0, 12.0)
        slot = next(s for s in self.A.slots(self.vacc, WED, now=NOW) if s["time"] == "09:00")
        self.assertEqual(sorted(slot["doctor_ids"]), sorted([self.dr_a.id, self.dr_b.id]))

    def test_specialization_filter_picks_doctors_with_it(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, WED, 8.0, 12.0)
        slots = self.A.slots(self.vacc, WED, specialization=self.ophthalmology, now=NOW)
        self.assertTrue(slots)
        self.assertEqual({tuple(s["doctor_ids"]) for s in slots}, {(self.dr_b.id,)})
        self.assertEqual({tuple(s["room_ids"]) for s in slots}, {(self.room2.id,)})

    def test_install_hook_links_doctors_to_team_cards(self):
        from odoo.addons.elite_vet_reservation import _link_doctors
        Doctor = self.env["elite.vet.doctor"]
        Doctor.search([]).write({"accepts_bookings": False})
        section = self.env["elite.vet.team.section"].create({"name": "Sekce hook"})
        member = self.env["elite.vet.team.member"].create({"name": "MVDr. Nová Lékařka", "section_id": section.id})
        new_doctor = Doctor.create({"name": "MVDr. Nová Lékařka"})
        _link_doctors(self.env)
        self.assertEqual(new_doctor.member_id, member)
        self.assertTrue(new_doctor.accepts_bookings)
        self.assertFalse(self.nurse.accepts_bookings)
