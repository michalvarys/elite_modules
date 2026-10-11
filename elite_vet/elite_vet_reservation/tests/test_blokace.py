"""Část E: druhy blokací (jen web / úplná), víkendy a svátky jen pro web,
ruční čas v průvodci a dvě lékařky v jedné ordinaci na tabuli."""
import importlib.util
import os
from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.reservation import barva_lekarky, pruhy_sluzeb
from ..models.svatky import cz_svatky, svatek, velikonocni_nedele
from .common import ReservationCase

WED = date(2026, 10, 14)      # středa
SAT = date(2026, 10, 17)      # sobota
NOW = datetime(2026, 10, 1, 8, 0)


@tagged("post_install", "-at_install")
class TestSvatky(ReservationCase):

    def test_velikonoce_a_svatky(self):
        self.assertEqual(velikonocni_nedele(2026), date(2026, 4, 5))
        s26 = cz_svatky(2026)
        self.assertEqual(s26[date(2026, 4, 3)], "Velký pátek")
        self.assertEqual(s26[date(2026, 4, 6)], "Velikonoční pondělí")
        s27 = cz_svatky(2027)
        self.assertEqual(s27[date(2027, 3, 26)], "Velký pátek")
        self.assertEqual(s27[date(2027, 3, 29)], "Velikonoční pondělí")
        self.assertEqual(len(s27), 13)
        for m, d in ((1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28), (10, 28), (11, 17), (12, 24), (12, 25), (12, 26)):
            self.assertIn(date(2027, m, d), s27)
        self.assertEqual(svatek(date(2026, 9, 28)), "Den české státnosti")
        self.assertIsNone(svatek(WED))
        # Výsledek je kopie: úprava nesmí rozbít cache.
        s27.clear()
        self.assertEqual(len(cz_svatky(2027)), 13)


@tagged("post_install", "-at_install")
class TestDruhBlokace(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.R = cls.env["elite.vet.reservation"]
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
            cls.hours(cls, cls.room2, wd, 8.0, 18.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15,
            "booking_max_days_ahead": 60, "booking_min_hours_before": 24})

    def block(self, day, h_from, h_to, scope, room=None, **vals):
        base = {"kind": "block", "block_reason": "Blokace %s" % scope, "block_scope": scope,
                "room_id": (room or self.room1).id,
                "start": self.dt(day, h_from), "stop": self.dt(day, h_to)}
        base.update(vals)
        return self.R.create(base)

    def rooms_at(self, slots, minute):
        return next((s["room_ids"] for s in slots if s["minute"] == minute), [])

    def test_default_scope_is_full(self):
        b = self.R.create({"kind": "block", "block_reason": "Oběd", "room_id": self.room1.id,
                           "start": self.dt(WED, 12), "stop": self.dt(WED, 13)})
        self.assertEqual(b.block_scope, "full")

    def test_busy_domain_scope(self):
        web = self.block(WED, 10, 11, "web")
        full = self.block(WED, 12, 13, "full")
        start, stop = self.dt(WED, 0), self.dt(WED, 23)
        self.assertEqual(self.R.search(self.R._busy_domain([self.room1.id], start, stop, scope="web")), web | full)
        self.assertEqual(self.R.search(self.R._busy_domain([self.room1.id], start, stop)), full)
        with self.assertRaises(ValueError):
            self.R._busy_domain([self.room1.id], start, stop, scope="cokoli")

    def test_web_block_hides_slots_only_for_web(self):
        self.block(WED, 10, 11, "web")
        web = self.A.slots(self.vacc, WED, now=NOW)
        self.assertEqual(self.rooms_at(web, 600), [self.room2.id])
        self.assertEqual(self.rooms_at(web, 660), [self.room1.id, self.room2.id])
        internal = self.A.slots(self.vacc, WED, now=NOW, scope="internal")
        self.assertEqual(self.rooms_at(internal, 600), [self.room1.id, self.room2.id])
        # Výchozí scope je web (veřejné API nesmí omylem dostat pravidla recepce).
        self.assertEqual(self.A.slots(self.vacc, WED, now=NOW), web)

    def test_full_block_hides_slots_everywhere(self):
        self.block(WED, 10, 11, "full")
        for scope in ("web", "internal"):
            self.assertEqual(self.rooms_at(self.A.slots(self.vacc, WED, now=NOW, scope=scope), 600),
                             [self.room2.id], scope)

    def test_global_web_block(self):
        self.block(WED, 10, 11, "web", room_id=False)
        self.assertEqual(self.rooms_at(self.A.slots(self.vacc, WED, now=NOW), 600), [])
        self.assertEqual(self.rooms_at(self.A.slots(self.vacc, WED, now=NOW, scope="internal"), 600),
                         [self.room1.id, self.room2.id])
        self.reservation(start=self.dt(WED, 10, 0))   # recepce smí

    def test_reservation_over_web_block_allowed_over_full_refused(self):
        self.block(WED, 10, 11, "web")
        r = self.reservation(start=self.dt(WED, 10, 0))
        self.assertEqual(r.state, "confirmed")
        self.block(WED, 12, 13, "full")
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(WED, 12, 0))

    def test_web_block_anytime_full_block_not_over_reservation(self):
        self.reservation(start=self.dt(WED, 10, 0))
        web = self.block(WED, 9, 12, "web")
        self.block(WED, 9, 12, "web")   # i přes jinou blokaci jen pro web
        with self.assertRaises(ValidationError):
            self.block(WED, 9, 12, "full")
        with self.assertRaises(ValidationError):
            web.block_scope = "full"
        # Úplná blokace přes blokaci jen pro web (bez rezervace) jde.
        self.block(WED, 13, 14, "web")
        self.block(WED, 13, 14, "full")

    def test_repeat_weekly_keeps_scope(self):
        self.block(WED, 7, 8, "web", repeat_weekly_until=WED + timedelta(days=14))
        copies = self.R.search([("kind", "=", "block"), ("block_reason", "=", "Blokace web")])
        self.assertEqual(len(copies), 3)
        self.assertEqual(set(copies.mapped("block_scope")), {"web"})

    def test_board_suggestions_and_move_ignore_web_block(self):
        day = fields.Date.today() + timedelta(days=30)
        w = self.reservation(start=self.dt(day, 10, 0), state="web_new", source="web", room_id=False)
        self.block(day, 10, 11, "web")
        self.assertIn(self.room1.id, [s["room_id"] for s in self.R.board_suggestions(w.id)])
        self.block(day, 10, 11, "full", room=self.room2)
        self.assertNotIn(self.room2.id, [s["room_id"] for s in self.R.board_suggestions(w.id)])
        r = self.reservation(start=self.dt(day, 8, 0), room_id=self.room2.id)
        self.R.board_move(r.id, fields.Date.to_string(day), 615, self.room1.id)   # do blokace jen pro web
        self.assertEqual((r.room_id, r.start), (self.room1, self.dt(day, 10, 15)))
        with self.assertRaises(ValidationError):
            self.R.board_move(r.id, fields.Date.to_string(day), 615, self.room2.id)   # do úplné ne
        self.R.board_confirm(w.id, fields.Date.to_string(day), 600, self.room1.id)
        self.assertEqual((w.state, w.room_id), ("confirmed", self.room1))

    def test_board_data_block_scope(self):
        web = self.block(WED, 10, 11, "web")
        full = self.block(WED, 12, 13, "full")
        ev = {e["id"]: e for e in self.R.board_data("2026-10-14")["events"]}
        self.assertEqual(ev[web.id]["block_scope"], "web")
        self.assertEqual(ev[full.id]["block_scope"], "full")

    def test_migration_sets_full(self):
        b = self.block(WED, 12, 13, "web")
        self.env.cr.execute("UPDATE elite_vet_reservation SET block_scope = NULL WHERE id = %s", (b.id,))
        path = os.path.join(os.path.dirname(__file__), "..", "migrations", "18.0.1.4.0", "post-migrate.py")
        spec = importlib.util.spec_from_file_location("ev_migrace_1_4", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, "18.0.1.3.0")
        b.invalidate_recordset(["block_scope"])
        self.assertEqual(b.block_scope, "full")


@tagged("post_install", "-at_install")
class TestVikendySvatky(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.R = cls.env["elite.vet.reservation"]
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
        cls.s = cls.env["elite.vet.setting"].nastaveni()
        cls.s.write({"booking_block_weekends": True, "booking_block_holidays": True, "booking_slot_step": 15,
                     "booking_require_doctor": False, "booking_max_days_ahead": 60, "booking_min_hours_before": 24})

    def test_defaults_on(self):
        Setting = self.env["elite.vet.setting"]
        self.assertTrue(Setting._fields["booking_block_weekends"].default(Setting))
        self.assertTrue(Setting._fields["booking_block_holidays"].default(Setting))

    def test_weekend_web_only(self):
        self.assertEqual(self.A.slots(self.vacc, SAT, now=NOW), [])
        self.assertEqual(self.A.slots(self.vacc, SAT + timedelta(days=1), now=NOW), [])
        self.assertTrue(self.A.slots(self.vacc, SAT, now=NOW, scope="internal"))
        self.assertTrue(self.A.slots(self.vacc, WED, now=NOW))
        days = self.A.days(self.vacc, 2026, 10, now=NOW)
        self.assertNotIn("2026-10-17", days)
        self.assertIn("2026-10-16", days)
        self.s.booking_block_weekends = False
        self.assertTrue(self.A.slots(self.vacc, SAT, now=NOW))

    def test_holiday_web_only(self):
        now27 = datetime(2027, 3, 1, 8, 0)
        for d in (date(2027, 3, 26), date(2027, 3, 29)):
            self.assertEqual(self.A.slots(self.vacc, d, now=now27), [], d)
            self.assertTrue(self.A.slots(self.vacc, d, now=now27, scope="internal"), d)
        self.assertTrue(self.A.slots(self.vacc, date(2027, 3, 25), now=now27))
        self.assertEqual(self.A.slots(self.vacc, date(2026, 10, 28), now=NOW), [])
        self.s.booking_block_holidays = False
        self.assertTrue(self.A.slots(self.vacc, date(2027, 3, 26), now=now27))

    def test_day_note(self):
        self.assertEqual(self.A.web_day_note(SAT), "Víkend – web neobjednává")
        self.assertEqual(self.A.web_day_note(date(2026, 9, 28)),
                         "Státní svátek: Den české státnosti – web neobjednává")
        self.assertIsNone(self.A.web_day_note(WED))
        self.assertEqual(self.R.board_data("2026-10-28")["day_note"],
                         "Státní svátek: Den vzniku samostatného československého státu – web neobjednává")
        self.assertEqual(self.R.board_data("2026-10-14")["day_note"], "")
        self.s.write({"booking_block_weekends": False, "booking_block_holidays": False})
        self.assertEqual(self.R.board_data("2026-10-17")["day_note"], "")

    def test_reception_books_on_weekend(self):
        self.reservation(start=self.dt(SAT, 10, 0))


@tagged("post_install", "-at_install")
class TestRucniCas(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
            cls.hours(cls, cls.room2, wd, 8.0, 18.0)
        cls.env["elite.vet.setting"].nastaveni().write({"booking_require_doctor": False, "booking_slot_step": 15})
        cls.day = fields.Date.today() + timedelta(days=10)
        cls.W = cls.env["elite.vet.reservation.wizard"]
        cls.R = cls.env["elite.vet.reservation"]

    def z_tabule(self, minute, room, **vals):
        """Průvodce otevřený klikem do buňky tabule."""
        base = {"procedure_id": self.vacc.id}
        base.update(vals)
        return self.W.with_context(default_date=fields.Date.to_string(self.day), default_minute=minute,
                                   default_room_id=room.id).create(base)

    def ulozit(self, w):
        w.write({"partner_mode": "new", "contact_name": "Ruční Klient", "contact_phone": "+420 606 000 111",
                 "contact_email": "rucni@example.cz", "pet_name": "Bobík", "pet_species": "dog"})
        w.action_krok_souhrn()
        w.action_ulozit()
        return self.R.search([("contact_email", "=", "rucni@example.cz")])

    def test_click_outside_hours_prefills_manual_time(self):
        w = self.z_tabule(19 * 60, self.room1)
        w.action_krok_cas()
        self.assertEqual(w.step, "cas")
        self.assertTrue(w.manual)
        self.assertEqual((w.manual_room_id, w.manual_time), (self.room1, "19:00"))
        self.assertTrue(w.upozorneni.startswith("Mimo běžnou ordinační dobu – vkládáte ručně"))
        w.action_rucni_cas()
        self.assertEqual((w.step, w.minute, w.room_id), ("klient", 19 * 60, self.room1))
        r = self.ulozit(w)
        self.assertIn("(zadáno ručně)", w.souhrn)
        self.assertEqual((r.room_id, r.start, r.state), (self.room1, self.dt(self.day, 19, 0), "confirmed"))

    def test_click_into_web_block_is_normal_slot(self):
        self.R.create({"kind": "block", "block_scope": "web", "block_reason": "Jen telefonem",
                       "room_id": self.room1.id, "start": self.dt(self.day, 10), "stop": self.dt(self.day, 11)})
        w = self.z_tabule(600, self.room1)
        w.action_krok_cas()
        self.assertEqual(w.step, "klient")
        self.assertFalse(w.manual)

    def test_click_on_busy_time_is_not_manual(self):
        self.reservation(start=self.dt(self.day, 10, 0))
        w = self.z_tabule(600, self.room1)
        w.action_krok_cas()
        self.assertEqual(w.step, "cas")
        self.assertFalse(w.manual)
        self.assertIn("není pro tento úkon volný", w.upozorneni)

    def test_manual_collisions(self):
        self.reservation(start=self.dt(self.day, 19, 0))
        self.R.create({"kind": "block", "block_scope": "full", "block_reason": "Porada",
                       "room_id": self.room1.id, "start": self.dt(self.day, 20), "stop": self.dt(self.day, 21)})
        self.R.create({"kind": "block", "block_scope": "web", "block_reason": "Jen telefonem",
                       "room_id": self.room1.id, "start": self.dt(self.day, 21), "stop": self.dt(self.day, 22)})
        w = self.W.create({"procedure_id": self.vacc.id, "date": self.day})
        w.action_krok_cas()
        w.write({"manual": True, "manual_room_id": self.room1.id})
        with self.assertRaises(UserError):
            w.action_rucni_cas()                     # bez času
        for cas in ("19:00", "20:15"):
            w.manual_time = cas
            with self.assertRaises(UserError):
                w.action_rucni_cas()
        w.manual_time = "21:00"                      # blokace jen pro web nebrání
        w.action_rucni_cas()
        self.assertEqual(self.ulozit(w).start, self.dt(self.day, 21, 0))

    def test_manual_doctor_not_serving_and_closed_room(self):
        # Sál nemá ordinační dobu vůbec, lékařka tam neslouží: ručně to přesto jde.
        w = self.W.create({"procedure_id": self.vacc.id, "date": self.day, "doctor_id": self.dr_b.id})
        w.action_krok_cas()
        w.write({"manual": True, "manual_room_id": self.sal.id, "manual_time": "07:30"})
        w.action_rucni_cas()
        r = self.ulozit(w)
        self.assertEqual((r.room_id, r.doctor_id, r.start), (self.sal, self.dr_b, self.dt(self.day, 7, 30)))

    def test_manual_picks_serving_doctor(self):
        self.assign(self.dr_a, self.room2, self.day, 18.0, 20.0)
        w = self.W.create({"procedure_id": self.vacc.id, "date": self.day})
        w.action_krok_cas()
        w.write({"manual": True, "manual_room_id": self.room2.id, "manual_time": "18:30"})
        w.action_rucni_cas()
        self.assertEqual(w.slot_doctor_id, self.dr_a)

    def test_save_still_checks_overlap(self):
        w = self.W.create({"procedure_id": self.vacc.id, "date": self.day})
        w.action_krok_cas()
        w.write({"manual": True, "manual_room_id": self.room1.id, "manual_time": "19:00"})
        w.action_rucni_cas()
        self.reservation(start=self.dt(self.day, 19, 0))   # mezitím obsadil někdo jiný
        with self.assertRaises(ValidationError):
            self.ulozit(w)


@tagged("post_install", "-at_install")
class TestDveLekarky(ReservationCase):

    def test_pruhy_sluzeb(self):
        sl, lanes, soubehy = pruhy_sluzeb([
            {"id": 1, "from": 480, "to": 840}, {"id": 2, "from": 600, "to": 960}, {"id": 3, "from": 900, "to": 1080}])
        self.assertEqual([s["lane"] for s in sorted(sl, key=lambda s: s["id"])], [0, 1, 0])
        self.assertEqual(lanes, 2)
        self.assertEqual([x["label"] for x in soubehy], ["2 lékařky 10:00–14:00", "2 lékařky 15:00–16:00"])
        self.assertEqual(pruhy_sluzeb([]), ([], 0, []))

    def test_board_data_two_doctors_in_room(self):
        self.hours(self.room1, 2, 8.0, 18.0)
        self.assign(self.dr_a, self.room1, WED, 8.0, 14.0)
        self.assign(self.dr_b, self.room1, WED, 10.0, 16.0)
        room = next(r for r in self.env["elite.vet.reservation"].board_data("2026-10-14")["rooms"]
                    if r["id"] == self.room1.id)
        self.assertEqual(room["lanes"], 2)
        self.assertEqual([o["label"] for o in room["overlaps"]], ["2 lékařky 10:00–14:00"])
        by_doc = {d["doctor_id"]: d for d in room["doctors"]}
        self.assertEqual({by_doc[self.dr_a.id]["lane"], by_doc[self.dr_b.id]["lane"]}, {0, 1})
        self.assertEqual(by_doc[self.dr_a.id]["color"], barva_lekarky(self.dr_a))
        self.assertEqual(by_doc[self.dr_a.id]["initials"], "AT")
        self.assertEqual(by_doc[self.dr_b.id]["time_label"], "10:00–16:00")
        # Kapacita ordinace zůstává jeden pacient naráz.
        self.reservation(start=self.dt(WED, 11, 0), doctor_id=self.dr_a.id)
        with self.assertRaises(ValidationError):
            self.reservation(start=self.dt(WED, 11, 0), doctor_id=self.dr_b.id)
