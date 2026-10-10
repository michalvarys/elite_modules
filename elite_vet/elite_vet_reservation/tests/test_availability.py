from datetime import date, datetime

from odoo.tests import tagged

from .common import ReservationCase

WED = date(2026, 10, 14)   # streda


@tagged("post_install", "-at_install")
class TestAvailability(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.NOW = datetime(2026, 10, 1, 8, 0)   # UTC, daleko pred testovanymi dny
        for wd in range(5):
            cls.hours(cls, cls.room1, wd, 8.25, 19.5)
            cls.hours(cls, cls.room2, wd, 8.25, 19.5)

    def times(self, slots):
        return [s["time"] for s in slots]

    def test_interval_helpers(self):
        from odoo.addons.elite_vet_reservation.models.availability import intersect, subtract
        self.assertEqual(intersect([(480, 720)], [(600, 900)]), [(600, 720)])
        self.assertEqual(subtract([(480, 720)], [(540, 600)]), [(480, 540), (600, 720)])
        self.assertEqual(subtract([(480, 720)], [(400, 800)]), [])

    def test_open_minutes_template_and_exception(self):
        self.assertEqual(self.A.open_minutes(self.room1, WED), [(495, 1170)])
        self.assertEqual(self.A.open_minutes(self.room1, date(2026, 10, 17)), [])      # sobota
        self.env["elite.vet.room.exception"].create({"room_id": self.room1.id, "date": WED, "closed": True})
        self.assertEqual(self.A.open_minutes(self.room1, WED), [])
        self.env["elite.vet.room.exception"].create({"room_id": self.room1.id, "date": date(2026, 10, 17),
                                                     "hour_from": 9.0, "hour_to": 12.0})
        self.assertEqual(self.A.open_minutes(self.room1, date(2026, 10, 17)), [(540, 720)])

    def test_slots_follow_step_and_duration(self):
        slots = self.A.slots(self.vacc, WED, now=self.NOW)
        self.assertEqual(self.times(slots)[:3], ["08:15", "08:30", "08:45"])
        self.assertEqual(self.times(slots)[-1], "19:15")        # 15 min se vejde do 19:30
        self.assertEqual(sorted(slots[0]["room_ids"]), sorted([self.room1.id, self.room2.id]))

    def test_slot_must_fit_duration(self):
        slots = self.A.slots(self.derm, WED, now=self.NOW)      # 30 min, jen room1
        self.assertEqual(self.times(slots)[-1], "19:00")
        self.assertEqual(slots[-1]["room_ids"], [self.room1.id])

    def test_busy_reservation_and_block_remove_slots(self):
        self.reservation(start=self.dt(WED, 9, 0), procedure_id=self.derm.id)   # room1 9:00-9:30
        slots = self.A.slots(self.derm, WED, now=self.NOW)
        self.assertNotIn("09:00", self.times(slots))
        self.assertNotIn("08:45", self.times(slots))     # 8:45-9:15 by se krylo
        self.assertIn("09:30", self.times(slots))
        self.env["elite.vet.reservation"].create({"kind": "block", "block_reason": "Oběd", "room_id": False,
                                                  "start": self.dt(WED, 12, 0), "stop": self.dt(WED, 13, 0)})
        slots = self.A.slots(self.vacc, WED, now=self.NOW)
        self.assertNotIn("12:30", self.times(slots))
        self.assertIn("13:00", self.times(slots))

    def test_web_new_does_not_block(self):
        self.reservation(start=self.dt(WED, 9, 0), state="web_new", source="web")
        self.assertIn("09:00", self.times(self.A.slots(self.vacc, WED, now=self.NOW)))

    def test_doctor_filter(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        slots = self.A.slots(self.vacc, WED, doctor=self.dr_a, now=self.NOW)
        self.assertEqual(self.times(slots)[0], "08:15")
        self.assertEqual(self.times(slots)[-1], "11:45")
        self.assertEqual(slots[0]["room_ids"], [self.room1.id])
        self.assertEqual(slots[0]["doctor_ids"], [self.dr_a.id])

    def test_doctor_filter_respects_procedure_restriction(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0, procedures=self.derm)
        self.assertEqual(self.A.slots(self.vacc, WED, doctor=self.dr_a, now=self.NOW), [])
        self.assertTrue(self.A.slots(self.derm, WED, doctor=self.dr_a, now=self.NOW))

    def test_specialization_filter(self):
        # Vlastni sekce a specializace, aby test nezavisel na seedu tymoveho modulu
        section = self.env["elite.vet.team.section"].create({"name": "Lékařky"})
        spec = self.env["elite.vet.team.specialization"].create({
            "name": "Test spec", "icon_id": self.env["elite.vet.team.icon"].search([], limit=1).id})
        member = self.env["elite.vet.team.member"].create({
            "name": "MVDr. Alena Testová", "section_id": section.id,
            "specialization_ids": [(6, 0, spec.ids)]})
        self.dr_a.member_id = member
        self.assign(self.dr_a, self.room2, WED, 13.0, 15.0)
        self.assign(self.dr_b, self.room1, WED, 13.0, 15.0)
        slots = self.A.slots(self.vacc, WED, specialization=spec, now=self.NOW)
        self.assertEqual({tuple(s["room_ids"]) for s in slots}, {(self.room2.id,)})

    def test_require_doctor_setting(self):
        self.env["elite.vet.setting"].nastaveni().booking_require_doctor = True
        self.assertEqual(self.A.slots(self.vacc, WED, now=self.NOW), [])
        self.assign(self.dr_a, self.room1, WED, 10.0, 11.0)
        self.assertEqual(self.times(self.A.slots(self.vacc, WED, now=self.NOW)), ["10:00", "10:15", "10:30", "10:45"])

    def test_min_hours_before_and_max_days_ahead(self):
        now = self.dt(WED, 9, 0)                             # 9:00 praz. casu ve stredu
        slots = self.A.slots(self.vacc, date(2026, 10, 15), now=now)   # ctvrtek: min 24 h -> od 9:00
        self.assertEqual(self.times(slots)[0], "09:00")
        self.assertEqual(self.A.slots(self.vacc, WED, now=now), [])
        far = date(2026, 12, 16)                             # 63 dni > 60
        self.assertEqual(self.A.slots(self.vacc, far, now=now), [])

    def test_days_lists_only_days_with_slots(self):
        self.env["elite.vet.room.exception"].create({"room_id": self.room1.id, "date": WED, "closed": True})
        self.env["elite.vet.room.exception"].create({"room_id": self.room2.id, "date": WED, "closed": True})
        days = self.A.days(self.vacc, 2026, 10, now=self.NOW)
        self.assertNotIn("2026-10-14", days)
        self.assertIn("2026-10-13", days)
        self.assertNotIn("2026-10-17", days)         # sobota
        self.assertNotIn("2026-10-01", days)         # min 24 h od NOW (1.10. 8:00 UTC)

    def test_dst_day_slots(self):
        # 25.10.2026 je nedele s prechodem na zimni cas; sablona ma jen Po-Pa, tak otevreme vyjimkou
        dst = date(2026, 10, 25)
        self.env["elite.vet.room.exception"].create({"room_id": self.room1.id, "date": dst, "hour_from": 9.0, "hour_to": 12.0})
        slots = self.A.slots(self.vacc, dst, now=self.NOW)
        self.assertEqual(self.times(slots)[0], "09:00")
        self.assertEqual(self.A.local_to_utc(dst, 540), datetime(2026, 10, 25, 8, 0))   # po prechodu: UTC+1
        self._assert_dst_reservation(dst)

    def _assert_dst_reservation(self, dst, now=None):
        """Rezervace v 10:00 v den prechodu musi zablokovat spravne minuty (round-trip UTC <-> mistni cas)."""
        self.reservation(start=self.dt(dst, 10, 0), procedure_id=self.derm.id)
        times = self.times(self.A.slots(self.derm, dst, now=now or self.NOW))
        self.assertNotIn("10:00", times)
        self.assertIn("09:30", times)
        self.assertIn("10:30", times)
        self.assertEqual(self.A.utc_to_local_minutes(self.A.local_to_utc(dst, 600), dst), 600)

    def test_dst_spring_day_slots(self):
        # 29.3.2026 je nedele s prechodem na letni cas
        dst = date(2026, 3, 29)
        self.env["elite.vet.room.exception"].create({"room_id": self.room1.id, "date": dst, "hour_from": 9.0, "hour_to": 12.0})
        self._assert_dst_reservation(dst, now=datetime(2026, 3, 1, 8, 0))   # NOW musi byt pred testovanym dnem

    def test_two_doctors_same_room_no_duplicate_room_ids(self):
        self.env["elite.vet.setting"].nastaveni().booking_require_doctor = True
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        self.assign(self.dr_b, self.room1, WED, 10.0, 14.0)
        slot = next(s for s in self.A.slots(self.vacc, WED, now=self.NOW) if s["time"] == "10:00")
        self.assertEqual(slot["room_ids"], [self.room1.id])
        self.assertEqual(sorted(slot["doctor_ids"]), sorted([self.dr_a.id, self.dr_b.id]))

    def test_doctor_ids_informational_without_filter(self):
        self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        by_time = {s["time"]: s for s in self.A.slots(self.vacc, WED, now=self.NOW)}
        self.assertEqual(by_time["09:00"]["doctor_ids"], [self.dr_a.id])
        self.assertEqual(sorted(by_time["09:00"]["room_ids"]), sorted([self.room1.id, self.room2.id]))
        self.assertEqual(by_time["13:00"]["doctor_ids"], [])
