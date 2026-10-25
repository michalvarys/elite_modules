import json
from datetime import date, timedelta

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, tagged

WINVET_URL = "https://reservation.winvet.cz/booking/t23-test"


@tagged("post_install", "-at_install")
class TestWebBookingSwitch(HttpCase):
    """Task 19: "Rezervace na webu" switches /rezervacni-system between the WinVet form (by its
    address) and our wizard. WinVet is the default; in WinVet mode the public API refuses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, *groups):
            return Users.create({
                "name": "T23 %s" % login, "login": login,
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id] + [cls.env.ref(g).id for g in groups])]})

        cls.manager = user("t23_manager", "elite_vet_reservation.group_reservation_manager")
        cls.calendar_manager = user("t23_calendar", "elite_vet_calendar.group_calendar_manager")
        cls.reception = user("t23_reception", "elite_vet_reservation.group_reservation_reception")

    def setUp(self):
        super().setUp()
        from odoo.addons.elite_vet_reservation.controllers import booking
        booking._SUBMITS.clear()
        self.env["elite.vet.reservation"].search([]).unlink()
        self.env["elite.vet.room"].search([]).write({"active": False})
        self.room = self.env["elite.vet.room"].create({"name": "Ordinace T23", "color": "teal"})
        for wd in range(7):
            self.env["elite.vet.room.hours"].create({"room_id": self.room.id, "weekday": str(wd),
                                                    "hour_from": 8.0, "hour_to": 18.0})
        self.proc = self.env["elite.vet.procedure"].create({"name": "Očkování T23", "duration": 15, "symbol": "V"})
        self.day = (date.today() + timedelta(days=3)).isoformat()
        self.setting = self.env["elite.vet.setting"].nastaveni()
        self.setting.write({"booking_block_weekends": False, "booking_block_holidays": False,
                            "booking_require_doctor": False, "booking_url": WINVET_URL})

    def rpc(self, path, params):
        resp = self.url_open(path, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                             headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def submit_data(self):
        return {"procedure_id": self.proc.id, "date": self.day, "time": "10:00",
                "contact_name": "Jana Testová", "contact_email": "jana@example.cz",
                "contact_phone": "+420777111222", "pet_name": "Rex", "pet_species": "dog",
                "problem": "Očkování", "consent": True, "hp": ""}

    # ------------------------------------------------------------------ default
    def test_default_is_winvet(self):
        Setting = self.env["elite.vet.setting"]
        self.assertEqual(Setting._fields["web_booking_source"].default(Setting), "winvet")
        self.assertTrue(Setting._fields["web_booking_source"].required)
        # the record of this (freshly installed) database, before any test changes it
        self.env.cr.execute("SELECT web_booking_source FROM elite_vet_setting")
        self.assertEqual({r[0] for r in self.env.cr.fetchall()}, {"winvet"})
        # a new record without values (nastaveni() on an empty database)
        self.assertEqual(Setting.sudo().create({}).web_booking_source, "winvet")

    def test_upgrade_of_a_database_without_the_field(self):
        """An upgrade adds the column; existing rows get WinVet (what production shows today)."""
        self.setting.web_booking_source = "elite"
        self.env.flush_all()
        self.env.cr.execute("ALTER TABLE elite_vet_setting DROP COLUMN web_booking_source")
        # what -u does for the model: create the missing column, fill the default, set NOT NULL
        self.env.registry.init_models(self.env.cr, ["elite.vet.setting"], dict(self.env.context), install=False)
        self.env.invalidate_all()
        self.env.cr.execute("SELECT count(*), count(*) FILTER (WHERE web_booking_source = 'winvet') "
                            "FROM elite_vet_setting")
        total, winvet = self.env.cr.fetchone()
        self.assertTrue(total)
        self.assertEqual(total, winvet)
        self.assertEqual(self.setting.web_booking_source, "winvet")

    # ------------------------------------------------------------------ page
    def test_page_winvet_shows_the_iframe(self):
        self.setting.web_booking_source = "winvet"
        html = self.url_open("/rezervacni-system").text
        self.assertIn('src="%s"' % WINVET_URL, html)
        self.assertIn('class="evrez-nacitani"', html)
        self.assertIn("evrez-spinner", html)
        self.assertNotIn('id="ev-booking"', html)

    def test_page_elite_shows_our_wizard(self):
        self.setting.web_booking_source = "elite"
        html = self.url_open("/rezervacni-system").text
        self.assertIn('id="ev-booking"', html)
        self.assertNotIn("<iframe", html.split('id="ev-booking"')[1].split("evrez-rozpis")[0])
        self.assertNotIn(WINVET_URL, html)
        self.assertNotIn('class="evrez-nacitani"', html)

    # ------------------------------------------------------------------ public API
    def test_winvet_refuses_public_booking(self):
        self.setting.web_booking_source = "winvet"
        y, m = int(self.day[:4]), int(self.day[5:7])
        for path, params in (("/rezervace/api/options", {}),
                             ("/rezervace/api/days", {"procedure_id": self.proc.id, "year": y, "month": m}),
                             ("/rezervace/api/days", {"procedure_id": self.proc.id, "year": y, "month": m,
                                                      "with_holidays": True}),
                             ("/rezervace/api/slots", {"procedure_id": self.proc.id, "date": self.day}),
                             ("/rezervace/api/submit", self.submit_data())):
            res = self.rpc(path, params)
            self.assertEqual(res["ok"], False, path)
            self.assertEqual(res["error"], "web_booking_off", path)
            self.assertTrue(res["message"], path)
            self.assertTrue(res["url"].endswith("/rezervacni-system"), path)
            self.assertNotIn("procedures", res)
        self.assertFalse(self.env["elite.vet.reservation"].search([("contact_email", "=", "jana@example.cz")]))

    def test_elite_accepts_public_booking(self):
        self.setting.web_booking_source = "elite"
        options = self.rpc("/rezervace/api/options", {})
        self.assertIn(self.proc.id, [p["id"] for p in options["procedures"]])
        slots = self.rpc("/rezervace/api/slots", {"procedure_id": self.proc.id, "date": self.day})
        self.assertIn("10:00", [s["time"] for s in slots])
        res = self.rpc("/rezervace/api/submit", self.submit_data())
        self.assertTrue(res["ok"], res)
        rec = self.env["elite.vet.reservation"].search([("cancel_token", "=", res["token"])])
        self.assertEqual((rec.state, rec.source), ("web_new", "web"))

    def test_winvet_keeps_internal_booking(self):
        """The backend wizard (and so the board and the POS, which use the same models) still books."""
        self.setting.web_booking_source = "winvet"
        w = self.env["elite.vet.reservation.wizard"].create({"procedure_id": self.proc.id,
                                                             "date": date.fromisoformat(self.day)})
        w.action_step_time()
        self.assertIn(self.room, w.slot_ids.room_id)
        rec = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "procedure_id": self.proc.id, "room_id": self.room.id,
            "start": self.env["elite.vet.availability"].local_to_utc(date.fromisoformat(self.day), 600),
            "contact_name": "Recepce T23", "pet_name": "Rex"})
        self.assertEqual(rec.state, "confirmed")

    # ------------------------------------------------------------------ rights and validation
    def test_only_manager_switches(self):
        for user in (self.calendar_manager, self.reception):
            with self.assertRaises(AccessError):
                self.setting.with_user(user).write({"web_booking_source": "elite"})
        self.assertEqual(self.setting.web_booking_source, "winvet")
        self.setting.with_user(self.manager).write({"web_booking_source": "elite"})
        self.assertEqual(self.setting.web_booking_source, "elite")
        self.setting.with_user(self.manager).write({"web_booking_source": "winvet"})
        self.assertEqual(self.setting.web_booking_source, "winvet")
        # everybody reads it (the website as the public user too)
        public = self.env.ref("base.public_user")
        self.assertEqual(self.setting.with_user(public).web_booking_source, "winvet")

    def test_winvet_needs_the_address(self):
        s = self.setting.with_user(self.manager)
        s.write({"web_booking_source": "elite", "booking_url": False})
        with self.assertRaisesRegex(ValidationError, "adresu formuláře WinVet"), self.cr.savepoint():
            s.write({"web_booking_source": "winvet"})
        s.write({"web_booking_source": "winvet", "booking_url": WINVET_URL})
        with self.assertRaisesRegex(ValidationError, "adresu formuláře WinVet"), self.cr.savepoint():
            s.write({"booking_url": " "})
        # other settings can be saved on a record that never had the address
        self.env.cr.execute("UPDATE elite_vet_setting SET booking_url = NULL WHERE id = %s", [s.id])
        self.env.invalidate_all()
        s.write({"booking_slot_step": 20})
        self.assertEqual(s.booking_slot_step, 20)

    def test_form_shows_the_switch_next_to_the_address(self):
        view = self.env.ref("elite_vet_web.view_setting_rezervace_form")
        arch = self.env["elite.vet.setting"].with_user(self.manager).get_view(view.id, "form")["arch"]
        self.assertIn('name="web_booking_source"', arch)
        self.assertLess(arch.index('name="web_booking_source"'), arch.index('name="booking_url"'))
        self.assertIn("required=\"web_booking_source == 'winvet'\"", arch)
        self.assertIn("Adresa formuláře WinVet", arch)

    def test_text_under_the_booking_follows_the_wizard(self):
        """The text under the booking stays a sibling right after our wizard (booking.css
        centers it there with the selector `.evbk ~ .evrez-zprava-misto`)."""
        for lang in ["en_US"] + self.env["res.lang"].search([]).mapped("code"):
            self.setting.with_context(lang=lang).booking_loading_middle = "T23 text pod rezervací"
        self.setting.web_booking_source = "elite"
        html = self.url_open("/rezervacni-system").text
        wizard, place, text = (html.index('id="ev-booking"'), html.index('class="evrez-zprava-misto"'),
                               html.index("T23 text pod rezervací"))
        self.assertLess(wizard, place)
        self.assertLess(place, text)
        self.setting.web_booking_source = "winvet"
        html = self.url_open("/rezervacni-system").text
        self.assertIn('class="evrez-zprava-misto"', html)
        self.assertIn("T23 text pod rezervací", html)
