"""Contract v4: the WinVet calendar (resources, activities, events) - synthetic data only."""
from datetime import date, datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.elite_vet_reservation.tests.common import ReservationCase

from ..models.winvet_calendar import PARAM_ENABLED
from .common import WinvetCase

WED = date(2026, 11, 18)   # Wednesday inside the pushed window
WINDOW = {"from": "2026-11-01", "to": "2026-11-30"}
NOW = datetime(2026, 11, 1, 7, 0)   # UTC, before every tested slot


@tagged("post_install", "-at_install")
class TestWinvetCalendar(WinvetCase, ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.A = cls.env["elite.vet.availability"]
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1")
        for room in (cls.room1, cls.room2):
            cls.hours(cls, room, WED.weekday(), 8.0, 18.0)
        cls.vaccination_cs = cls.env["elite.vet.procedure"].create(
            {"name": "Očkování psa", "duration": 15, "symbol": "O", "color": "green"})

    # ------------------------------------------------------------------ helpers

    def resources(self):
        self.push("calendar_resources", [
            {"id": self.ref(1), "name": "ORDINACE 1", "color": "#c9f6fd", "visible": True,
             "work_from": "08:00:00", "work_to": "20:00:00", "sequence": 1},
            {"id": self.ref(2), "name": "ordinace  2", "color": "#dfffcb", "visible": True,
             "work_from": "08:00:00", "work_to": "20:00:00", "sequence": 2},
            {"id": self.ref(3), "name": "Georgiana - sál", "color": None, "visible": False,
             "work_from": None, "work_to": None, "sequence": 4},
            {"id": self.ref(4), "name": "SAL", "color": "#ffb3ff", "visible": True,
             "work_from": None, "work_to": None, "sequence": 3},
        ], mode="full", run_id="res-1")
        self.push("calendar_activities", [
            {"id": self.ref(10), "name": "VACCINATION", "duration": 15, "color": "#1fdb3c", "symbol": "V",
             "web": True},
            {"id": self.ref(11), "name": "ockovani  PSA", "duration": 15, "color": None, "symbol": None,
             "web": False},
            {"id": self.ref(12), "name": "Něco jiného", "duration": 30, "color": None, "symbol": None,
             "web": False},
        ], mode="full", run_id="act-1")

    def event(self, key, start, end, resources=(1,), **over):
        rec = {"key": key, "id": int(key.split("-")[0]), "pattern_id": None, "recurring": "-" in key,
               "occurrence_date": None, "start": start, "end": end, "all_day": False,
               "resource_ids": [self.ref(r) for r in resources], "activity_id": self.ref(10),
               "owner_id": None, "patient_id": None, "title": "Synthetic title %s" % key,
               "busy_status": 2, "done": False, "modified": "2026-10-20 10:00:00"}
        rec.update(over)
        return rec

    def push_events(self, records, run_id="ev-1", window=None, batch=1, batches=1):
        res = self.sync.push({"entity": "calendar_events", "mode": "full", "records": records, "deleted": [],
                              "batch": batch, "batches": batches, "run_id": run_id, "window": window or WINDOW})
        self.assertTrue(res.get("ok"), res)
        return res

    def events(self):
        return self.env["elite.vet.winvet.calendar.event"].search([])

    def by_key(self, key):
        return self.env["elite.vet.winvet.calendar.event"].search([("key", "=", key)])

    def free(self, room, scope="internal"):
        slots = self.A.slots(self.vacc, WED, now=NOW, min_hours=0, max_days=400, rooms=room, scope=scope)
        return {s["time"] for s in slots}

    def standard_events(self):
        return [
            self.event("101", "2026-11-18 10:00:00", "2026-11-18 10:30:00"),
            self.event("102", "2026-11-18 00:00:00", "2026-11-19 00:00:00", resources=(2,), all_day=True,
                       title="Dovolená (synthetic)"),
            self.event("103", "2026-11-18 12:00:00", "2026-11-18 12:15:00", resources=(3,)),
            self.event("104-20261118", "2026-11-18 14:00:00", "2026-11-18 15:00:00", resources=(1, 2),
                       pattern_id=104, occurrence_date="2026-11-18"),
        ]

    # ------------------------------------------------------------------ mapping

    def test_resources_and_activities_map_by_name(self):
        self.resources()
        Res = self.env["elite.vet.winvet.calendar.resource"]
        by_ref = {r.winvet_ref: r for r in Res.search([])}
        self.assertEqual(by_ref[self.ref(1)].room_id, self.room1)
        self.assertEqual(by_ref[self.ref(2)].room_id, self.room2)
        self.assertFalse(by_ref[self.ref(3)].room_id, "a hidden WinVet calendar stays unmapped")
        self.assertEqual(by_ref[self.ref(4)].room_id, self.surgery, "Sál = SAL (accents ignored)")
        Act = self.env["elite.vet.winvet.calendar.activity"]
        acts = {a.winvet_ref: a for a in Act.search([])}
        self.assertEqual(acts[self.ref(10)].procedure_id, self.vacc)
        self.assertEqual(acts[self.ref(11)].procedure_id, self.vaccination_cs)
        self.assertFalse(acts[self.ref(12)].procedure_id)
        # a manual mapping survives the next push; an automatic one follows the names
        by_ref[self.ref(2)].room_id = self.surgery
        self.assertTrue(by_ref[self.ref(2)].room_manual)
        self.resources()
        self.assertEqual(by_ref[self.ref(2)].room_id, self.surgery)
        self.assertEqual(by_ref[self.ref(1)].room_id, self.room1)

    # ------------------------------------------------------------------ import

    def test_import_update_and_delete_in_window(self):
        self.resources()
        mails, messages = self.env["mail.mail"].search_count([]), self.env["mail.message"].search_count([])
        old = self.event("90", "2026-10-10 09:00:00", "2026-10-10 09:15:00")
        self.push_events([old], run_id="old", window={"from": "2026-10-01", "to": "2026-10-31"})
        res = self.push_events(self.standard_events())
        self.assertEqual(res["created"], 4)
        timed = self.by_key("101")
        self.assertEqual(timed.room_ids, self.room1)
        self.assertEqual(timed.start, self.dt(WED, 10))
        self.assertEqual(timed.date, WED)
        self.assertEqual(timed.activity_id.procedure_id, self.vacc)
        self.assertEqual(timed.name, "Synthetic title 101")
        self.assertEqual(self.by_key("104-20261118").room_ids, self.room1 | self.room2)
        self.assertFalse(self.by_key("103").room_ids, "hidden WinVet calendar = no room")
        all_day = self.by_key("102")
        self.assertTrue(all_day.all_day)
        self.assertEqual((all_day.date, all_day.end_date), (WED, WED))

        # update: changed title; delete: 103 gone from WinVet; the October event is outside the window
        records = self.standard_events()
        records[0]["title"] = "Changed synthetic"
        records = [r for r in records if r["key"] != "103"]
        res = self.push_events(records[:2], run_id="ev-2", batch=1, batches=2)
        self.assertTrue(self.by_key("103"), "nothing is deleted before the last batch")
        res = self.push_events(records[2:], run_id="ev-2", batch=2, batches=2)
        self.assertEqual(res["deleted"], 1)
        self.assertFalse(self.by_key("103"))
        self.assertEqual(self.by_key("101").name, "Changed synthetic")
        self.assertTrue(self.by_key("90"), "events outside the pushed window are kept")
        # no e-mails, no chatter
        self.assertEqual(self.env["mail.mail"].search_count([]), mails)
        self.assertEqual(self.env["mail.message"].search_count([]), messages)
        self.assertNotIn("message_ids", self.env["elite.vet.winvet.calendar.event"]._fields)
        status = self.env["elite.vet.winvet.status"].get_status()
        self.assertIn("calendar_events", status.entity_ids.mapped("entity"))

    def test_client_and_pet_from_the_card_index(self):
        self.resources()
        self.push("owners", [self.owner(201)])
        self.push("patients", [self.patient(202, 201)])
        pet = self.find("elite.vet.pet", 202)
        self.push_events([
            self.event("110", "2026-11-18 09:00:00", "2026-11-18 09:15:00",
                       owner_id=self.ref(201), patient_id=self.ref(202)),
            self.event("111", "2026-11-18 09:30:00", "2026-11-18 09:45:00", owner_id=self.ref(999)),
        ])
        matched, unmatched = self.by_key("110"), self.by_key("111")
        self.assertEqual(matched.pet_id, pet)
        self.assertEqual(matched.partner_id, pet.partner_id)
        self.assertEqual(matched._label(), "%s (%s)" % (pet.name, pet.partner_id.name))
        self.assertFalse(unmatched.partner_id)
        self.assertEqual(unmatched._label(), "Synthetic title 111")

    def test_read_only(self):
        self.resources()
        self.push_events(self.standard_events())
        event = self.by_key("101")
        with self.assertRaises(UserError):
            event.write({"title": "x"})
        with self.assertRaises(UserError):
            event.unlink()
        reception_user = self.env["res.users"].create({
            "name": "T25 recepce", "login": "t25_reception_calendar",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        as_reception = event.with_user(reception_user)
        self.assertTrue(as_reception.read(["name"]))
        with self.assertRaises(Exception):
            as_reception.with_context(winvet_sync=True).write({"title": "x"})

    # ------------------------------------------------------------------ busy rule

    def test_timed_event_blocks_every_booking_path(self):
        self.resources()
        self.assign(self.dr_a, self.room1, WED, 8.0, 18.0)
        self.assign(self.dr_b, self.room2, WED, 8.0, 18.0)
        self.assertIn("10:00", self.free(self.room1))
        self.push_events(self.standard_events())
        # web (+ chat, they use the same slots) and reception (wizard, POS Objednat)
        for scope in ("web", "internal"):
            free = self.free(self.room1, scope)
            self.assertNotIn("10:00", free, scope)
            self.assertNotIn("10:15", free, scope)
            self.assertIn("10:30", free, scope)
            self.assertNotIn("14:00", free, scope)
        self.assertNotIn("14:30", self.free(self.room2), "an event in two calendars blocks both rooms")
        # the all-day note does not block
        self.assertIn("10:00", self.free(self.room2))
        # wizard manual time
        wizard = self.env["elite.vet.reservation.wizard"].create({"procedure_id": self.vacc.id, "date": WED})
        clash = wizard._collision(self.room1, 600)
        self.assertEqual(clash._name, "elite.vet.winvet.calendar.event")
        self.assertFalse(wizard._collision(self.room1, 630))
        self.assertFalse(wizard._collision(self.room2, 600))
        # the overlap check on save (board drop, every write)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.reservation(start=self.dt(WED, 10, 15), stop=self.dt(WED, 10, 30))
        ok = self.reservation(start=self.dt(WED, 10, 30), stop=self.dt(WED, 10, 45))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            ok.action_reschedule(self.dt(WED, 10, 0))
        self.env.invalidate_all()
        # blocks may be placed over a WinVet entry
        self.env["elite.vet.reservation"].create({
            "kind": "block", "room_id": self.room1.id, "start": self.dt(WED, 10), "stop": self.dt(WED, 10, 30),
            "block_reason": "T25 block"})

    def test_board_data(self):
        self.resources()
        self.push_events(self.standard_events())
        data = self.env["elite.vet.reservation"].board_data(WED.isoformat())
        winvet = [e for e in data["events"] if e["kind"] == "winvet"]
        self.assertEqual(sorted((e["room_id"], e["time_label"]) for e in winvet), sorted([
            (self.room1.id, "10:00–10:30"), (self.room1.id, "14:00–15:00"), (self.room2.id, "14:00–15:00")]))
        self.assertTrue(all(e["id"] < 0 and e["winvet_event_id"] for e in winvet))
        self.assertEqual({e["procedure"] for e in winvet}, {"VACCINATION"})
        notes = {r["id"]: r["winvet_notes"] for r in data["rooms"]}
        self.assertEqual([n["label"] for n in notes[self.room2.id]], ["Dovolená (synthetic)"])
        self.assertEqual(notes[self.room1.id], [])

    # ------------------------------------------------------------------ switch-off

    def test_switch_off_hides_unblocks_and_ignores_pushes(self):
        self.resources()
        self.assign(self.dr_a, self.room1, WED, 8.0, 18.0)
        self.push_events(self.standard_events())
        settings = self.env["elite.vet.winvet.calendar.settings"].create({})
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.event_count, 4)
        settings.action_disable()
        data = self.env["elite.vet.reservation"].board_data(WED.isoformat())
        self.assertFalse([e for e in data["events"] if e["kind"] == "winvet"])
        self.assertIn("10:00", self.free(self.room1))
        self.reservation(start=self.dt(WED, 10), stop=self.dt(WED, 10, 15))
        res = self.push_events([self.event("120", "2026-11-18 16:00:00", "2026-11-18 16:15:00")], run_id="off")
        self.assertEqual(res["skipped"], 1)
        self.assertFalse(self.by_key("120"))
        self.assertTrue(self.by_key("101"), "switching off keeps the rows (purge is separate)")
        settings.action_enable()
        self.assertNotIn("14:00", self.free(self.room1))
        settings.action_purge()
        self.assertFalse(self.events())
