"""Task 29: Zrušit přijetí – the reception takes back a check-in done by mistake (POS Dnes)."""
from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import file_open, mute_logger

from odoo.addons.elite_vet_winvet.models.winvet_calendar import PARAM_ENABLED

from .common import ReceptionCase

NOTE = "Přijetí zrušila recepce (Jana)."


@tagged("post_install", "-at_install")
class TestUndoCheckIn(ReceptionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1")
        cls.resource = cls.env["elite.vet.winvet.calendar.resource"].create({
            "winvet_ref": 9_290_001, "name": "Synthetic calendar T29", "visible": True, "room_id": cls.room.id})
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role T29", "login": "undo_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def today(self, user=None):
        return self.api(user or self.reception).today_data()

    def arriving_keys(self):
        return {r["key"] for r in self.today()["arriving"]}

    def waiting_ids(self):
        return {w["record_id"] for w in self.today()["waiting"]}

    def waiting_row(self, record):
        return [w for w in self.today()["waiting"] if w["record_id"] == record.id][0]

    def undo(self, record, user=None, employee="Jana"):
        return self.api(user or self.reception).undo_check_in(record.id, employee)

    def notes(self, thing):
        return thing.message_ids.filtered(lambda m: NOTE in (m.body or ""))

    def room_column(self):
        return [c for c in self.api(self.reception).room_board()["columns"] if c["room_id"] == self.room.id][0]

    # ---------------------------------------------------------------- reservation
    def test_reservation_back_in_arriving_and_again(self):
        pet = self.new_pet("Vrácený T29")
        res = self.reservation(9, 0, pet=pet)
        key = "r-%s" % res.id
        first = self.Record.browse(self.api(self.reception).check_in(res.id, "Jana", "Omylem")["record_id"])
        row = self.waiting_row(first)
        self.assertFalse(row["walk_in"])
        self.assertNotIn(key, self.arriving_keys())
        mails = self.env["mail.mail"].search_count([])

        result = self.undo(first)
        self.assertEqual((result["record_id"], result["state"], result["reservation_id"]),
                         (first.id, "cancelled", res.id))
        self.assertEqual(first.state, "cancelled", "kept for the history")
        self.assertFalse(first.reservation_id, "detached: the reservation can be checked in again")
        self.assertEqual(res.state, "confirmed")
        self.assertIn(key, self.arriving_keys())
        self.assertNotIn(first.id, self.waiting_ids())
        self.assertTrue(self.notes(first))
        self.assertTrue(self.notes(res))
        self.assertEqual(self.env["mail.mail"].search_count([]), mails, "no e-mail")
        # the room screen: booked again, not waiting
        column = self.room_column()
        self.assertNotIn(first.id, [i["record_id"] for i in column["sections"]["waiting"]])
        self.assertIn(res.id, [i["reservation_id"] for i in column["sections"]["booked"]])
        # the board shows it as checkable again
        my = self.Record.with_user(self.manager).my_patients_today()["items"]
        item = [i for i in my if i.get("reservation_id") == res.id][0]
        self.assertIsNone(item["record_id"])

        # check-in again = a new record of the reservation (the cancelled one stays)
        second = self.Record.browse(self.api(self.reception).check_in(res.id, "Jana")["record_id"])
        self.assertNotEqual(second, first)
        self.assertEqual((second.reservation_id, second.visit_stage, second.room_id), (res, "waiting", self.room))
        self.assertNotIn(key, self.arriving_keys())
        self.assertEqual(first.state, "cancelled")

    # ---------------------------------------------------------------- WinVet entry
    def test_winvet_entry_back_in_arriving(self):
        pet = self.new_pet("WinVet T29")
        start = self.today_utc(10)
        event = self.env["elite.vet.winvet.calendar.event"].create({
            "key": "t29-1", "start": start, "stop": start + timedelta(minutes=30), "title": "Synthetic T29",
            "resource_ids": [(6, 0, self.resource.ids)], "pet_id": pet.id, "partner_id": pet.partner_id.id})
        written = event.write_date
        key = "w-%s" % event.id
        first = self.Record.browse(self.api(self.reception).check_in_winvet(event.id, "Jana")["record_id"])
        self.assertFalse(self.waiting_row(first)["walk_in"])
        self.assertNotIn(key, self.arriving_keys())

        result = self.undo(first)
        self.assertEqual(result["winvet_event_id"], event.id)
        self.assertEqual(first.state, "cancelled")
        self.assertIn(key, self.arriving_keys())
        self.assertNotIn(first.id, self.waiting_ids())
        self.assertEqual(event.write_date, written, "the WinVet entry never changes")
        self.env.flush_all()
        column = self.room_column()
        self.assertIn(event.id, [i.get("winvet_event_id") for i in column["sections"]["booked"]])

        second = self.Record.browse(self.api(self.reception).check_in_winvet(event.id, "Jana")["record_id"])
        self.assertNotEqual(second, first)
        self.assertEqual((second.winvet_event_id, second.visit_stage), (event, "waiting"))
        self.assertNotIn(key, self.arriving_keys())

    # ---------------------------------------------------------------- walk-in
    def test_walk_in_disappears(self):
        pet = self.new_pet("Bez objednání T29")
        record = self.Record.browse(
            self.api(self.reception).walk_in(pet.id, employee_name="Jana", room_id=self.room.id)["record_id"])
        self.assertTrue(self.waiting_row(record)["walk_in"])
        arriving = self.arriving_keys()
        self.undo(record)
        self.assertEqual(record.state, "cancelled")
        self.assertNotIn(record.id, self.waiting_ids())
        self.assertEqual(self.arriving_keys(), arriving, "a walk-in does not go to Přicházejí")
        self.assertTrue(self.notes(record))
        column = self.room_column()
        self.assertNotIn(record.id, [i["record_id"] for s in column["sections"].values() for i in s])
        my = self.Record.with_user(self.manager).my_patients_today()
        self.assertNotIn(record.id, [i["record_id"] for i in my["items"] + my["unassigned"]])
        # a new walk-in of the same pet = a new record
        again = self.api(self.reception).walk_in(pet.id, employee_name="Jana")
        self.assertNotEqual(again["record_id"], record.id)
        # the user's name when the till sends no employee
        other = self.Record.browse(again["record_id"])
        self.api(self.reception).undo_check_in(other.id)
        self.assertTrue(other.message_ids.filtered(
            lambda m: ("Přijetí zrušila recepce (%s)." % self.reception.name) in (m.body or "")))

    # ---------------------------------------------------------------- refused
    @mute_logger("odoo.http")
    def test_refused_with_content(self):
        for field, value in (("anamnesis", "Kašle"), ("examination", "Bez nálezu"), ("diagnosis", "Zdravý"),
                             ("room_note", "Zaplatí zítra"), ("temperature", 38.5), ("weight", 12.0),
                             ("heart_rate", 90), ("respiratory_rate", 20)):
            with self.subTest(field=field):
                pet = self.new_pet("Obsah %s" % field)
                record = self.Record.browse(self.api(self.reception).walk_in(pet.id)["record_id"])
                record.sudo().write({field: value})
                with self.assertRaisesRegex(UserError, "zápis od lékaře/ky"):
                    self.undo(record)
                self.assertEqual((record.state, record.visit_stage), ("draft", "waiting"))
        pet = self.new_pet("Obsah položky")
        record = self.Record.browse(self.api(self.reception).walk_in(pet.id)["record_id"])
        self.env["elite.vet.clinical.record.line"].create({"record_id": record.id, "item_id": self.exam.id})
        with self.assertRaisesRegex(UserError, "zápis od lékaře/ky"):
            self.undo(record)
        self.assertEqual(record.state, "draft")

    def test_refused_in_room_done_other_day(self):
        pet = self.new_pet("V ordinaci T29")
        res = self.reservation(9, 30, pet=pet)
        record = self.Record.browse(self.api(self.reception).check_in(res.id)["record_id"])
        self.api(self.nurse).call_patient(record.id)
        with self.assertRaisesRegex(UserError, "Pacient už je v ordinaci"):
            self.undo(record)
        self.assertEqual((record.state, record.reservation_id), ("draft", res))
        record.sudo().action_done()
        with self.assertRaisesRegex(UserError, "uzavřená"):
            self.undo(record)
        # yesterday's waiting record
        old = self.Record.create({"pet_id": self.new_pet("Včera T29").id,
                                  "start": self.today_utc(10) - timedelta(days=1), "visit_stage": "waiting"})
        with self.assertRaisesRegex(UserError, "jen dnešní"):
            self.undo(old)
        self.assertEqual(old.state, "draft")
        # twice
        walk = self.Record.browse(self.api(self.reception).walk_in(self.new_pet("Dvakrát T29").id)["record_id"])
        self.undo(walk)
        with self.assertRaisesRegex(UserError, "už bylo zrušené"):
            self.undo(walk)
        with self.assertRaisesRegex(UserError, "nebyl nalezen"):
            self.api(self.reception).undo_check_in(10 ** 9)

    def test_rights(self):
        pet = self.new_pet("Práva T29")
        record = self.Record.browse(self.api(self.reception).walk_in(pet.id)["record_id"])
        with self.assertRaises(AccessError):
            self.undo(record, user=self.outsider)
        self.assertEqual(record.state, "draft")
        # reception and above
        for user in (self.nurse, self.doctor_user, self.manager):
            with self.subTest(user=user.login):
                rec = self.Record.browse(self.api(self.reception).walk_in(
                    self.new_pet("Práva %s" % user.login).id)["record_id"])
                self.undo(rec, user=user)
                self.assertEqual(rec.state, "cancelled")
        self.undo(record)
        self.assertEqual(record.state, "cancelled")

    def test_pos_assets(self):
        path = "elite_vet_reception/static/src/pos/today_screen/"
        with file_open(path + "today_screen.js") as f:
            js = f.read()
        with file_open(path + "today_screen.xml") as f:
            xml = f.read()
        self.assertIn('"undo_check_in"', js)
        self.assertIn("Pacient se vrátí mezi Přicházejí.", js)
        self.assertIn("Pacient zmizí z čekárny.", js)
        self.assertIn("o_ev_undo_check_in", xml)
        self.assertIn("row.stage === 'waiting'", xml)
