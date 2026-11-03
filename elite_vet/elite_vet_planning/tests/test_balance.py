from datetime import date

from odoo.tests import TransactionCase, tagged

from odoo.addons.elite_vet_planning.models.planner import day_hours, month_balance, working_days


@tagged("post_install", "-at_install")
class TestBalance(TransactionCase):

    def test_day_hours_overlap_counted_once(self):
        self.assertEqual(day_hours([(8, 16), (12, 20)]), 12)
        self.assertEqual(day_hours([(8, 12), (14, 18)]), 8)
        self.assertEqual(day_hours([(8, 16), (9, 15)]), 8)

    def test_november_2026_has_20_working_days(self):
        # 17. 11. 2026 is a Tuesday holiday.
        self.assertEqual(len(working_days(date(2026, 11, 1), date(2026, 11, 30))), 20)

    def test_month_balance(self):
        Doctor = self.env["elite.vet.doctor"]
        Type = self.env["elite.vet.shift.type"]
        t = Type.create({"name": "T Bilance", "time_from": 8, "time_to": 16})
        member = Doctor.create({"name": "Sestra Bilance", "weekly_hours": 30})
        Shift = self.env["elite.vet.shift"]
        shifts = Shift.create([
            {"date": "2026-11-02", "doctor_id": member.id, "type_id": t.id, "hour_from": 8, "hour_to": 16},
            {"date": "2026-11-02", "doctor_id": member.id, "type_id": t.id, "hour_from": 12, "hour_to": 20},
            {"date": "2026-11-03", "doctor_id": member.id, "type_id": t.id, "hour_from": 12, "hour_to": 20},
            {"date": "2026-11-04", "doctor_id": member.id, "type_id": t.id, "hour_from": 8, "hour_to": 16},
            {"date": "2026-11-07", "doctor_id": member.id, "type_id": t.id, "hour_from": 10, "hour_to": 18},
        ])
        Req = self.env["elite.vet.staff.request"]
        requests = Req.create([
            {"member_id": member.id, "date": "2026-11-05", "code": "D"},
            {"member_id": member.id, "date": "2026-11-06", "code": "NV"},
            {"member_id": member.id, "date": "2026-11-09", "code": "PN"},
            {"member_id": member.id, "date": "2026-11-08", "code": "D"},   # Sunday: no fond, no credit
        ])
        b = month_balance(member, shifts, requests, date(2026, 11, 1), date(2026, 11, 30))[member.id]
        self.assertEqual(b["fond"], 120)            # 20 days × 6 h
        self.assertEqual(b["shift_hours"], 12 + 8 + 8 + 8)
        self.assertEqual(b["credited"], 6)          # one D on a working day
        self.assertEqual((b["full_day"], b["morning"], b["afternoon"], b["weekend"]), (1, 1, 1, 1))
        self.assertEqual(b["absences"]["D"], 2)
        self.assertEqual(b["saldo"], 42 - 120)
