"""Task 24: web vs clinic reservations in the till (Tabule detail, board data, Dnes)."""
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestSourceVisible(ReceptionCase):

    def booked_by_reception(self, hour, pet):
        values = {"kind": "reservation", "state": "confirmed", "room_id": self.room.id,
                  "start": self.today_utc(hour, 0), "stop": self.today_utc(hour, 20),
                  "pet_id": pet.id, "partner_id": pet.partner_id.id, "source": "internal"}
        if self.procedure:
            values["procedure_id"] = self.procedure.id
        return self.env["elite.vet.reservation"].with_user(self.reception).create(values).with_env(self.env)

    def booked_on_web(self, hour, pet):
        values = {"kind": "reservation", "state": "confirmed", "room_id": self.room.id,
                  "start": self.today_utc(hour, 0), "stop": self.today_utc(hour, 20),
                  "pet_id": pet.id, "partner_id": pet.partner_id.id, "source": "web"}
        if self.procedure:
            values["procedure_id"] = self.procedure.id
        public = self.env.ref("base.public_user")
        return self.env["elite.vet.reservation"].with_user(public).sudo().create(values).with_env(self.env)

    def test_detail_says_who_booked_it(self):
        clinic = self.booked_by_reception(9, self.new_pet("Klinický T24"))
        web = self.booked_on_web(10, self.new_pet("Webový T24"))
        data = self.api(self.reception).board_reservation(clinic.id)
        self.assertEqual((data["source"], data["created_by"], data["created_by_initials"]),
                         ("internal", "Recepční Klinická", "RK"))
        self.assertTrue(data["created_at"])
        data = self.api(self.reception).board_reservation(web.id)
        self.assertEqual((data["source"], data["created_by"], data["created_by_initials"]), ("web", "", ""))

    def test_till_board_data_has_the_origin(self):
        clinic = self.booked_by_reception(9, self.new_pet("Klinický T24b"))
        web = self.booked_on_web(10, self.new_pet("Webový T24b"))
        events = {e["id"]: e for e in self.env["elite.vet.reservation"].with_user(self.reception)
                  .board_data(str(clinic_today()))["events"]}
        self.assertEqual(events[clinic.id]["created_by_initials"], "RK")
        self.assertEqual(events[clinic.id]["created_by"], "Recepční Klinická")
        self.assertEqual((events[web.id]["source"], events[web.id]["created_by"]), ("web", ""))

    def test_arriving_marks_web_bookings(self):
        clinic = self.booked_by_reception(9, self.new_pet("Klinický T24c"))
        web = self.booked_on_web(10, self.new_pet("Webový T24c"))
        rows = {r["reservation_id"]: r for r in self.api(self.reception).today_data()["arriving"]}
        self.assertFalse(rows[clinic.id]["from_web"])
        self.assertTrue(rows[web.id]["from_web"])

    def test_till_assets_have_filter_legend_and_badge(self):
        with file_open("elite_vet_reception/static/src/pos/board_dialog/board_dialog.xml") as f:
            board = f.read()
        with file_open("elite_vet_reception/static/src/pos/board_dialog/board_dialog.js") as f:
            js = f.read()
        with file_open("elite_vet_reception/static/src/pos/today_screen/today_screen.xml") as f:
            today = f.read()
        for text in ("o_ev_board_source_filter", "o_ev_board_legend", "o_ev_board_src_web", "o_ev_board_detail_source"):
            self.assertIn(text, board)
        self.assertIn("elite_vet_reception.board_source_filter", js)
        self.assertIn("o_ev_web_badge", today)
