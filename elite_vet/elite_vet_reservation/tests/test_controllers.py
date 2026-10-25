import json
from datetime import date, timedelta

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestControllers(HttpCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.elite_vet_reservation.controllers import booking
        booking._SUBMITS.clear()
        # reservations from manual testing would occupy the tested slots (restored by rollback)
        self.env["elite.vet.reservation"].search([]).unlink()
        Room = self.env["elite.vet.room"]
        self.room = Room.create({"name": "Ordinace T", "color": "teal"})
        for wd in range(7):
            self.env["elite.vet.room.hours"].create({"room_id": self.room.id, "weekday": str(wd), "hour_from": 8.0, "hour_to": 18.0})
        self.proc = self.env["elite.vet.procedure"].create({"name": "Vaccination T", "duration": 15, "symbol": "V"})
        self.day = (date.today() + timedelta(days=3)).isoformat()
        # "Today + 3" may fall on a weekend/holiday; those have their own test below.
        self.setting = self.env["elite.vet.setting"].nastaveni()
        # the public API books only with "Rezervace na webu" = Elite Vet (default WinVet, task 19)
        self.setting.write({"booking_block_weekends": False, "booking_block_holidays": False,
                            "web_booking_source": "elite"})

    def rpc(self, path, params):
        resp = self.url_open(path, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def good_submit(self, **over):
        data = {"procedure_id": self.proc.id, "date": self.day, "time": "10:00",
                "contact_name": "Jana Testová", "contact_email": "jana@example.cz", "contact_phone": "+420777111222",
                "pet_name": "Rex", "pet_species": "dog", "problem": "Očkování", "consent": True, "hp": ""}
        data.update(over)
        return data

    def test_options_lists_online_procedures(self):
        res = self.rpc("/rezervace/api/options", {})
        self.assertIn(self.proc.id, [p["id"] for p in res["procedures"]])
        proc = next(p for p in res["procedures"] if p["id"] == self.proc.id)
        self.assertIn("doctor_ids", proc)
        self.assertEqual(res["settings"]["step"], 15)

    def test_days_and_slots(self):
        y, m = int(self.day[:4]), int(self.day[5:7])
        days = self.rpc("/rezervace/api/days", {"procedure_id": self.proc.id, "year": y, "month": m})
        self.assertIn(self.day, days)
        slots = self.rpc("/rezervace/api/slots", {"procedure_id": self.proc.id, "date": self.day})
        self.assertIn("10:00", [s["time"] for s in slots])

    def test_public_slots_skip_non_online_room(self):
        # The theatre with opening hours is bookable by reception in the wizard, not by the web.
        surgery = self.env["elite.vet.room"].create({"name": "Sál T", "color": "purple", "online": False})
        for wd in range(7):
            self.env["elite.vet.room.hours"].create({"room_id": surgery.id, "weekday": str(wd), "hour_from": 8.0, "hour_to": 18.0})
        proc = self.env["elite.vet.procedure"].create({"name": "Sál úkon T", "duration": 15, "symbol": "S",
                                                       "room_ids": [(6, 0, surgery.ids)]})
        self.assertEqual(self.rpc("/rezervace/api/slots", {"procedure_id": proc.id, "date": self.day}), [])
        w = self.env["elite.vet.reservation.wizard"].create({"procedure_id": proc.id,
                                                             "date": date.fromisoformat(self.day)})
        w.action_step_time()
        self.assertIn(surgery, w.slot_ids.room_id)

    def test_submit_creates_waiting_reservation(self):
        res = self.rpc("/rezervace/api/submit", self.good_submit())
        self.assertTrue(res["ok"], res)
        rec = self.env["elite.vet.reservation"].search([("cancel_token", "=", res["token"])])
        self.assertEqual((rec.state, rec.source, rec.room_id.id), ("web_new", "web", False))
        self.assertEqual(rec.contact_name, "Jana Testová")
        self.assertEqual(rec.duration_minutes, 15)

    def test_submit_validation_errors(self):
        res = self.rpc("/rezervace/api/submit", self.good_submit(contact_email="neni-email", problem="", consent=False))
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "validation")
        self.assertEqual(set(res["fields"]), {"contact_email", "problem", "consent"})

    def test_rate_limit_counts_only_valid_submits(self):
        for _i in range(6):
            res = self.rpc("/rezervace/api/submit", self.good_submit(contact_email="neni-email"))
            self.assertEqual(res["error"], "validation")
        res = self.rpc("/rezervace/api/submit", self.good_submit())
        self.assertTrue(res["ok"], res)

    def test_submit_honeypot_silently_ok(self):
        res = self.rpc("/rezervace/api/submit", self.good_submit(hp="spam"))
        self.assertTrue(res["ok"])
        self.assertFalse(self.env["elite.vet.reservation"].search([("contact_email", "=", "jana@example.cz")]))

    def test_submit_slot_taken_when_confirmed(self):
        A = self.env["elite.vet.availability"]
        start = A.local_to_utc(date.fromisoformat(self.day), 600)
        # All online rooms must be taken (the DB holds seeded ones too), otherwise the slot would stay free.
        for room in self.proc.rooms_for_booking():
            self.env["elite.vet.reservation"].create({"procedure_id": self.proc.id, "room_id": room.id,
                                                      "state": "confirmed", "start": start, "contact_name": "X"})
        res = self.rpc("/rezervace/api/submit", self.good_submit())
        self.assertEqual((res["ok"], res["error"]), (False, "slot_taken"))

    def test_validate_submit_phone_normalisation(self):
        from odoo.addons.elite_vet_reservation.controllers.booking import validate_submit
        errors, clean = validate_submit(self.good_submit(contact_phone="777 111 222"))
        self.assertFalse(errors)
        self.assertEqual(clean["contact_phone"], "+420777111222")

    def test_web_api_skips_weekend_and_web_block(self):
        """The public API applies web rules: nothing on weekends, a web-only block takes the slot."""
        d = date.today() + timedelta(days=3)
        A = self.env["elite.vet.availability"]
        self.env["elite.vet.reservation"].create({
            "kind": "block", "block_scope": "web", "block_reason": "Jen telefonem", "room_id": self.room.id,
            "start": A.local_to_utc(d, 600), "stop": A.local_to_utc(d, 660)})
        # Other rooms from demo data may be free; only Ordinace T is checked.
        res = self.rpc("/rezervace/api/slots", {"procedure_id": self.proc.id, "date": self.day})
        times = [s["time"] for s in res if self.room.id in s["room_ids"]]
        self.assertIn("09:45", times)
        self.assertFalse({"10:00", "10:45"} & set(times))
        self.assertIn("11:00", times)
        self.setting.booking_block_weekends = True
        sat = d + timedelta(days=(5 - d.weekday()) % 7)
        self.assertEqual(self.rpc("/rezervace/api/slots", {"procedure_id": self.proc.id, "date": sat.isoformat()}), [])

    def test_pending_request_holds_slot(self):
        """A second web request for a time held by an unconfirmed request is rejected."""
        proc = self.env["elite.vet.procedure"].create({"name": "Jen T", "duration": 15, "symbol": "J",
                                                      "room_ids": [(6, 0, self.room.ids)]})
        first = self.rpc("/rezervace/api/submit", self.good_submit(procedure_id=proc.id))
        self.assertTrue(first["ok"])
        slots = self.rpc("/rezervace/api/slots", {"procedure_id": proc.id, "date": self.day})
        self.assertNotIn("10:00", [s["time"] for s in slots])
        second = self.rpc("/rezervace/api/submit", self.good_submit(procedure_id=proc.id, contact_name="Petr Druhý"))
        self.assertEqual(second["error"], "slot_taken")
