from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tools import mute_logger

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase

RECEPTION = "elite_vet_reservation.group_reservation_reception"
NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"
MANAGER = "elite_vet_reservation.group_reservation_manager"
TILL = "elite_vet_sale.group_till_stock"
RECEPTION_MODEL = "odoo.addons.elite_vet_reception.models.room_board.ReceptionRooms"


@tagged("post_install", "-at_install")
class TestMemberAccounts(ReceptionCase):
    """Task 23: an account per team member, linked to the roster doctor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("cs_CZ")
        Room = cls.env["elite.vet.room"]
        cls.room1 = Room.create({"name": "Ordinace T23 jedna", "sequence": 910})
        cls.room2 = Room.create({"name": "Ordinace T23 dvě", "sequence": 911})
        section = cls.env["elite.vet.team.section"].create({"name": "Sekce T23"})
        Member = cls.env["elite.vet.team.member"]
        Doctor = cls.env["elite.vet.doctor"]
        cls.member_a = Member.create({"name": "MVDr. Anna Účtová-T23", "section_id": section.id,
                                      "email": "anna.t23@example.invalid"})
        cls.member_n = Member.create({"name": "Nela Sesterská-T23", "section_id": section.id,
                                      "email": "nela.t23@example.invalid"})
        cls.doc_a = Doctor.create({"name": "MVDr. Anna Účtová-T23", "member_id": cls.member_a.id,
                                   "accepts_bookings": True})
        cls.doc_b = Doctor.create({"name": "MVDr. Bára Rozpisová-T23", "accepts_bookings": True})
        cls.nurse_n = Doctor.create({"name": "Nela Sesterská-T23", "member_id": cls.member_n.id})
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, name, *groups, **vals):
            return Users.create(dict({
                "name": name, "login": login, "email": "%s@example.invalid" % login,
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id] + [cls.env.ref(g).id for g in groups])]},
                **vals))

        # the linked doctor's account has another name than the roster (no name match)
        cls.user_a = user("t23_anna", "Anna T23 přihlášení", DOCTOR)
        cls.doc_a.user_id = cls.user_a
        cls.room_user = user("t23_room", "Ordinace T23 účet", DOCTOR, elite_vet_room_id=cls.room1.id)
        cls.room_action = cls.env.ref("elite_vet_reception.action_room_board")
        cls.card_action = cls.env.ref("elite_vet_clinic.action_patient_card")

    def duty(self, room, doctor, hour_from=0.0, hour_to=24.0):
        return self.env["elite.vet.doctor.assignment"].create({
            "doctor_id": doctor.id, "room_id": room.id, "date": clinic_today(),
            "hour_from": hour_from, "hour_to": hour_to})

    def walk_in(self, name, **kw):
        data = self.api(self.reception).walk_in(self.new_pet(name).id, **kw)
        return self.Record.browse(data["record_id"])

    def wizard(self, user=None):
        return self.env["elite.vet.account.wizard"].with_user(user or self.manager)

    def line(self, wizard, doctor):
        return wizard.line_ids.filtered(lambda l: l.doctor_id == doctor)

    # ---------------------------------------------------------------- link
    def test_link_is_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.doc_b.user_id = self.user_a
            self.doc_b.flush_recordset()

    def test_link_internal_users_only(self):
        portal = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Portál T23", "login": "t23_portal",
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])]})
        with self.assertRaises(ValidationError):
            self.doc_b.user_id = portal

    def test_reverse_on_the_user(self):
        self.assertEqual(self.user_a.elite_vet_doctor_id, self.doc_a)
        self.assertFalse(self.reception.elite_vet_doctor_id)
        self.doc_a.user_id = False
        self.assertFalse(self.user_a.elite_vet_doctor_id)

    # ---------------------------------------------------------------- _doctor_for_user
    def test_doctor_for_user_link_first(self):
        Records = self.Record
        self.assertEqual(Records._doctor_for_user(self.user_a), self.doc_a, "by the link, not the name")
        # an unlinked user still matches by name (existing behaviour)
        self.assertEqual(Records._doctor_for_user(self.doctor_user), self.doctor)

    def test_name_fallback_not_for_a_doctor_linked_to_another(self):
        namesake = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "MVDr. Anna Účtová-T23", "login": "t23_namesake",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref(DOCTOR).id])]})
        self.assertFalse(self.Record._doctor_for_user(namesake), "the doctor of that name belongs to user_a")
        self.doc_a.user_id = False
        self.assertEqual(self.Record._doctor_for_user(namesake), self.doc_a)

    def test_my_patients_today_uses_the_link(self):
        pet = self.new_pet("Můj T23")
        self.reservation(10, 0, pet=pet, doctor=self.doc_a)
        self.reservation(11, 0, pet=self.new_pet("Cizí T23"), doctor=self.doc_b)
        data = self.as_user(self.user_a).my_patients_today()
        self.assertEqual(data["doctor"], {"id": self.doc_a.id, "name": self.doc_a.name})
        self.assertEqual([i["pet_id"] for i in data["items"]], [pet.id])

    # ---------------------------------------------------------------- wizard
    def test_wizard_lines(self):
        wizard = self.wizard().create({})
        self.assertNotIn(self.doc_a, wizard.line_ids.doctor_id, "already has an account")
        a_line = self.line(wizard, self.nurse_n)
        self.assertEqual((a_line.login, a_line.role, a_line.create_account),
                         ("nela.t23@example.invalid", "nurse", True))
        b_line = self.line(wizard, self.doc_b)
        self.assertEqual((b_line.login, b_line.role, b_line.create_account), (False, "doctor", False))

    def test_wizard_only_for_managers(self):
        for user in (self.reception, self.nurse, self.doctor_user):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.wizard(user).create({})
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.wizard(user).action_open()
        self.assertEqual(self.wizard().action_open()["res_model"], "elite.vet.account.wizard")

    def _only(self, wizard, *doctors):
        """Untick every line except the given doctors (ev data of other members stays untouched)."""
        for line in wizard.line_ids:
            line.create_account = line.doctor_id in doctors

    def test_wizard_creates_linked_accounts_with_roles(self):
        mails_before = self.env["mail.mail"].search_count([])
        wizard = self.wizard().create({})
        self._only(wizard, self.nurse_n, self.doc_b)
        self.line(wizard, self.doc_b).write({"login": "bara.t23@example.invalid"})
        result = wizard.action_create()
        self.assertIn("Vytvořeno účtů: 2.", result["params"]["message"])
        nela, bara = self.nurse_n.user_id, self.doc_b.user_id
        self.assertEqual((nela.login, nela.email), ("nela.t23@example.invalid", "nela.t23@example.invalid"))
        self.assertEqual(bara.name, self.doc_b.name)
        for user in (nela, bara):
            self.assertFalse(user.share)
            self.assertEqual((user.lang, user.tz), ("cs_CZ", "Europe/Prague"))
            self.env.cr.execute("SELECT password FROM res_users WHERE id = %s", [user.id])
            self.assertFalse(self.env.cr.fetchone()[0], "no password")
            # role automation: no till for nurse / doctor, home = screen Ordinace (linked)
            self.assertFalse(user.has_group(TILL))
            self.assertEqual(user.action_id.id, self.room_action.id)
        self.assertTrue(bara.has_group(DOCTOR))
        self.assertTrue(nela.has_group(NURSE) and not nela.has_group(DOCTOR))
        self.assertEqual(self.env["mail.mail"].search_count([]), mails_before, "no invitation by default")

    def test_wizard_reception_role_gets_till(self):
        wizard = self.wizard().create({})
        self._only(wizard, self.nurse_n)
        self.line(wizard, self.nurse_n).role = "reception"
        wizard.action_create()
        user = self.nurse_n.user_id
        self.assertTrue(user.has_group(TILL))
        self.assertFalse(user.has_group(NURSE))
        self.assertEqual(user.action_id.id, self.env.ref("elite_vet_reception.action_open_reception_pos").id)

    def test_wizard_logins(self):
        wizard = self.wizard().create({})
        self._only(wizard, self.doc_b)
        with self.assertRaisesRegex(UserError, "Bára Rozpisová-T23"):
            wizard.action_create()   # ticked without a login
        self._only(wizard, self.doc_b, self.nurse_n)
        self.line(wizard, self.doc_b).login = "NELA.t23@example.invalid"
        with self.assertRaisesRegex(UserError, "stejné přihlašovací jméno"):
            wizard.action_create()
        self.line(wizard, self.doc_b).login = "t23_anna"
        with self.assertRaisesRegex(UserError, "už má účet „Anna T23 přihlášení“"):
            wizard.action_create()
        self.assertFalse(self.doc_b.user_id | self.nurse_n.user_id, "nothing created on an error")

    def test_wizard_skipped_counts(self):
        wizard = self.wizard().create({})
        self._only(wizard, self.nurse_n)
        unticked = len(wizard.line_ids) - 1
        message = wizard.action_create()["params"]["message"]
        self.assertIn("Vytvořeno účtů: 1.", message)
        self.assertIn("Přeskočeno: %d (nezaškrtnuto %d)" % (unticked, unticked), message)

    def test_wizard_invitation_is_queued_not_sent(self):
        wizard = self.wizard().create({"send_invitation": True})
        self._only(wizard, self.nurse_n)
        with patch("odoo.addons.base.models.ir_mail_server.IrMailServer.send_email") as send:
            wizard.action_create()
        send.assert_not_called()
        user = self.nurse_n.user_id
        mail = self.env["mail.mail"].search([("email_to", "=", user.email)])
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.state, "outgoing")
        self.assertIn(user.partner_id.signup_type, ("signup",))

    def test_wizard_invitation_needs_an_email(self):
        wizard = self.wizard().create({"send_invitation": True})
        self._only(wizard, self.doc_b)
        self.line(wizard, self.doc_b).login = "bara_t23"
        with self.assertRaisesRegex(UserError, "jen na e-mail"):
            wizard.action_create()

    def test_wizard_form(self):
        with Form(self.wizard(), view="elite_vet_reception.view_account_wizard_form") as form:
            self.assertTrue(len(form.line_ids))

    # ---------------------------------------------------------------- home and room preselection
    def test_home_of_linked_accounts(self):
        self.assertEqual(self.user_a.action_id.id, self.room_action.id)
        self.doc_a.user_id = False
        self.assertEqual(self.user_a.action_id.id, self.card_action.id)
        self.doc_a.user_id = self.user_a
        self.assertEqual(self.user_a.action_id.id, self.room_action.id)
        # a linked reception account keeps the till home, Vedení its own
        self.doc_b.user_id = self.reception
        self.assertEqual(self.reception.action_id.id,
                         self.env.ref("elite_vet_reception.action_open_reception_pos").id)
        self.doc_b.user_id = self.manager
        self.assertEqual(self.manager.action_id.id, self.env.ref("elite_vet_winvet.action_winvet_dashboard").id)
        # the room account keeps its behaviour
        self.assertEqual(self.room_user.action_id.id, self.room_action.id)

    def test_room_preselection_by_roster(self):
        self.duty(self.room1, self.doc_a, 8.0, 12.0)
        self.duty(self.room2, self.doc_a, 13.0, 17.0)
        api = self.api(self.user_a)
        for hour, room in ((9.0, self.room1), (12.5, self.room2), (14.0, self.room2), (18.0, None)):
            with self.subTest(hour=hour), patch("%s._clinic_hour_now" % RECEPTION_MODEL, return_value=hour):
                perms = api.room_board()["perms"]
                self.assertTrue(perms["member_account"])
                self.assertEqual(perms["roster_room_id"], room.id if room else None)
                self.assertIsNone(perms["user_room_id"])
        perms = self.api(self.room_user).room_board()["perms"]
        self.assertEqual((perms["member_account"], perms["user_room_id"]), (False, self.room1.id))
        self.assertFalse(self.api(self.nurse).room_board()["perms"]["member_account"])

    # ---------------------------------------------------------------- who took the patient
    def test_assign_by_linked_doctor_takes_it(self):
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Převzatý T23")
        self.api(self.user_a).assign_room(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_a, "her, not the roster doctor")
        self.assertFalse(record.doctor_from_roster)

    def test_roster_doctor_replaced_by_linked_doctor(self):
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Z rozpisu T23")
        self.api(self.reception).assign_room(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_b)
        self.assertTrue(record.doctor_from_roster)
        result = self.api(self.user_a).call_patient(record.id, self.room1.id)
        self.assertEqual((record.doctor_id, record.visit_stage, result["needs_doctor"]),
                         (self.doc_a, "in_room", []))

    def test_explicit_doctor_kept(self):
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Vybraná T23", doctor_id=self.doc_b.id)
        self.assertFalse(record.doctor_from_roster)
        self.api(self.user_a).call_patient(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_b)
        # roster doctor changed by hand -> explicit
        record2 = self.walk_in("Ručně T23")
        self.api(self.reception).assign_room(record2.id, self.room1.id)
        record2.doctor_id = self.doctor
        self.assertFalse(record2.doctor_from_roster)
        self.api(self.user_a).assign_room(record2.id, self.room2.id)
        self.assertEqual(record2.doctor_id, self.doctor)

    def test_two_on_duty_linked_doctor_not_asked(self):
        self.duty(self.room1, self.doc_a)
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Dvě T23")
        result = self.api(self.user_a).assign_room(record.id, self.room1.id)
        self.assertEqual((record.doctor_id, result["needs_doctor"]), (self.doc_a, []))

    def test_room_account_and_unlinked_keep_the_roster(self):
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Účet ordinace T23")
        self.api(self.room_user).call_patient(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_b)
        self.assertTrue(record.doctor_from_roster)
        record2 = self.walk_in("Nepropojená T23")
        self.api(self.doctor_user).assign_room(record2.id, self.room1.id)
        self.assertEqual(record2.doctor_id, self.doc_b)

    def test_linked_nurse_does_not_take_it(self):
        nurse = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Nela T23 účet", "login": "t23_nela",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref(NURSE).id])]})
        self.nurse_n.user_id = nurse
        self.assertEqual(nurse.action_id.id, self.room_action.id, "home of a linked nurse")
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Sestra volá T23")
        self.api(nurse).call_patient(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_b)

    def test_unassign_does_not_take_it(self):
        record = self.walk_in("Zpět T23")
        self.api(self.user_a).assign_room(record.id, False)
        self.assertFalse(record.doctor_id)

    def test_call_without_room_by_linked_doctor(self):
        record = self.walk_in("Bez ordinace T23")
        self.api(self.user_a).call_patient(record.id)
        self.assertEqual(record.doctor_id, self.doc_a)
