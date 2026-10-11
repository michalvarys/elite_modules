import json
from datetime import date, timedelta

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestControllers(HttpCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.elite_vet_reservation.controllers import booking
        booking._SUBMITS.clear()
        # rezervace z rucniho zkouseni by obsazovaly testovane sloty (vrati se rollbackem)
        self.env["elite.vet.reservation"].search([]).unlink()
        Room = self.env["elite.vet.room"]
        self.room = Room.create({"name": "Ordinace T", "color": "teal"})
        for wd in range(7):
            self.env["elite.vet.room.hours"].create({"room_id": self.room.id, "weekday": str(wd), "hour_from": 8.0, "hour_to": 18.0})
        self.proc = self.env["elite.vet.procedure"].create({"name": "Vaccination T", "duration": 15, "symbol": "V"})
        self.day = (date.today() + timedelta(days=3)).isoformat()

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
        # Obsadit je treba vsechny online ordinace (v DB jsou i osazene), jinak by slot zustal volny.
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
