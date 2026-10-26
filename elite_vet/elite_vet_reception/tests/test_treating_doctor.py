from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase

NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"


@tagged("post_install", "-at_install")
class TestTreatingDoctor(ReceptionCase):
    """Task 23 addition: a logged-in linked doctor who changes a visit record becomes its doctor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Doctor = cls.env["elite.vet.doctor"]
        cls.doc_a = Doctor.create({"name": "MVDr. Alžběta Ošetřující-T23", "accepts_bookings": True})
        cls.doc_b = Doctor.create({"name": "MVDr. Blanka Druhá-T23", "accepts_bookings": True})
        cls.doc_c = Doctor.create({"name": "MVDr. Cecílie Ruční-T23", "accepts_bookings": True})
        cls.nurse_m = Doctor.create({"name": "Sestra Marta-T23"})
        cls.room_doc = Doctor.create({"name": "MVDr. Ordinační Účet-T23", "accepts_bookings": True})
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, *groups, **vals):
            return Users.create(dict({
                "name": "Účet %s" % login, "login": login,
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id] + [cls.env.ref(g).id for g in groups])]},
                **vals))

        cls.user_a = user("t23_treat_a", DOCTOR)
        cls.user_b = user("t23_treat_b", DOCTOR)
        cls.user_nurse = user("t23_treat_nurse", NURSE)
        cls.user_not_booking = user("t23_treat_nb", DOCTOR)   # Lékařka role, member without bookings
        room = cls.env["elite.vet.room"].create({"name": "Ordinace T23 ošetřující"})
        cls.user_room = user("t23_treat_room", DOCTOR, elite_vet_room_id=room.id)
        cls.doc_a.user_id = cls.user_a
        cls.doc_b.user_id = cls.user_b
        cls.nurse_m.user_id = cls.user_nurse
        cls.not_booking = Doctor.create({"name": "MVDr. Bez rezervací-T23", "user_id": cls.user_not_booking.id})
        cls.room_doc.user_id = cls.user_room

    def flush_tracking(self):
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()

    def new_record(self, doctor=None, auto=False):
        record = self.Record.create({"pet_id": self.new_pet("Pacient ošetřující T23").id})
        if doctor:
            record.write({"doctor_id": doctor.id, "doctor_auto": auto})
        self.flush_tracking()   # as if created in an earlier request: later changes are tracked
        return record

    def save(self, user, record, **vals):
        return self.as_user(user).save_record(record.id, vals or {"record_text": "Text %s" % user.login})

    # ---------------------------------------------------------------- set / replace
    def test_edit_sets_an_empty_doctor(self):
        record = self.new_record()
        data = self.save(self.user_a, record)
        self.assertEqual((record.doctor_id, record.doctor_auto), (self.doc_a, False))
        self.assertEqual((data["doctor_name"], data["doctor_auto"]), (self.doc_a.name, False))

    def test_edit_replaces_an_automatic_doctor(self):
        record = self.new_record(self.doc_c, auto=True)
        self.save(self.user_a, record, temperature="38,5")
        self.assertEqual((record.doctor_id, record.doctor_auto), (self.doc_a, False))
        # the change of the doctor is in the history
        self.flush_tracking()
        self.assertTrue(record.message_ids.tracking_value_ids.filtered(
            lambda t: t.field_id.name == "doctor_id"))

    def test_reservation_doctor_is_automatic(self):
        pet = self.new_pet("Z rezervace ošetřující T23")
        res = self.reservation(9, 0, pet=pet, doctor=self.doc_c)
        data = self.as_user(self.nurse).open_today_record(pet.id, res.id)
        record = self.Record.browse(data["id"])
        self.assertEqual((record.doctor_id, record.doctor_auto), (self.doc_c, True))
        self.save(self.user_a, record)
        self.assertEqual(record.doctor_id, self.doc_a)

    def test_roster_doctor_is_automatic(self):
        room = self.env["elite.vet.room"].create({"name": "Ordinace T23 rozpis"})
        self.env["elite.vet.doctor.assignment"].create({
            "doctor_id": self.doc_c.id, "room_id": room.id, "date": clinic_today(),
            "hour_from": 0.0, "hour_to": 24.0})
        data = self.api(self.reception).walk_in(self.new_pet("Rozpis ošetřující T23").id)
        record = self.Record.browse(data["record_id"])
        self.api(self.reception).assign_room(record.id, room.id)
        self.assertEqual((record.doctor_id, record.doctor_auto), (self.doc_c, True))
        self.as_user(self.user_a).add_free_line(record.id, "Konzultace T23", 300)
        self.assertEqual(record.doctor_id, self.doc_a, "a bill line counts")

    def test_bill_lines_and_finishing(self):
        record = self.new_record()
        line = self.Record.env["elite.vet.clinical.record.line"].create(
            {"record_id": record.id, "name": "Položka T23"})
        self.assertFalse(record.doctor_id, "a line by the system user changes nothing")
        self.as_user(self.user_a).update_line(line.id, {"quantity": 2})
        self.assertEqual(record.doctor_id, self.doc_a)
        record2 = self.new_record()
        self.Record.with_user(self.user_b).browse(record2.id).action_done()
        self.assertEqual((record2.state, record2.doctor_id), ("done", self.doc_b))
        record3 = self.new_record()
        line3 = self.Record.env["elite.vet.clinical.record.line"].create(
            {"record_id": record3.id, "name": "Položka T23 b"})
        self.as_user(self.user_b).remove_line(line3.id)
        self.assertEqual(record3.doctor_id, self.doc_b, "removing a line counts")

    def test_backend_form_edit(self):
        record = self.new_record()
        record.with_user(self.user_a).write({"record_text": "Zdravý T23"})
        self.assertEqual(record.doctor_id, self.doc_a)

    # ---------------------------------------------------------------- keep
    def test_explicit_doctor_kept(self):
        record = self.new_record()
        self.save(self.user_b, record, doctor_id=self.doc_c.id)   # chosen in the card
        self.assertEqual((record.doctor_id, record.doctor_auto), (self.doc_c, False))
        self.save(self.user_a, record)
        self.assertEqual(record.doctor_id, self.doc_c)
        self.assertEqual(record.other_doctor_ids, self.doc_a)

    def test_first_treating_doctor_wins(self):
        record = self.new_record()
        self.save(self.user_a, record)
        data = self.save(self.user_b, record, record_text="Nález T23")
        self.assertEqual(record.doctor_id, self.doc_a)
        self.assertEqual(record.other_doctor_ids, self.doc_b)
        self.assertEqual(data["other_doctors"], [self.doc_b.name])
        self.flush_tracking()
        self.assertTrue(record.message_ids.tracking_value_ids.filtered(
            lambda t: t.field_id.name == "other_doctor_ids"), "the later doctor is in the history")
        self.save(self.user_b, record, record_text="Znovu T23")
        self.assertEqual(len(record.other_doctor_ids), 1)

    def test_own_choice_of_doctor_is_not_overwritten_by_the_same_save(self):
        record = self.new_record()
        self.save(self.user_a, record, doctor_id=self.doc_c.id, record_text="S výběrem T23")
        self.assertEqual(record.doctor_id, self.doc_c, "doctor_id in the same save wins")

    # ---------------------------------------------------------------- no change
    def test_nurse_reception_room_account_and_non_booking_change_nothing(self):
        for user in (self.user_nurse, self.user_room, self.user_not_booking, self.nurse, self.doctor_user):
            with self.subTest(user=user.login):
                record = self.new_record()
                auto = self.new_record(self.doc_c, auto=True)
                self.save(user, record)
                self.save(user, auto)
                self.assertFalse(record.doctor_id)
                self.assertEqual((auto.doctor_id, auto.doctor_auto), (self.doc_c, True))
        # reception: only the reception note through the till API
        record = self.new_record()
        data = self.api(self.reception).walk_in(record.pet_id.id)
        self.api(self.reception).set_reception_note(data["record_id"], "Spěchá T23")
        self.assertFalse(self.Record.browse(data["record_id"]).doctor_id)

    def test_cancelled_record_unchanged(self):
        record = self.new_record()
        record.action_cancel()
        record.with_user(self.user_a).write({"room_note": "Po zrušení T23"})
        self.assertFalse(record.doctor_id)
