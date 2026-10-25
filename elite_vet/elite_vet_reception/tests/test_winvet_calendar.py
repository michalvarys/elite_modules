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
