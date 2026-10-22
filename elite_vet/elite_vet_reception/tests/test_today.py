from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import ReceptionCase

WEB_MESSAGE = "Rezervace z webu ještě není spárovaná s klientem a zvířetem – otevřete Kartotéku."


@tagged("post_install", "-at_install")
class TestToday(ReceptionCase):
    """Visit stages and the reception "today" API (Task 1)."""

    def by_key(self, items, key, value):
        return [item for item in items if item[key] == value]

    def done_with_bill(self, pet):
        nurse = self.as_user(self.nurse)
        data = nurse.open_today_record(pet.id, force_new=True)
        nurse.add_item(data["id"], self.exam.id)
        nurse.mark_done(data["id"])
        return self.Record.browse(data["id"])

    # ---------------------------------------------------------------- today_data
    def test_today_data_splits_the_day(self):
        reception = self.api(self.reception)
        baseline_paid = reception.today_data()["paid_count"]
        pet_arriving, pet_waiting, pet_bill, pet_paid = (
            self.new_pet(n) for n in ("Příchozí", "Čekající", "Účtovaný", "Zaplacený"))
        later = self.reservation(10, 30, pet=pet_arriving)
        earlier = self.reservation(9, 0, pet=pet_waiting)
        web = self.reservation(8, 0, contact_name="Webová Klientka", pet_name="Bobík",
                               contact_email="web.recepce@example.invalid")
        cancelled = self.reservation(11, 0, pet=pet_arriving, state="cancelled")
        reception.check_in(earlier.id, employee_name="Jana")
        bill = self.done_with_bill(pet_bill)
        paid = self.done_with_bill(pet_paid)
        self.settle(paid.sale_order_id)

        data = reception.today_data()
        self.assertEqual(data["date"], clinic_today().isoformat())
        arriving_ids = [a["reservation_id"] for a in data["arriving"]]
        self.assertIn(later.id, arriving_ids)
        self.assertIn(web.id, arriving_ids)
        self.assertNotIn(earlier.id, arriving_ids, "checked-in reservation is no longer arriving")
        self.assertNotIn(cancelled.id, arriving_ids)
        self.assertLess(arriving_ids.index(web.id), arriving_ids.index(later.id), "ordered by time")
        web_item = self.by_key(data["arriving"], "reservation_id", web.id)[0]
        self.assertTrue(web_item["needs_match"])
        self.assertIsNone(web_item["pet_id"])
        self.assertEqual((web_item["pet_name"], web_item["owner"]), ("Bobík", "Webová Klientka"))
        later_item = self.by_key(data["arriving"], "reservation_id", later.id)[0]
        self.assertFalse(later_item["needs_match"])
        self.assertEqual(later_item["pet_id"], pet_arriving.id)
        self.assertEqual(later_item["time"], "10:30")
        self.assertEqual((later_item["doctor"], later_item["room"]), (self.doctor.name, self.room.name))

        waiting = [w for w in data["waiting"] if w["pet_name"] == "Čekající"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual((waiting[0]["stage"], waiting[0]["stage_label"]), ("waiting", "Čeká"))
        self.assertEqual(waiting[0]["room"], self.room.name)
        self.assertIsInstance(waiting[0]["waiting_minutes"], int)
        self.assertTrue(waiting[0]["arrived_time"])
        waiting_names = {w["pet_name"] for w in data["waiting"]}
        self.assertNotIn("Účtovaný", waiting_names, "a finished record is not in the waiting room")

        to_pay = self.by_key(data["to_pay"], "record_id", bill.id)
        self.assertEqual(len(to_pay), 1)
        self.assertEqual(to_pay[0]["sale_order_id"], bill.sale_order_id.id)
        self.assertEqual((to_pay[0]["payment_state"], to_pay[0]["payment_state_label"]),
                         ("waiting", "Čeká na platbu"))
        self.assertAlmostEqual(to_pay[0]["amount"], 450.0, places=2)
        self.assertEqual(to_pay[0]["partner_id"], self.owner.id)
        self.assertFalse(self.by_key(data["to_pay"], "record_id", paid.id), "paid bill not in to_pay")
        self.assertEqual(data["paid_count"], baseline_paid + 1)

    def test_today_data_requires_reception(self):
        outsider = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role", "login": "reception_outsider_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.api(outsider).today_data()
        for user in (self.nurse, self.doctor_user, self.manager):
            self.assertIn("arriving", self.api(user).today_data())

    # ---------------------------------------------------------------- check_in
    def test_check_in_creates_one_record(self):
        pet = self.new_pet("Přijímaný")
        res = self.reservation(9, 0, pet=pet)
        first = self.api(self.reception).check_in(res.id, employee_name="Jana Recepční")
        self.assertEqual(first["stage"], "waiting")
        record = self.Record.browse(first["record_id"])
        self.assertEqual(record.reservation_id, res)
        self.assertEqual(record.state, "draft")
        self.assertEqual(record.visit_stage, "waiting")
        self.assertTrue(record.arrived_at)
        self.assertEqual(record.received_by, "Jana Recepční")
        self.assertEqual(record.doctor_id, self.doctor, "doctor from the reservation")
        second = self.api(self.reception).check_in(res.id)
        self.assertEqual(second["record_id"], first["record_id"])
        self.assertEqual(self.Record.search_count([("reservation_id", "=", res.id)]), 1)

    def test_check_in_after_doctor_opened_card(self):
        """Review Focus 1: the doctor opened the card first -> same record, stays in_room."""
        pet = self.new_pet("Už v ordinaci")
        res = self.reservation(9, 0, pet=pet)
        opened = self.as_user(self.doctor_user).open_today_record(pet.id, res.id)
        record = self.Record.browse(opened["id"])
        self.assertEqual(record.visit_stage, "in_room")
        self.assertTrue(record.called_at)
        data = self.api(self.reception).check_in(res.id)
        self.assertEqual(data["record_id"], record.id)
        self.assertEqual(data["stage"], "in_room")
        self.assertEqual(self.Record.search_count([("pet_id", "=", pet.id)]), 1)

    def test_check_in_web_reservation_without_pet(self):
        """Review Focus 2: an unmatched web reservation is refused; after matching it works."""
        res = self.reservation(9, 0, contact_name="Webový Klient", pet_name="Rex",
                               contact_email="web.klient.recepce@example.invalid", source="web")
        with self.assertRaises(UserError) as err:
            self.api(self.reception).check_in(res.id)
        self.assertEqual(str(err.exception), WEB_MESSAGE)
        pet = self.new_pet("Rex")
        res.write({"pet_id": pet.id, "partner_id": pet.partner_id.id})
        data = self.api(self.reception).check_in(res.id)
        self.assertEqual(self.Record.browse(data["record_id"]).pet_id, pet)

    def test_check_in_requires_reception(self):
        outsider = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role 2", "login": "reception_outsider2_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        res = self.reservation(9, 0, pet=self.new_pet("Cizí"))
        with self.assertRaises(AccessError):
            self.api(outsider).check_in(res.id)

    # ---------------------------------------------------------------- walk_in
    def test_walk_in(self):
        pet = self.new_pet("Bez objednání")
        other_doctor = self.env["elite.vet.doctor"].create({"name": "MVDr. Druhá Recepční-Testová"})
        data = self.api(self.reception).walk_in(pet.id, doctor_id=other_doctor.id, employee_name="Petra")
        record = self.Record.browse(data["record_id"])
        self.assertEqual((record.pet_id, record.state, record.visit_stage), (pet, "draft", "waiting"))
        self.assertFalse(record.reservation_id)
        self.assertEqual(record.doctor_id, other_doctor)
        self.assertEqual(record.received_by, "Petra")
        again = self.api(self.reception).walk_in(pet.id)
        self.assertEqual(again["record_id"], record.id, "open record today is reused")
        # after the visit is finished, a second walk-in the same day is a new record
        self.as_user(self.nurse).mark_done(record.id)
        third = self.api(self.reception).walk_in(pet.id)
        self.assertNotEqual(third["record_id"], record.id)
        self.assertEqual(self.Record.browse(third["record_id"]).visit_stage, "waiting")

    # ---------------------------------------------------------------- call_patient
    def test_call_patient(self):
        pet = self.new_pet("Volaný")
        data = self.api(self.reception).walk_in(pet.id)
        with self.assertRaises(AccessError):
            self.api(self.reception).call_patient(data["record_id"])
        called = self.api(self.nurse).call_patient(data["record_id"])
        self.assertEqual(called["stage"], "in_room")
        record = self.Record.browse(data["record_id"])
        self.assertEqual(record.visit_stage, "in_room")
        self.assertTrue(record.called_at)

    def test_open_today_record_moves_waiting_to_in_room(self):
        pet = self.new_pet("Otevřený z karty")
        data = self.api(self.reception).walk_in(pet.id)
        self.as_user(self.doctor_user).open_today_record(pet.id)
        record = self.Record.browse(data["record_id"])
        self.assertEqual(record.visit_stage, "in_room")
        self.assertTrue(record.called_at)

    # ---------------------------------------------------------------- rights
    def test_reception_cannot_write_record_texts(self):
        pet = self.new_pet("Chráněný")
        data = self.api(self.reception).walk_in(pet.id)
        with self.assertRaises(AccessError):
            self.Record.with_user(self.reception).browse(data["record_id"]).write({"anamnesis": "Recepce píše"})
        with self.assertRaises(AccessError):
            self.as_user(self.reception).save_record(data["record_id"], {"anamnesis": "Recepce píše"})
        with self.assertRaises(AccessError):
            self.as_user(self.reception).open_today_record(pet.id)
