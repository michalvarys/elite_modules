"""WinVet calendar entries (elite_vet_winvet, contract v4) in Dnes and on the till board."""
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_winvet.models.winvet_calendar import PARAM_ENABLED

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestWinvetCalendarReception(ReceptionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "1")
        cls.resource = cls.env["elite.vet.winvet.calendar.resource"].create({
            "winvet_ref": 9_100_001, "name": "Synthetic calendar", "visible": True, "room_id": cls.room.id})
        cls.Event = cls.env["elite.vet.winvet.calendar.event"]

    def event(self, key, hour, pet=None, days=0, **vals):
        start = self.today_utc(hour) + timedelta(days=days)
        values = {"key": key, "start": start, "stop": start + timedelta(minutes=30),
                  "resource_ids": [(6, 0, self.resource.ids)], "title": "Synthetic %s" % key}
        if pet:
            values.update({"pet_id": pet.id, "partner_id": pet.partner_id.id})
        values.update(vals)
        return self.Event.create(values)

    def arriving(self, user=None):
        return self.api(user or self.reception).today_data()["arriving"]

    def test_listed_and_checked_in(self):
        pet = self.new_pet("Winvetík")
        event = self.event("t25-1", 9, pet=pet)
        self.event("t25-2", 10)                       # no pet in the card index: not listed
        self.event("t25-3", 11, pet=pet, done=True)   # done in WinVet: not listed
        self.event("t25-4", 9, pet=pet, days=1)       # tomorrow
        rows = [r for r in self.arriving() if r.get("winvet_event_id")]
        self.assertEqual([r["winvet_event_id"] for r in rows], [event.id])
        row = rows[0]
        self.assertEqual((row["key"], row["pet_id"], row["room"], row["source"]),
                         ("w-%s" % event.id, pet.id, self.room.name, "winvet"))
        self.assertIsNone(row["reservation_id"])
        written = event.write_date

        result = self.api(self.reception).check_in_winvet(event.id, employee_name="Jana", note="Synthetic note")
        record = self.Record.browse(result["record_id"])
        self.assertEqual(record.winvet_event_id, event)
        self.assertEqual(record.room_id, self.room)
        self.assertEqual(record.pet_id, pet)
        self.assertEqual(record.visit_stage, "waiting")
        self.assertEqual(record.reception_note, "Synthetic note")
        self.assertFalse(record.reservation_id)
        self.assertFalse([r for r in self.arriving() if r.get("winvet_event_id")])
        # again (second till) = the same visit; the entry itself never changes
        again = self.api(self.reception).check_in_winvet(event.id)
        self.assertEqual(again["record_id"], record.id)
        self.assertEqual(event.write_date, written)
        self.assertIn(record.id, [w["record_id"] for w in self.api(self.reception).today_data()["waiting"]])

    def booked_on_room_screen(self):
        data = self.api(self.reception).room_board()
        column = [c for c in data["columns"] if c["room_id"] == self.room.id][0]
        return column, [i for i in column["sections"]["booked"] if i.get("source") == "winvet"]

    def test_room_screen_lists_winvet_appointments(self):
        pet = self.new_pet("Winvetík Ordinace")
        with_pet = self.event("t35-1", 9, pet=pet)
        title_only = self.event("t35-2", 10, title="Synthetic client without card",
                                partner_id=pet.partner_id.id)   # a client, no pet matched
        self.event("t35-3", 12, title="Synthetic lunch")        # no client, no activity: a note
        self.event("t35-4", 11, pet=pet, done=True)             # done in WinVet
        self.event("t35-5", 0, pet=pet, all_day=True)           # all-day note
        self.event("t35-6", 9, pet=pet, days=1)                 # tomorrow
        # the sync writes the entries in its own request; here their stored day / room
        # (computed) must be written before the screen searches them
        self.env.flush_all()
        column, items = self.booked_on_room_screen()
        self.assertEqual([i["winvet_event_id"] for i in items], [with_pet.id, title_only.id])
        self.assertEqual(column["counts"]["booked"], len(column["sections"]["booked"]))
        first = items[0]
        self.assertEqual((first["pet_id"], first["stage"], first["draggable"], first["record_id"]),
                         (pet.id, "booked", False, None))
        self.assertEqual(items[1]["pet_name"], "Synthetic client without card")
        # checked in at the till: leaves "Dnes ještě přijdou" (the visit record takes over)
        self.api(self.reception).check_in_winvet(with_pet.id)
        _column, items = self.booked_on_room_screen()
        self.assertEqual([i["winvet_event_id"] for i in items], [title_only.id])

    def test_refused_cases_and_switch_off(self):
        pet = self.new_pet("Zítřek")
        tomorrow = self.event("t25-10", 9, pet=pet, days=1)
        without_pet = self.event("t25-11", 9)
        with self.assertRaises(UserError):
            self.api(self.reception).check_in_winvet(tomorrow.id)
        with self.assertRaises(UserError):
            self.api(self.reception).check_in_winvet(without_pet.id)
        today = self.event("t25-12", 12, pet=pet)
        self.env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, "0")
        self.assertFalse([r for r in self.arriving() if r.get("winvet_event_id")])
        with self.assertRaises(UserError):
            self.api(self.reception).check_in_winvet(today.id)

    def test_till_board_shows_read_only_entries(self):
        pet = self.new_pet("Tabulík")
        event = self.event("t25-20", 9, pet=pet)
        self.reservation(11, pet=pet)
        day = self.api(self.reception).today_data()["date"]
        data = self.env["elite.vet.reservation"].with_user(self.reception).board_data(day)
        winvet = [e for e in data["events"] if e["kind"] == "winvet"]
        self.assertEqual([(e["id"], e["winvet_event_id"], e["room_id"]) for e in winvet],
                         [(-event.id, event.id, self.room.id)])
        self.assertFalse(winvet[0]["is_second_room"])
        self.assertFalse(winvet[0]["payment_state"])
        self.assertIn(pet.name, winvet[0]["name"])
