"""Task 24: web vs clinic reservations visible on the board and in the lists."""
import re
from datetime import date, timedelta

import pytz
from lxml import etree

from odoo.tests import tagged
from odoo.tools import file_open
from odoo.tools.safe_eval import safe_eval

from .common import ReservationCase

WED = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestSourceVisible(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.reception = Users.create({
            "name": "Jana Nováková T24", "login": "t24_reception",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id,
                                  cls.env.ref("elite_vet_reservation.group_reservation_reception").id])]})
        cls.public = cls.env.ref("base.public_user")

    def setUp(self):
        super().setUp()
        self.hours(self.room1, 2, 8.0, 19.0)
        self.hours(self.room2, 2, 8.0, 19.0)
        self.R = self.env["elite.vet.reservation"]

    def clinic_res(self, h, **vals):
        base = {"kind": "reservation", "state": "confirmed", "source": "internal",
                "procedure_id": self.vacc.id, "room_id": self.room1.id, "contact_name": "Klient T24",
                "pet_name": "Rex", "start": self.dt(WED, h, 0)}
        base.update(vals)
        return self.R.with_user(self.reception).create(base).with_env(self.env)

    def web_res(self, h, **vals):
        """Created as the website does it: the public user under sudo (controllers/booking.py)."""
        base = {"kind": "reservation", "state": "confirmed", "source": "web",
                "procedure_id": self.vacc.id, "room_id": self.room1.id, "contact_name": "Web T24",
                "pet_name": "Bobík", "start": self.dt(WED, h, 0)}
        base.update(vals)
        return self.R.with_user(self.public).sudo().create(base).with_env(self.env)

    def event(self, rec, day="2026-10-14"):
        return next(e for e in self.R.board_data(day)["events"] if e["id"] == rec.id)

    # ---------------------------------------------------------------- data

    def test_board_clinic_reservation_has_creator(self):
        rec = self.clinic_res(9)
        ev = self.event(rec)
        self.assertEqual(ev["source"], "internal")
        self.assertEqual(ev["created_by"], "Jana Nováková T24")
        self.assertEqual(ev["created_by_initials"], "JT")
        local = pytz.utc.localize(rec.create_date).astimezone(pytz.timezone("Europe/Prague"))
        self.assertEqual(ev["created_at"], "%d. %d. %d %s" % (local.day, local.month, local.year,
                                                                local.strftime("%H:%M")))
        self.assertEqual(rec.created_by_id, self.reception)

    def test_board_web_reservation_has_no_creator(self):
        rec = self.web_res(10)
        self.assertEqual(rec.create_uid, self.public)
        ev = self.event(rec)
        self.assertEqual((ev["source"], ev["created_by"], ev["created_by_initials"]), ("web", "", ""))
        self.assertTrue(ev["created_at"])
        self.assertFalse(rec.created_by_id)

    def test_board_second_room_copy_shows_main(self):
        main = self.web_res(11)
        copy = main.add_second_room(self.room2)
        self.assertEqual(copy.source, "internal")
        ev = self.event(copy)
        self.assertEqual((ev["source"], ev["created_by"]), ("web", ""))
        clinic = self.clinic_res(13)
        copy2 = clinic.add_second_room(self.room2)
        self.assertEqual(self.event(copy2)["created_by"], "Jana Nováková T24")

    def test_board_blocks_keep_source_only(self):
        block = self.R.create({"kind": "block", "state": "confirmed", "room_id": self.room1.id,
                               "start": self.dt(WED, 15, 0), "stop": self.dt(WED, 16, 0), "block_reason": "T24"})
        ev = self.event(block)
        self.assertNotIn("created_by", ev)
        self.assertEqual(ev["source"], "internal")

    def test_source_label_is_klinika(self):
        self.assertEqual(dict(self.R._fields["source"].selection)["internal"], "Klinika")

    # ---------------------------------------------------------------- views

    def arch(self, xmlid):
        return etree.fromstring(self.env.ref(xmlid).arch)

    def test_lists_show_source_and_creator(self):
        for xmlid in ("elite_vet_reservation.view_reservation_list",
                      "elite_vet_reservation.view_reservation_history_list"):
            arch = self.arch(xmlid)
            for name in ("source", "created_by_id"):
                node = arch.find(".//field[@name='%s']" % name)
                self.assertIsNotNone(node, (xmlid, name))
                self.assertEqual(node.get("optional"), "show", (xmlid, name))

    def test_search_filters_exist_and_work(self):
        clinic, web = self.clinic_res(9), self.web_res(10)
        for xmlid in ("elite_vet_reservation.view_reservation_search",
                      "elite_vet_reservation.view_reservation_history_search"):
            arch = self.arch(xmlid)
            filters = {f.get("name"): f for f in arch.iter("filter")}
            for name in ("from_web", "from_clinic", "group_source"):
                self.assertIn(name, filters, (xmlid, name))
            self.assertIn("'group_by': 'source'", filters["group_source"].get("context"))
            # the two source filters are their own group (not OR-ed with another filter)
            prev = filters["from_web"].getprevious()
            self.assertEqual(prev.tag, "separator", xmlid)
            web_ids = self.R.search(safe_eval(filters["from_web"].get("domain"))).ids
            clinic_ids = self.R.search(safe_eval(filters["from_clinic"].get("domain"))).ids
            self.assertIn(web.id, web_ids)
            self.assertNotIn(clinic.id, web_ids)
            self.assertIn(clinic.id, clinic_ids)
            self.assertNotIn(web.id, clinic_ids)

    def test_board_assets_have_filter_and_legend(self):
        with file_open("elite_vet_reservation/static/src/board/board.xml") as f:
            xml = f.read()
        with file_open("elite_vet_reservation/static/src/board/board.js") as f:
            js = f.read()
        for text in ("evb-source-filter", "evb-legend", "WEB", "WinVet", "Klinika"):
            self.assertIn(text, xml)
        self.assertIn("localStorage.setItem(SOURCE_FILTER_KEY", js)
        self.assertEqual(re.findall(r'key: "(\w+)", label: "([^"]+)"', js),
                         [("all", "Vše"), ("web", "Web"), ("clinic", "Klinika")])

    # ---------------------------------------------------------------- chat widget

    def test_chat_widget_books_through_the_web_api(self):
        """The chat widget sends its booking to the website form's /rezervace/api/submit, which
        creates the request with source = web (asserted in test_controllers / below)."""
        with file_open("elite_vet_reservation/static/src/chat/chat_core.js") as f:
            core = f.read()
        self.assertEqual(re.findall(r"rpc\('(/rezervace/api/submit)'", core), ["/rezervace/api/submit"])
        with file_open("elite_vet_reservation/controllers/booking.py") as f:
            controller = f.read()
        self.assertIn('"kind": "reservation", "state": "web_new", "source": "web"', controller)
