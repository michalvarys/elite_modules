"""Task 30: WinVet appointments without a WinVet patient (title only) – Spárovat… in Dnes and on
the screen Ordinace, then the check-in. Synthetic data only."""
from datetime import timedelta

import pytz

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.models.winvet_calendar import PARAM_ENABLED

from .common import ReceptionCase

PRAGUE = pytz.timezone("Europe/Prague")


@tagged("post_install", "-at_install")
class TestWinvetPairing(ReceptionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1")
        cls.resource = cls.env["elite.vet.winvet.calendar.resource"].create({
            "winvet_ref": 9_300_001, "name": "Synthetic calendar T30", "visible": True, "room_id": cls.room.id})
        cls.activity = cls.env["elite.vet.winvet.calendar.activity"].create({
            "winvet_ref": 9_300_010, "name": "Synthetic vaccination T30"})
        cls.Event = cls.env["elite.vet.winvet.calendar.event"]
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role T30", "login": "pairing_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    # ------------------------------------------------------------------ helpers

    def event(self, key, hour, title="Synthetická Jana, přeočkování", **vals):
        start = self.today_utc(hour)
        values = {"key": key, "start": start, "stop": start + timedelta(minutes=30),
                  "resource_ids": [(6, 0, self.resource.ids)], "title": title,
                  "activity_id": self.activity.id}
        values.update(vals)
        event = self.Event.create(values)
        self.env.flush_all()
        return event

    def today(self, user=None):
        return self.api(user or self.reception).today_data()

    def row(self, event):
        rows = [r for r in self.today()["arriving"] if r.get("winvet_event_id") == event.id]
        return rows[0] if rows else None

    def room_item(self, event):
        column = [c for c in self.api(self.reception).room_board()["columns"] if c["room_id"] == self.room.id][0]
        items = [i for i in column["sections"]["booked"] if i.get("winvet_event_id") == event.id]
        return items[0] if items else None

    def local(self, utc):
        return pytz.utc.localize(utc).astimezone(PRAGUE).strftime("%Y-%m-%d %H:%M:%S")

    def push_same(self, event, **over):
        """The bridge pushes the entry again (same key) – no window, nothing is deleted."""
        rec = {"key": event.key, "id": 4242, "start": self.local(event.start), "end": self.local(event.stop),
               "all_day": False, "resource_ids": [self.resource.winvet_ref], "activity_id": self.activity.winvet_ref,
               "owner_id": None, "patient_id": None, "title": event.title, "busy_status": 2, "done": False,
               "modified": "2026-10-26 08:00:00"}
        rec.update(over)
        res = self.env["elite.vet.winvet.sync"].push({"entity": "calendar_events", "mode": "incremental",
                                                     "records": [rec], "deleted": []})
        self.assertTrue(res.get("ok"), res)
        self.env.flush_all()
        event.invalidate_recordset()

    # ------------------------------------------------------------------ tests

    def test_title_only_entries_listed(self):
        title_only = self.event("t30-1", 9)
        note = self.event("t30-2", 11, title="Oběd", activity_id=False)        # staff note
        done = self.event("t30-3", 12, done=True)                               # done in WinVet
        all_day = self.event("t30-4", 0, all_day=True)                          # all-day
        row = self.row(title_only)
        self.assertTrue(row)
        self.assertEqual((row["pet_id"], row["needs_pairing"], row["paired_manually"], row["winvet_title"],
                          row["search_hint"]),
                         (None, True, False, "Synthetická Jana, přeočkování", "Synthetická Jana"))
        for other in (note, done, all_day):
            self.assertIsNone(self.row(other))
        item = self.room_item(title_only)
        self.assertEqual((item["pet_id"], item["needs_pairing"], item["pet_name"]),
                         (None, True, "Synthetická Jana, přeočkování"))
        self.assertIsNone(self.room_item(note))
        with self.assertRaises(UserError):
            self.api(self.reception).check_in_winvet(title_only.id)

    def test_search_hint(self):
        hint = self.Reception._winvet_search_hint
        self.assertEqual(hint("Pištěková - pes - 2,5 roku má kulku"), "Pištěková")
        self.assertEqual(hint("Kateřina Topolová / Vakcinace"), "Kateřina Topolová")
        self.assertEqual(hint("Tulejová Diana, přeočkování kocourka"), "Tulejová Diana")
        self.assertEqual(hint("Novák Jan Pavel kontrola"), "Novák Jan")
        self.assertEqual(hint(False), "")

    def test_pair_existing_pet_then_check_in(self):
        event = self.event("t30-10", 9)
        pet = self.new_pet("Párek T30")
        written = event.winvet_modified
        result = self.api(self.reception).pair_winvet(event.id, pet.partner_id.id, pet.id)
        self.assertEqual((result["pet_id"], result["partner_id"]), (pet.id, pet.partner_id.id))
        self.assertEqual((event.manual_pet_id, event.manual_partner_id, event.matched_by_id),
                         (pet, pet.partner_id, self.reception))
        self.assertTrue(event.matched_at)
        self.assertEqual((event.effective_pet_id, event.effective_partner_id), (pet, pet.partner_id))
        self.assertFalse(event.pet_id)   # the WinVet data stay as they were
        self.assertEqual(event.winvet_modified, written)
        row = self.row(event)
        self.assertEqual((row["pet_id"], row["pet_name"], row["needs_pairing"], row["paired_manually"]),
                         (pet.id, pet.name, False, True))
        # room screen: the pet (Otevřít kartu) and the board card with the pet name
        item = self.room_item(event)
        self.assertEqual((item["pet_id"], item["pet_name"], item["needs_pairing"]), (pet.id, pet.name, False))
        board = self.env["elite.vet.reservation"].with_user(self.reception).board_data(self.today()["date"])
        card = [e for e in board["events"] if e.get("winvet_event_id") == event.id][0]
        self.assertEqual(card["pet"], pet.name)
        self.assertIn(pet.name, card["name"])
        # check-in after pairing: the visit of the paired pet
        record = self.Record.browse(self.api(self.reception).check_in_winvet(event.id, "Jana")["record_id"])
        self.assertEqual((record.pet_id, record.winvet_event_id, record.visit_stage), (pet, event, "waiting"))
        self.assertIsNone(self.row(event))
        with self.assertRaises(UserError):   # checked in: the pairing is fixed
            self.api(self.reception).unpair_winvet(event.id)
        with self.assertRaises(UserError):
            self.api(self.reception).pair_winvet(event.id, pet.partner_id.id, pet.id)

    def test_pair_new_client_and_pet(self):
        event = self.event("t30-20", 10)
        api = self.api(self.reception)
        owner = api.save_owner({"name": "Synthetická Jana T30"})["owner"]
        data = api.save_pet(owner["id"], {"name": "Micka T30", "species": "cat"})
        pet_id = data["pets"][0]["id"]
        api.pair_winvet(event.id, owner["id"], pet_id)
        self.assertEqual(event.effective_pet_id.id, pet_id)
        self.assertEqual(self.row(event)["owner"], "Synthetická Jana T30")

    def test_sync_keeps_manual_pairing_and_winvet_match_wins(self):
        event = self.event("t30-30", 11)
        pet = self.new_pet("Synchronek T30")
        self.api(self.reception).pair_winvet(event.id, pet.partner_id.id, pet.id)
        # the same entry again with a new text: the pairing stays
        self.push_same(event, title="Synthetická Jana, přeočkování (změna)")
        self.assertEqual(event.title, "Synthetická Jana, přeočkování (změna)")
        self.assertEqual((event.manual_pet_id, event.effective_pet_id), (pet, pet))
        # even a sync write naming the pairing fields does not touch them
        event.with_context(winvet_sync=True).write({"manual_pet_id": False, "busy_status": 3})
        self.assertEqual((event.manual_pet_id, event.busy_status), (pet, 3))
        # WinVet later sends its own patient: that one wins, the manual pairing is the fallback
        winvet_pet = self.new_pet("WinVetík T30")
        winvet_pet.sudo().write({"winvet_ref": 9_300_100})
        self.push_same(event, patient_id=9_300_100)
        self.assertEqual(event.pet_id, winvet_pet)
        self.assertEqual(event.effective_pet_id, winvet_pet)
        self.assertEqual(event.manual_pet_id, pet)
        row = self.row(event)
        self.assertEqual((row["pet_id"], row["paired_manually"]), (winvet_pet.id, False))
        with self.assertRaises(UserError):
            self.api(self.reception).pair_winvet(event.id, pet.partner_id.id, pet.id)
        # WinVet drops its patient again: back to the manual pairing
        self.push_same(event, patient_id=None)
        self.assertEqual(event.effective_pet_id, pet)

    def test_unpair(self):
        event = self.event("t30-40", 12)
        pet = self.new_pet("Rozpárek T30")
        api = self.api(self.nurse)
        api.pair_winvet(event.id, pet.partner_id.id, pet.id)
        result = api.unpair_winvet(event.id)
        self.assertEqual(result["winvet_event_id"], event.id)
        self.assertFalse(event.manual_pet_id or event.manual_partner_id or event.matched_by_id or event.matched_at)
        self.assertTrue(self.row(event)["needs_pairing"])
        with self.assertRaises(UserError):   # nothing to unpair
            api.unpair_winvet(event.id)

    def test_refusals(self):
        event = self.event("t30-50", 13)
        dead = self.new_pet("Uhynulík T30")
        dead.deceased = True
        with self.assertRaises(UserError):
            self.api(self.reception).pair_winvet(event.id, dead.partner_id.id, dead.id)
        other_owner = self.env["res.partner"].create({"name": "Jiný majitel T30"})
        pet = self.new_pet("Cizí T30")
        with self.assertRaises(UserError):   # the pet must belong to the owner
            self.api(self.reception).pair_winvet(event.id, other_owner.id, pet.id)
        done = self.event("t30-51", 14, done=True)
        with self.assertRaises(UserError):
            self.api(self.reception).pair_winvet(done.id, pet.partner_id.id, pet.id)
        with self.assertRaises(AccessError):
            self.api(self.outsider).pair_winvet(event.id, pet.partner_id.id, pet.id)
        with self.assertRaises(AccessError):
            self.api(self.outsider).unpair_winvet(event.id)
        # the entry itself stays read-only outside the pairing API
        with self.assertRaises(UserError):
            event.write({"manual_pet_id": pet.id})
        with self.assertRaises(UserError):
            event.with_context(winvet_manual_match=True).write({"title": "x"})
        for user in (self.nurse, self.doctor_user, self.manager):
            self.api(user).pair_winvet(event.id, pet.partner_id.id, pet.id)
            self.api(user).unpair_winvet(event.id)

    def test_assets(self):
        from odoo.tools.misc import file_open
        with file_open("elite_vet_reception/static/src/pos/card_index_dialog/card_index_dialog.js") as f:
            js = f.read()
        self.assertIn('"winvet"', js)
        self.assertIn("pair_winvet", js)
        self.assertNotIn("@point_of_sale", js)   # also loaded in the backend (screen Ordinace)
        with file_open("elite_vet_reception/static/src/room_board/room_board.xml") as f:
            self.assertIn("Spárovat…", f.read())
        with file_open("elite_vet_reception/__manifest__.py") as f:
            self.assertIn("static/src/pos/card_index_dialog/*", f.read())
