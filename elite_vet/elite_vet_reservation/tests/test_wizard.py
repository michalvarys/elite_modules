"""Průvodce „Nová rezervace“ a živá aktualizace tabule (bus)."""
import json
from datetime import timedelta

import pytz

from odoo import fields
from odoo.addons.bus.models.bus import channel_with_db, json_dump
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestReservationWizard(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Celý den otevřeno, ať test „na dnešek“ projde v kteroukoli hodinu.
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 0.0, 24.0)
            cls.hours(cls, cls.room2, wd, 0.0, 24.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 24, "booking_slot_step": 15})
        cls.day = fields.Date.today() + timedelta(days=10)
        cls.W = cls.env["elite.vet.reservation.wizard"]
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.reception = Users.create({
            "name": "Recepce Průvodce", "login": "recepce_pruvodce", "email": "recepce@example.cz",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_reception").id])]})

    def wizard(self, **vals):
        base = {"procedure_id": self.vacc.id, "date": self.day}
        base.update(vals)
        return self.W.create(base)

    def lines(self, w):
        return [(ln.minute, ln.room_id.id, ln.doctor_id.id) for ln in w.slot_ids]

    def mails_to(self, email):
        return self.env["mail.mail"].search([("email_to", "ilike", email)])

    def fill_new_client(self, w, **vals):
        base = {"partner_mode": "new", "contact_name": "Jana Průvodcová", "contact_phone": "+420 606 111 222",
                "contact_email": "jana.pruvodce@example.cz", "pet_name": "Micka", "pet_species": "cat"}
        base.update(vals)
        w.write(base)

    def test_full_flow_creates_reservation_with_room_doctor_and_time(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        w = self.W.with_user(self.reception).create({"procedure_id": self.vacc.id, "date": self.day})
        w.action_krok_cas()
        self.assertEqual(w.step, "cas")
        line = w.slot_ids.filtered(lambda ln: ln.minute == 9 * 60 and ln.room_id == self.room2)
        self.assertEqual(line.doctor_id, self.dr_b)
        self.assertEqual(line.time_label, "9:00")
        line.action_vybrat()
        self.assertEqual(w.step, "klient")
        self.fill_new_client(w)
        w.action_krok_souhrn()
        self.assertEqual(w.step, "souhrn")
        self.assertIn("Ordinace 2", w.souhrn)
        w.action_ulozit()
        r = self.env["elite.vet.reservation"].search([("contact_email", "=", "jana.pruvodce@example.cz")])
        self.assertEqual(len(r), 1)
        self.assertEqual((r.state, r.source, r.kind), ("confirmed", "internal", "reservation"))
        self.assertEqual(r.room_id, self.room2)
        self.assertEqual(r.doctor_id, self.dr_b)
        self.assertEqual(r.start, self.dt(self.day, 9, 0))
        self.assertEqual(r.stop, self.dt(self.day, 9, 15))
        # Nový klient a mazlíček se založí přes párování.
        self.assertEqual(r.partner_id.name, "Jana Průvodcová")
        self.assertTrue(r.partner_id.is_vet_client)
        self.assertEqual(r.pet_id.name, "Micka")
        self.assertEqual(r.pet_id.partner_id, r.partner_id)
        self.assertEqual(r.pet_id.species, "cat")

    def test_slots_respect_doctor_and_busy_times(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room2.id)
        w = self.wizard(doctor_id=self.dr_b.id)
        w.action_krok_cas()
        got = self.lines(w)
        self.assertTrue(got)
        self.assertTrue(all(room == self.room2.id and doc == self.dr_b.id for _m, room, doc in got))
        self.assertNotIn((9 * 60, self.room2.id, self.dr_b.id), got)
        self.assertIn((9 * 60 + 15, self.room2.id, self.dr_b.id), got)
        # Bez filtru lékařky je v 9:00 volno jen v ordinaci 1.
        w2 = self.wizard()
        w2.action_krok_cas()
        at9 = [(room, doc) for m, room, doc in self.lines(w2) if m == 9 * 60]
        self.assertEqual(at9, [(self.room1.id, self.dr_a.id)])

    def test_today_is_bookable_for_reception(self):
        now = pytz.utc.localize(fields.Datetime.now()).astimezone(self.TZ)
        if now.hour == 23 and now.minute >= 30:
            self.skipTest("Těsně před půlnocí už dnes volný čas není.")
        today = now.date()
        # Web (minimálně 24 h předem) dnes nic nenabídne, recepce ano.
        self.assertFalse(self.env["elite.vet.availability"].slots(self.vacc, today))
        w = self.wizard(date=today)
        w.action_krok_cas()
        self.assertTrue(w.slot_ids)
        now_min = now.hour * 60 + now.minute
        self.assertTrue(all(ln.minute >= now_min for ln in w.slot_ids))

    def test_day_navigation_and_next_free_day(self):
        w = self.wizard()
        w.action_krok_cas()
        w.action_den_dalsi()
        self.assertEqual(w.date, self.day + timedelta(days=1))
        w.action_den_predchozi()
        self.assertEqual(w.date, self.day)
        # Den bez ordinační doby přeskočí „Další volný den“.
        closed = self.day + timedelta(days=1)
        for room in (self.room1, self.room2):
            self.env["elite.vet.room.exception"].create({"room_id": room.id, "date": closed, "closed": True})
        w.action_dalsi_volny_den()
        self.assertEqual(w.date, self.day + timedelta(days=2))
        self.assertTrue(w.slot_ids)

    def test_prefilled_free_time_skips_slot_step(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        w = self.W.with_context(default_date=fields.Date.to_string(self.day), default_minute=600,
                                default_room_id=self.room1.id).create({"procedure_id": self.vacc.id})
        w.action_krok_cas()
        self.assertEqual(w.step, "klient")
        self.assertEqual((w.minute, w.room_id, w.slot_doctor_id), (600, self.room1, self.dr_a))

    def test_prefilled_busy_time_shows_slots(self):
        self.reservation(start=self.dt(self.day, 10, 0), room_id=self.room1.id)
        w = self.wizard(minute=600, room_id=self.room1.id)
        w.action_krok_cas()
        self.assertEqual(w.step, "cas")
        self.assertFalse(w.room_id)
        self.assertTrue(w.slot_ids)

    def test_existing_client_and_pet_are_reused(self):
        partner = self.env["res.partner"].create({"name": "Petr Stálý", "phone": "+420 777 888 999",
                                                  "email": "petr.staly@example.cz", "is_vet_client": True})
        pet = self.env["elite.vet.pet"].create({"name": "Brok", "partner_id": partner.id, "species": "dog"})
        w = self.wizard(minute=600, room_id=self.room1.id)
        w.action_krok_cas()
        w.write({"partner_mode": "existing", "partner_id": partner.id, "pet_id": pet.id})
        self.assertEqual(w.contact_email, "petr.staly@example.cz")
        self.assertTrue(w.send_email)
        w.action_krok_souhrn()
        n_partners = self.env["res.partner"].search_count([])
        w.action_ulozit()
        r = self.env["elite.vet.reservation"].search([("partner_id", "=", partner.id)])
        self.assertEqual(r.pet_id, pet)
        self.assertEqual(self.env["res.partner"].search_count([]), n_partners)

    def test_email_only_when_checked(self):
        w = self.wizard(minute=600, room_id=self.room1.id)
        w.action_krok_cas()
        self.fill_new_client(w, contact_email="bez.mailu@example.cz", send_email=False)
        w.action_krok_souhrn()
        w.action_ulozit()
        self.assertFalse(self.mails_to("bez.mailu@example.cz"))

        w = self.wizard(minute=660, room_id=self.room1.id)
        w.action_krok_cas()
        self.fill_new_client(w, contact_email="s.mailem@example.cz")
        self.assertTrue(w.send_email)
        w.action_krok_souhrn()
        w.action_ulozit()
        self.assertEqual(len(self.mails_to("s.mailem@example.cz")), 1)

    def test_client_step_validation(self):
        w = self.wizard(minute=600, room_id=self.room1.id)
        w.action_krok_cas()
        with self.assertRaises(UserError):
            w.action_krok_souhrn()   # existující klient nevybrán
        w.write({"partner_mode": "new", "contact_name": "Bez Kontaktu"})
        with self.assertRaises(UserError):
            w.action_krok_souhrn()   # chybí telefon i e-mail

    def test_overlap_is_refused_on_save(self):
        w = self.wizard(minute=600, room_id=self.room1.id)
        w.action_krok_cas()
        self.fill_new_client(w)
        w.action_krok_souhrn()
        # Mezitím termín obsadil někdo jiný.
        self.reservation(start=self.dt(self.day, 10, 0), room_id=self.room1.id)
        with self.assertRaises(ValidationError):
            w.action_ulozit()

    def test_procedure_required(self):
        w = self.W.create({"date": self.day})
        with self.assertRaises(UserError):
            w.action_krok_cas()

    def test_client_search_by_phone_digits(self):
        partner = self.env["res.partner"].create({"name": "Telefonní Klient", "phone": "+420 731 222 333"})
        P = self.env["res.partner"].with_context(ev_hledat_telefon=True)
        self.assertIn(partner.id, [i for i, _n in P.name_search("731222333")])
        self.assertNotIn(partner.id, [i for i, _n in self.env["res.partner"].name_search("731222333")])


@tagged("post_install", "-at_install")
class TestLiveUpdate(ReservationCase):

    def bus_messages(self):
        group = self.env.ref("elite_vet_reservation.group_reservation_reception")
        channel = json_dump(channel_with_db(self.env.cr.dbname, group))
        self.env.cr.precommit.run()   # zprávy bus.bus vznikají až před commitem
        msgs = [json.loads(m.message) for m in self.env["bus.bus"].sudo().search([("channel", "=", channel)], order="id")]
        return [m["payload"] for m in msgs if m["type"] == "elite_vet_reservation/changed"]

    def test_reception_group_is_a_subscribed_channel(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Recepce Bus", "login": "recepce_bus",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_manager").id])]})
        # Odoo odebírá kanály všech skupin uživatele; Správce implikuje Recepci.
        self.assertIn(self.env.ref("elite_vet_reservation.group_reservation_reception"), user.groups_id)

    def test_create_sends_one_message_per_transaction(self):
        self.env.cr.precommit.run()
        before = len(self.bus_messages())
        r = self.reservation(start=self.dt(fields.Date.today() + timedelta(days=5), 9, 0))
        r.write({"note": "změna"})
        msgs = self.bus_messages()
        self.assertEqual(len(msgs) - before, 1)
        self.assertFalse(msgs[-1]["new_web"])

    def test_web_request_flags_new_web(self):
        self.env.cr.precommit.run()
        self.reservation(start=self.dt(fields.Date.today() + timedelta(days=5), 9, 0),
                         state="web_new", source="web", room_id=False)
        payload = self.bus_messages()[-1]
        self.assertTrue(payload["new_web"])
        self.assertEqual(len(payload["web"]), 1)
        self.assertIn("Rex", payload["web"][0])

    def test_assignment_change_notifies(self):
        self.env.cr.precommit.run()
        before = len(self.bus_messages())
        self.assign(self.dr_a, self.room1, fields.Date.today() + timedelta(days=5), 8.0, 12.0)
        self.assertEqual(len(self.bus_messages()) - before, 1)
