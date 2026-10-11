"""UX tabule a administrace: české názvy, návrhy v panelu Čekající,
popisky událostí, kopírování rozpisu, souhrn ordinační doby, „Kdo dělá“."""
from datetime import date, timedelta

from odoo.tests import tagged

from odoo.addons.elite_vet_reservation.models.reservation import inicialy
from odoo.addons.elite_vet_reservation.models.room import format_hours_summary

from .common import ReservationCase

WED = date(2026, 10, 14)


@tagged("post_install", "-at_install")
class TestBoardSuggestions(ReservationCase):
    """board_suggestions: kam jde čekající žádost potvrdit v požadovaném čase."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icon = cls.env["elite.vet.team.icon"].search([], limit=1)
        section = cls.env["elite.vet.team.section"].create({"name": "Lékařky UX test"})
        Spec = cls.env["elite.vet.team.specialization"]
        cls.stomatologie = Spec.create({"name": "UX stomatologie", "icon_id": icon.id})
        cls.ocni = Spec.create({"name": "UX oftalmologie", "icon_id": icon.id})
        Member = cls.env["elite.vet.team.member"]
        cls.dr_a.member_id = Member.create({"name": cls.dr_a.name, "section_id": section.id,
                                            "specialization_ids": [(6, 0, cls.stomatologie.ids)]})
        cls.dr_b.member_id = Member.create({"name": cls.dr_b.name, "section_id": section.id,
                                            "specialization_ids": [(6, 0, cls.ocni.ids)]})
        cls.zuby = cls.env["elite.vet.procedure"].create({
            "name": "Dental examination UX", "duration": 30,
            "specialization_ids": [(6, 0, cls.stomatologie.ids)]})
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 18.0)
            cls.hours(cls, cls.room2, wd, 8.0, 18.0)
        # Nastavení v DB mohl kdokoli změnit; testy počítají s výchozím chováním.
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60,
            "booking_min_hours_before": 24, "booking_slot_step": 15})
        # Budoucí den uvnitř horizontu webu (výchozí 60 dní), ať platí kdykoli se testy pustí.
        cls.day = date.today() + timedelta(days=10)
        cls.R = cls.env["elite.vet.reservation"]

    def waiting(self, procedure=None, doctor=None, h=9, m=0):
        vals = {"start": self.dt(self.day, h, m), "state": "web_new", "source": "web", "room_id": False,
                "procedure_id": (procedure or self.vacc).id}
        if doctor:
            vals["doctor_id"] = doctor.id
        return self.reservation(**vals)

    def pairs(self, w):
        return [(s["room_id"], s["doctor_id"]) for s in self.R.board_suggestions(w.id)]

    def test_free_time_suggests_every_room_with_doctor_on_duty(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        w = self.waiting()
        sug = self.R.board_suggestions(w.id)
        self.assertEqual([(s["room_id"], s["doctor_id"]) for s in sug],
                         [(self.room1.id, self.dr_a.id), (self.room2.id, self.dr_b.id)])
        self.assertEqual(sug[0]["room"], "Ordinace 1")
        self.assertEqual(sug[0]["doctor"], "MVDr. Alena Testová")

    def test_busy_room_is_not_suggested(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room1.id)
        self.assertEqual(self.pairs(self.waiting()), [(self.room2.id, self.dr_b.id)])

    def test_specialised_procedure_only_with_qualified_doctor(self):
        self.assign(self.dr_b, self.room1, self.day, 8.0, 12.0)   # oční, zuby nedělá
        self.assign(self.dr_a, self.room2, self.day, 8.0, 12.0)   # stomatoložka
        self.assertEqual(self.pairs(self.waiting(self.zuby)), [(self.room2.id, self.dr_a.id)])

    def test_requested_doctor_is_respected(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        self.assertEqual(self.pairs(self.waiting(doctor=self.dr_b)), [(self.room2.id, self.dr_b.id)])

    def test_room_without_duty_offered_without_doctor_when_not_required(self):
        # Obecný úkon a bez povinného lékaře: ordinace bez služby se nabídne, jen bez lékařky.
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assertEqual(self.pairs(self.waiting()), [(self.room1.id, self.dr_a.id), (self.room2.id, False)])

    def test_nothing_free_returns_empty_and_board_shows_it(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 12.0)
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room1.id)
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room2.id)
        w = self.waiting()
        self.assertEqual(self.R.board_suggestions(w.id), [])
        row = next(x for x in self.R.board_data(self.day.isoformat())["waiting"] if x["id"] == w.id)
        self.assertEqual(row["suggestions"], [])

    def test_confirm_from_suggestion_sets_room_and_doctor(self):
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        w = self.waiting()
        row = next(x for x in self.R.board_data(self.day.isoformat())["waiting"] if x["id"] == w.id)
        self.assertEqual(row["minute"], 540)
        dny = ["po", "út", "st", "čt", "pá", "so", "ne"]
        self.assertEqual(row["date_label"], "%s %d. %d. 09:00" % (dny[self.day.weekday()], self.day.day, self.day.month))
        self.R.board_confirm(w.id, row["date"], row["minute"], self.room2.id, self.dr_b.id)
        self.assertEqual((w.state, w.room_id, w.doctor_id, w.start),
                         ("confirmed", self.room2, self.dr_b, self.dt(self.day, 9, 0)))

    def test_confirmed_reservation_has_no_suggestions(self):
        self.assertEqual(self.R.board_suggestions(self.reservation(start=self.dt(self.day, 9, 0)).id), [])


@tagged("post_install", "-at_install")
class TestBoardEvents(ReservationCase):
    """Popisky událostí na tabuli a čeština v názvech."""

    def test_event_labels(self):
        self.hours(self.room1, 2, 8.0, 18.0)
        r = self.reservation(start=self.dt(WED, 9, 0), doctor_id=self.dr_a.id)
        ev = next(e for e in self.env["elite.vet.reservation"].board_data("2026-10-14")["events"] if e["id"] == r.id)
        self.assertEqual(ev["time_label"], "9:00–9:15")
        self.assertEqual((ev["pet"], ev["owner"]), ("Rex", "Test Klient"))
        self.assertEqual(ev["doctor_initials"], "AT")

    def test_initials(self):
        self.assertEqual(inicialy("MVDr. Dana Pokorná"), "DP")
        self.assertEqual(inicialy("MVDr. Ioana Chihaia, Ph.D."), "IC")
        self.assertEqual(inicialy("Eva"), "E")
        self.assertEqual(inicialy(False), "")

    def test_name_in_clinic_language(self):
        if "cs_CZ" not in dict(self.env["res.lang"].get_installed()):
            self.skipTest("cs_CZ není nainstalovaná")
        self.vacc.update_field_translations("name", {"cs_CZ": "Vakcinace UX"})
        for lang in ("en_US", "de_DE"):
            vals = {"kind": "reservation", "state": "confirmed", "procedure_id": self.vacc.id,
                    "room_id": self.room1.id, "contact_name": "Jana Nováková", "pet_name": "Rex",
                    "start": self.dt(WED, 10 if lang == "en_US" else 11, 0)}
            r = self.env["elite.vet.reservation"].with_context(lang=lang).create(vals)
            self.assertEqual(r.name, "Jana Nováková / Rex / Vakcinace UX")
            ev = next(e for e in self.env["elite.vet.reservation"].with_context(lang=lang)
                      .board_data("2026-10-14")["events"] if e["id"] == r.id)
            self.assertEqual(ev["procedure"], "Vakcinace UX")


@tagged("post_install", "-at_install")
class TestAdminUx(ReservationCase):
    """Rozpis lékařů, ordinace a úkony v administraci."""

    def test_copy_week_skips_overlaps(self):
        A = self.env["elite.vet.doctor.assignment"]
        a1 = self.assign(self.dr_a, self.room1, WED, 8.0, 12.0)
        a2 = self.assign(self.dr_b, self.room2, WED, 13.0, 18.0)
        # Lékařka B už má za týden službu, která by se s kopií překrývala.
        self.assign(self.dr_b, self.room1, WED + timedelta(days=7), 16.0, 19.0)
        res = (a1 | a2).action_kopirovat_tyden()
        self.assertEqual(res["tag"], "display_notification")
        self.assertIn("Zkopírováno 1, přeskočeno 1", res["params"]["message"])
        copy = A.search([("doctor_id", "=", self.dr_a.id), ("date", "=", WED + timedelta(days=7))])
        self.assertEqual((copy.room_id, copy.hour_from, copy.hour_to), (self.room1, 8.0, 12.0))
        self.assertEqual(A.search_count([("doctor_id", "=", self.dr_b.id), ("date", "=", WED + timedelta(days=7))]), 1)

    def test_hours_summary_format(self):
        lines = [(wd, 8.25, 19.5) for wd in range(5)] + [(6, 10.25, 17.75)]
        self.assertEqual(format_hours_summary(lines), "Po–Pá 8:15–19:30 · Ne 10:15–17:45")
        self.assertEqual(format_hours_summary([(0, 8, 12), (0, 13, 18), (2, 8, 12)]),
                         "Po 8:00–12:00, 13:00–18:00 · St 8:00–12:00")
        self.assertEqual(format_hours_summary([]), "")

    def test_room_hours_summary_field(self):
        for wd in range(5):
            self.hours(self.room1, wd, 8.25, 19.5)
        self.hours(self.room1, 5, 9.0, 12.0)
        # Řádek, jehož platnost skončila, se do souhrnu nepočítá.
        self.hours(self.room1, 6, 9.0, 12.0, date_to=date.today() - timedelta(days=1))
        self.assertEqual(self.room1.hours_summary, "Po–Pá 8:15–19:30 · So 9:00–12:00")

    def test_procedure_who_does_it(self):
        self.assertEqual(self.vacc.kdo_dela, "kterákoli lékařka")
        icon = self.env["elite.vet.team.icon"].search([], limit=1)
        section = self.env["elite.vet.team.section"].create({"name": "Sekce UX"})
        spec = self.env["elite.vet.team.specialization"].create({"name": "UX dermatologie", "icon_id": icon.id})
        self.dr_b.member_id = self.env["elite.vet.team.member"].create(
            {"name": self.dr_b.name, "section_id": section.id, "specialization_ids": [(6, 0, spec.ids)]})
        self.derm.specialization_ids = spec
        self.assertEqual(self.derm.kdo_dela, "MVDr. Bára Testová")
