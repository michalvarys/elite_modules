from datetime import timedelta

from odoo.tests import tagged

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestPatientList(ReceptionCase):
    """Staged "Moji pacienti dnes" of the patient card (Task 6)."""

    def items_by_pet(self, data):
        return {item["pet_name"]: item for item in data["items"]}

    def test_items_carry_stage_and_group(self):
        reception = self.api(self.reception)
        doctor_card = self.as_user(self.doctor_user)
        arriving_pet, waiting_pet, room_pet, done_pet = (
            self.new_pet(n) for n in ("Objednaný", "Čekající", "Volaný", "Hotový"))
        arriving = self.reservation(10, 0, pet=arriving_pet)
        waiting = self.reservation(9, 0, pet=waiting_pet)
        in_room = self.reservation(9, 20, pet=room_pet)
        done = self.reservation(8, 30, pet=done_pet)
        waiting_rec = reception.check_in(waiting.id)
        room_rec = reception.check_in(in_room.id)
        self.api(self.doctor_user).call_patient(room_rec["record_id"])
        done_rec = reception.check_in(done.id)
        nurse = self.as_user(self.nurse)
        nurse.add_item(done_rec["record_id"], self.exam.id)
        nurse.mark_done(done_rec["record_id"])
        self.Record.browse(waiting_rec["record_id"]).arrived_at -= timedelta(minutes=6)

        data = doctor_card.my_patients_today()
        self.assertTrue(data["filtered_by_doctor"], "the doctor's own reservations only (unchanged)")
        items = self.items_by_pet(data)
        self.assertTrue({"Objednaný", "Čekající", "Volaný", "Hotový"} <= set(items))

        item = items["Objednaný"]
        self.assertEqual((item["group"], item["visit_stage"], item["reservation_id"]),
                         ("arriving", False, arriving.id))
        self.assertIsNone(item["arrived_time"])
        self.assertIsNone(item["waiting_minutes"])

        item = items["Čekající"]
        self.assertEqual((item["group"], item["visit_stage"], item["record_state"]), ("waiting", "waiting", "draft"))
        self.assertEqual(item["record_id"], waiting_rec["record_id"])
        self.assertRegex(item["arrived_time"], r"^\d{2}:\d{2}$")
        self.assertGreaterEqual(item["waiting_minutes"], 6)
        self.assertFalse(item["walk_in"])

        item = items["Volaný"]
        self.assertEqual((item["group"], item["visit_stage"]), ("in_room", "in_room"))
        self.assertRegex(item["called_time"], r"^\d{2}:\d{2}$")

        item = items["Hotový"]
        self.assertEqual((item["group"], item["record_state"]), ("done", "done"))
        self.assertEqual(item["payment_state"], "waiting")

        self.assertEqual(len({item["key"] for item in data["items"]}), len(data["items"]), "unique keys")

    def test_walk_ins_appear(self):
        reception = self.api(self.reception)
        other_doctor = self.env["elite.vet.doctor"].create({"name": "MVDr. Cizí Neobjednaná-Testová"})
        mine, nobody, theirs = (self.new_pet(n) for n in ("Neobjednaný", "Bez lékařky", "Cizí neobjednaný"))
        mine_rec = reception.walk_in(mine.id, doctor_id=self.doctor.id)
        reception.walk_in(nobody.id)
        reception.walk_in(theirs.id, doctor_id=other_doctor.id)
        # a record opened from the card without reception (no stage) is not a walk-in
        plain = self.new_pet("Bez stavu")
        self.Record.create({"pet_id": plain.id, "doctor_id": self.doctor.id})

        data = self.as_user(self.doctor_user).my_patients_today()
        items = self.items_by_pet(data)
        self.assertIn("Neobjednaný", items)
        self.assertNotIn("Bez lékařky", items, "the doctor filter is kept: a walk-in without a doctor is not hers")
        self.assertNotIn("Cizí neobjednaný", items, "another doctor's walk-in stays filtered out")
        self.assertNotIn("Bez stavu", items)
        item = items["Neobjednaný"]
        self.assertTrue(item["walk_in"])
        self.assertIsNone(item["reservation_id"])
        self.assertEqual((item["record_id"], item["pet_id"], item["group"]), (mine_rec["record_id"], mine.id, "waiting"))
        self.assertEqual(item["owner"], self.owner.name)
        self.assertTrue(item["time"])

        self.api(self.doctor_user).call_patient(mine_rec["record_id"])
        item = self.items_by_pet(self.as_user(self.doctor_user).my_patients_today())["Neobjednaný"]
        self.assertEqual(item["group"], "in_room")

        # without a matching doctor (nurse) every walk-in of today is listed
        names = {i["pet_name"] for i in self.as_user(self.nurse).my_patients_today()["items"]}
        self.assertTrue({"Neobjednaný", "Bez lékařky", "Cizí neobjednaný"} <= names)

    def test_record_data_has_visit_stage(self):
        pet = self.new_pet("Kartový")
        rec = self.api(self.reception).check_in(self.reservation(11, 0, pet=pet).id)
        data = self.as_user(self.doctor_user).card_data(pet.id)
        self.assertEqual(data["today_record"]["id"], rec["record_id"])
        self.assertEqual(data["today_record"]["visit_stage"], "waiting", "card_data stays read-only")

    def test_unassigned_walk_ins_for_every_doctor(self):
        """Ruling R17: a walk-in without a doctor is offered to every doctor under `unassigned`;
        Zavolat gives it the calling doctor."""
        reception = self.api(self.reception)
        pet = self.new_pet("Kohokoli")
        rec = reception.walk_in(pet.id)
        record = self.Record.browse(rec["record_id"])
        self.assertFalse(record.doctor_id)

        data = self.as_user(self.doctor_user).my_patients_today()
        self.assertNotIn("Kohokoli", self.items_by_pet(data), "items keep the doctor filter")
        unassigned = {u["pet_name"]: u for u in data["unassigned"]}
        self.assertIn("Kohokoli", unassigned)
        item = unassigned["Kohokoli"]
        self.assertEqual((item["record_id"], item["group"], item["walk_in"], item["key"]),
                         (record.id, "waiting", True, "w%s" % record.id))
        self.assertIsInstance(item["waiting_minutes"], int)
        # another doctor (manager without a matched doctor sees everything in items instead)
        self.assertEqual(self.as_user(self.nurse).my_patients_today()["unassigned"], [],
                         "an unfiltered list already holds every walk-in")

        self.api(self.doctor_user).call_patient(record.id)
        self.assertEqual(record.doctor_id, self.doctor, "Zavolat assigns the calling doctor")
        self.assertEqual(record.visit_stage, "in_room")
        data = self.as_user(self.doctor_user).my_patients_today()
        self.assertEqual(self.items_by_pet(data)["Kohokoli"]["group"], "in_room")
        self.assertNotIn("Kohokoli", {u["pet_name"] for u in data["unassigned"]})

    def test_call_patient_keeps_an_assigned_doctor(self):
        other = self.env["elite.vet.doctor"].create({"name": "MVDr. Jiná Volající-Testová"})
        pet = self.new_pet("Přidělený")
        rec = self.api(self.reception).walk_in(pet.id, doctor_id=other.id)
        self.api(self.doctor_user).call_patient(rec["record_id"])
        self.assertEqual(self.Record.browse(rec["record_id"]).doctor_id, other)
        # a user without a matched doctor leaves an unassigned record without one
        pet2 = self.new_pet("Bez přidělení")
        rec2 = self.api(self.reception).walk_in(pet2.id)
        self.api(self.nurse).call_patient(rec2["record_id"])
        self.assertFalse(self.Record.browse(rec2["record_id"]).doctor_id)

    def test_waiting_minutes_only_for_open_stages(self):
        pet = self.new_pet("Uzavřený neobjednaný")
        rec = self.api(self.reception).walk_in(pet.id, doctor_id=self.doctor.id)
        nurse = self.as_user(self.nurse)
        nurse.add_item(rec["record_id"], self.exam.id)
        nurse.mark_done(rec["record_id"])
        item = self.items_by_pet(self.as_user(self.doctor_user).my_patients_today())["Uzavřený neobjednaný"]
        self.assertEqual(item["group"], "done")
        self.assertIsNone(item["waiting_minutes"])
