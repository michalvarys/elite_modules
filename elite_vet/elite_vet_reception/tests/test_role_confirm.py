"""Task 25 item 1: Recepce, Sestra and Lékařka (linked to a team member or not) confirm, reject and
move web requests and reservations; shifts and doctor assignments stay with the roster managers."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase

DOCTOR = "elite_vet_clinic.group_clinic_doctor"


@tagged("post_install", "-at_install")
class TestRoleConfirm(ReceptionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15,
            "booking_block_weekends": False, "booking_block_holidays": False})
        cls.day = clinic_today() + timedelta(days=3)
        cls.room_b = cls.env["elite.vet.room"].create({"name": "Ordinace T31 B"})
        cls.doctor.accepts_bookings = True
        cls.proc = cls.env["elite.vet.procedure"].create({
            "name": "T31 potvrzení", "duration": 20, "symbol": "P", "color": "green",
            "room_ids": [(6, 0, [cls.room.id, cls.room_b.id])]})
        cls.assignment = cls.env["elite.vet.doctor.assignment"].create({
            "doctor_id": cls.doctor.id, "room_id": cls.room.id, "date": cls.day,
            "hour_from": 8.0, "hour_to": 18.0})
        cls.second_doctor = cls.env["elite.vet.doctor"].create({
            "name": "MVDr. T31 Propojená", "accepts_bookings": True})
        cls.env["elite.vet.doctor.assignment"].create({
            "doctor_id": cls.second_doctor.id, "room_id": cls.room_b.id, "date": cls.day,
            "hour_from": 8.0, "hour_to": 18.0})
        cls.linked_doctor = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "MVDr. T31 Propojená", "login": "t31_linked_doctor_test",
            "email": "t31_linked_doctor_test@example.invalid",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref(DOCTOR).id])]})
        cls.second_doctor.user_id = cls.linked_doctor
        for room in (cls.room, cls.room_b):
            cls.env["elite.vet.room.hours"].create({"room_id": room.id, "weekday": str(cls.day.weekday()),
                                                    "hour_from": 7.0, "hour_to": 19.0})
        cls.roles = {"recepce": cls.reception, "sestra": cls.nurse, "lekarka": cls.doctor_user,
                     "lekarka_propojena": cls.linked_doctor}

    def local_utc(self, hour, minute=0):
        return fields.Datetime.to_datetime(
            self.env["elite.vet.reservation"].board_slot_utc(self.day.isoformat(), hour * 60 + minute))

    def web_request(self, hour, minute=0, **vals):
        start = self.env["elite.vet.reservation"].board_slot_utc(self.day.isoformat(), hour * 60 + minute)
        values = {"kind": "reservation", "state": "web_new", "source": "web", "room_id": False,
                  "procedure_id": self.proc.id, "start": start, "doctor_id": False,
                  "contact_name": "Klient T31", "contact_email": "klient.t31@example.invalid",
                  "contact_phone": "+420 777 031 031", "pet_name": "Rex T31", "pet_species": "dog"}
        values.update(vals)
        return self.env["elite.vet.reservation"].with_context(ev_no_mail=True).create(values)

    def confirmed(self, hour, minute=0):
        start = self.local_utc(hour, minute)
        return self.env["elite.vet.reservation"].with_context(ev_no_mail=True).create({
            "kind": "reservation", "state": "confirmed", "room_id": self.room.id, "procedure_id": self.proc.id,
            "doctor_id": self.doctor.id, "start": start, "stop": start + timedelta(minutes=20),
            "contact_name": "Klient T31", "contact_email": "klient.t31@example.invalid"})

    # ------------------------------------------------------------------ web requests

    def test_every_role_confirms_on_the_board(self):
        for hour, (role, user) in zip((8, 9, 10, 11), self.roles.items()):
            with self.subTest(role=role):
                req = self.web_request(hour)
                Res = self.env["elite.vet.reservation"].with_user(user)
                Res.board_confirm(req.id, self.day.isoformat(), hour * 60, self.room.id)
                self.assertEqual(req.state, "confirmed")
                self.assertEqual(req.room_id, self.room)
                self.assertEqual(req.doctor_id, self.doctor)
                self.assertTrue(req.partner_id and req.pet_id)
                # the confirmation e-mail is queued (sudo), not lost to the doctor's rights
                self.assertTrue(self.env["mail.mail"].search_count([
                    ("model", "=", "elite.vet.reservation"), ("res_id", "=", req.id)]))

    def test_every_role_confirms_a_suggestion_with_a_doctor(self):
        for hour, (role, user) in zip((12, 13, 14, 15), self.roles.items()):
            with self.subTest(role=role):
                req = self.web_request(hour)
                suggestions = self.env["elite.vet.reservation"].with_user(user).board_suggestions(req.id)
                target = next(s for s in suggestions if s["room_id"] == self.room_b.id)
                self.env["elite.vet.reservation"].with_user(user).board_confirm(
                    req.id, self.day.isoformat(), hour * 60, target["room_id"], target["doctor_id"])
                self.assertEqual((req.state, req.room_id, req.doctor_id),
                                 ("confirmed", self.room_b, self.second_doctor))

    def test_every_role_confirms_from_the_form(self):
        for hour, (role, user) in zip((8, 9, 10, 11), self.roles.items()):
            with self.subTest(role=role):
                req = self.web_request(hour, 30).with_user(user)
                req.write({"room_id": self.room_b.id, "doctor_id": self.second_doctor.id})
                req.action_confirm()
                self.assertEqual(req.state, "confirmed")

    def test_every_role_confirms_a_request_with_a_staff_e_mail(self):
        """The cause of the report: a request with the e-mail of an Odoo user (a staff member booking
        her own pet) matches that user's partner; flagging it as a client was refused to everyone but
        the access-rights admin."""
        staff = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Sestra T31 Vlastní", "login": "t31_staff_own_pet", "email": "t31.staff.own@example.invalid",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        self.assertFalse(staff.partner_id.is_vet_client)
        for hour, (role, user) in zip((8, 9, 10, 11), self.roles.items()):
            with self.subTest(role=role):
                req = self.web_request(hour, 45, contact_email="t31.staff.own@example.invalid")
                self.env["elite.vet.reservation"].with_user(user).board_confirm(
                    req.id, self.day.isoformat(), hour * 60 + 45, self.room.id)
                self.assertEqual(req.state, "confirmed")
                self.assertEqual(req.partner_id, staff.partner_id)
                self.assertTrue(staff.partner_id.is_vet_client)
                self.assertEqual(req.pet_id.partner_id, staff.partner_id)
                staff.partner_id.sudo().is_vet_client = False

    def test_every_role_rejects(self):
        for hour, (role, user) in zip((16, 16, 17, 17), self.roles.items()):
            with self.subTest(role=role):
                req = self.web_request(hour, 0 if role in ("recepce", "lekarka") else 30)
                req.with_user(user).action_cancel("clinic")
                self.assertEqual(req.state, "cancelled")
                self.assertEqual(req.cancelled_by_id, user)

    # ------------------------------------------------------------------ reservations

    def test_every_role_moves_on_the_board_and_in_the_till(self):
        for hour, (role, user) in zip((8, 10, 12, 14), self.roles.items()):
            with self.subTest(role=role):
                res = self.confirmed(hour)
                Res = self.env["elite.vet.reservation"].with_user(user)
                Res.board_move(res.id, self.day.isoformat(), hour * 60 + 30, self.room.id)
                self.assertEqual(res.start, self.local_utc(hour, 30))
                self.api(user).move_reservation(res.id, self.day.isoformat(), hour * 60 + 60, self.room_b.id)
                self.assertEqual((res.start, res.room_id), (self.local_utc(hour + 1), self.room_b))
                self.assertEqual(res.doctor_id, self.second_doctor)

    def test_till_move_with_and_without_e_mail(self):
        """Task 25: the till's move dialog may change the date and keep the client uninformed."""
        Mail = self.env["mail.mail"]
        res = self.confirmed(9)
        api = self.api(self.reception)
        api.move_reservation(res.id, self.day.isoformat(), 9 * 60 + 30, self.room.id, False)
        self.assertEqual(res.start, self.local_utc(9, 30))
        self.assertFalse(Mail.search_count([("model", "=", "elite.vet.reservation"), ("res_id", "=", res.id)]))
        self.assertTrue(res.message_ids.filtered(lambda m: "Klient nebyl o změně informován." in (m.body or "")))
        api.move_reservation(res.id, self.day.isoformat(), 10 * 60, self.room.id, True)
        self.assertEqual(Mail.search_count([("model", "=", "elite.vet.reservation"), ("res_id", "=", res.id),
                                            ("state", "=", "outgoing")]), 1)

    def test_silent_change_by_a_user_without_e_mail(self):
        """The chatter note of a silent move / confirmation does not need the user's e-mail (a member
        account may have none); found in the ev_test check."""
        no_mail = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "MVDr. T31 Bez e-mailu", "login": "t31_doctor_no_email",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref(DOCTOR).id])]})
        self.assertFalse(no_mail.email)
        Res = self.env["elite.vet.reservation"].with_user(no_mail)
        res = self.confirmed(9)
        Res.board_move(res.id, self.day.isoformat(), 9 * 60 + 30, self.room.id, False)
        self.assertEqual(res.start, self.local_utc(9, 30))
        req = self.web_request(12)
        Res.board_confirm(req.id, self.day.isoformat(), 12 * 60, self.room.id, None, False)
        self.assertEqual(req.state, "confirmed")
        for rec, text in ((res, "Klient nebyl o změně informován."), (req, "Klient nebyl o potvrzení informován.")):
            self.assertTrue(rec.message_ids.filtered(lambda m: text in (m.body or "")))

    def test_every_role_cancels_in_the_till(self):
        for hour, (role, user) in zip((9, 11, 13, 15), self.roles.items()):
            with self.subTest(role=role):
                res = self.confirmed(hour, 40)
                self.api(user).cancel_reservation(res.id)
                self.assertEqual(res.state, "cancelled")

    # ------------------------------------------------------------------ shifts stay with the managers

    def test_doctors_and_nurses_cannot_edit_shifts(self):
        shift_type = self.env["elite.vet.shift.type"].search([], limit=1) or \
            self.env["elite.vet.shift.type"].create({"name": "T31 směna"})
        for role in ("recepce", "sestra", "lekarka", "lekarka_propojena"):
            user = self.roles[role]
            with self.subTest(role=role):
                data = self.env["elite.vet.reservation"].with_user(user).board_data(self.day.isoformat())
                self.assertFalse(data["can_edit_shifts"])
                Assignment = self.env["elite.vet.doctor.assignment"].with_user(user)
                with self.assertRaises(AccessError):
                    Assignment.create({"doctor_id": self.doctor.id, "room_id": self.room_b.id,
                                       "date": self.day + timedelta(days=1),
                                       "hour_from": 8.0, "hour_to": 9.0})
                with self.assertRaises(AccessError):
                    self.assignment.with_user(user).write({"hour_to": 17.0})
                with self.assertRaises(AccessError):
                    self.assignment.with_user(user).unlink()
                with self.assertRaises(AccessError):
                    self.env["elite.vet.shift"].with_user(user).create({
                        "doctor_id": self.doctor.id, "type_id": shift_type.id,
                        "date": self.day + timedelta(days=1)})
        self.assertEqual(self.assignment.hour_to, 18.0)
        self.assertTrue(self.env["elite.vet.reservation"].with_user(self.manager)
                        .board_data(self.day.isoformat())["can_edit_shifts"])
