from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today
from odoo.addons.elite_vet_reservation.models.live import PRECOMMIT_KEY

from .common import ReceptionCase

NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"
MANAGER = "elite_vet_reservation.group_reservation_manager"
RECEPTION_MODEL = "odoo.addons.elite_vet_reception.models.room_board.ReceptionRooms"


@tagged("post_install", "-at_install")
class TestRooms(ReceptionCase):
    """Screen Ordinace: room accounts, room of the visit, doctor from the roster (Task 15)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Room = cls.env["elite.vet.room"]
        cls.room1 = Room.create({"name": "Ordinace T15 jedna", "sequence": 900})
        cls.room2 = Room.create({"name": "Ordinace T15 dvě", "sequence": 901})
        Doctor = cls.env["elite.vet.doctor"]
        cls.doc_a = Doctor.create({"name": "MVDr. Alena Službová-Testová", "accepts_bookings": True})
        cls.doc_b = Doctor.create({"name": "MVDr. Bára Službová-Testová", "accepts_bookings": True})
        cls.room_user = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Ordinace T15 účet", "login": "room_account_test", "email": "room_account@example.invalid",
            "elite_vet_room_id": cls.room1.id,
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref(DOCTOR).id])]})
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role ordinace", "login": "room_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})
        cls.room_action = cls.env.ref("elite_vet_reception.action_room_board")

    def duty(self, room, doctor, hour_from=0.0, hour_to=24.0):
        return self.env["elite.vet.doctor.assignment"].create({
            "doctor_id": doctor.id, "room_id": room.id, "date": clinic_today(),
            "hour_from": hour_from, "hour_to": hour_to})

    def walk_in(self, name, **kw):
        data = self.api(self.reception).walk_in(self.new_pet(name).id, **kw)
        return self.Record.browse(data["record_id"])

    def column(self, data, room):
        key = "room-%d" % room.id if room else "unassigned"
        return next(c for c in data["columns"] if c["key"] == key)

    def keys(self, column, section):
        return [i["key"] for i in column["sections"][section]]

    # ---------------------------------------------------------------- room of the visit
    def test_check_in_takes_the_reservation_room(self):
        res = self.reservation(9, 0, pet=self.new_pet("Z rezervace"), room_id=self.room2.id)
        data = self.api(self.reception).check_in(res.id)
        record = self.Record.browse(data["record_id"])
        self.assertEqual(record.room_id, self.room2)
        self.assertEqual((data["room_id"], data["room"]), (self.room2.id, self.room2.name))
        # the doctor of the reservation stays (the roster only fills an empty doctor)
        self.assertEqual(record.doctor_id, self.doctor)

    def test_existing_draft_with_reservation_gets_its_room(self):
        """A record opened from the card before the field existed / before arrival: computed."""
        pet = self.new_pet("Rozepsaný předem")
        res = self.reservation(10, 0, pet=pet, room_id=self.room1.id)
        data = self.as_user(self.doctor_user).open_today_record(pet.id, res.id)
        self.assertEqual(self.Record.browse(data["id"]).room_id, self.room1)

    def test_walk_in_is_unassigned_or_in_the_chosen_room(self):
        record = self.walk_in("Bez ordinace")
        self.assertFalse(record.room_id)
        self.duty(self.room2, self.doc_a)
        record2 = self.walk_in("S ordinací", room_id=self.room2.id)
        self.assertEqual(record2.room_id, self.room2)
        self.assertEqual(record2.doctor_id, self.doc_a, "doctor on duty in the chosen room")
        self.assertIn({"id": self.room2.id, "name": self.room2.name},
                      self.api(self.reception).booking_options()["rooms"])

    # ---------------------------------------------------------------- assign_room
    def test_assign_move_unassign(self):
        record = self.walk_in("Stěhovaný")
        reception = self.api(self.reception)
        precommit = self.env.cr.precommit.data
        precommit.pop(PRECOMMIT_KEY, None)
        result = reception.assign_room(record.id, self.room1.id)
        self.assertIn(PRECOMMIT_KEY, precommit, "the screens refresh (bus)")
        self.assertEqual((record.room_id, result["room_id"], result["needs_doctor"]), (self.room1, self.room1.id, []))
        reception.assign_room(record.id, self.room2.id)
        self.assertEqual(record.room_id, self.room2)
        reception.assign_room(record.id, False)
        self.assertFalse(record.room_id)
        self.assertEqual(record.visit_stage, "waiting", "assigning does not call the patient")

    def test_assign_keeps_the_reservation_room(self):
        res = self.reservation(9, 30, pet=self.new_pet("Přesunutý"), room_id=self.room1.id)
        data = self.api(self.reception).check_in(res.id)
        self.api(self.nurse).assign_room(data["record_id"], self.room2.id)
        self.assertEqual(self.Record.browse(data["record_id"]).room_id, self.room2)
        self.assertEqual(res.room_id, self.room1)

    # ---------------------------------------------------------------- take_next_patient (task 26)
    def test_take_next_takes_the_longest_waiting(self):
        reception = self.api(self.reception)
        later = self.walk_in("Přišel později")
        first = self.walk_in("Čeká nejdéle")
        in_room = self.walk_in("Už je u sestry")
        now = fields.Datetime.now()
        first.arrived_at = now - timedelta(minutes=40)
        later.arrived_at = now - timedelta(minutes=10)
        in_room.write({"arrived_at": now - timedelta(minutes=60), "visit_stage": "in_room"})
        other_room = self.walk_in("Má ordinaci", room_id=self.room2.id)
        other_room.arrived_at = now - timedelta(minutes=90)
        self.duty(self.room1, self.doc_a)
        precommit = self.env.cr.precommit.data
        precommit.pop(PRECOMMIT_KEY, None)
        result = reception.take_next_patient(self.room1.id)
        self.assertIn(PRECOMMIT_KEY, precommit, "the screens refresh (bus)")
        self.assertEqual((result["record_id"], result["room_id"], result["needs_doctor"]), (first.id, self.room1.id, []))
        self.assertEqual((first.room_id, first.doctor_id, first.visit_stage), (self.room1, self.doc_a, "waiting"),
                         "same rules as assign_room: doctor on duty, not called in")
        self.assertEqual(reception.take_next_patient(self.room1.id)["record_id"], later.id)
        self.assertFalse(reception.take_next_patient(self.room1.id), "nobody waits without a room")
        self.assertFalse(in_room.room_id, "a patient already in a room is not taken")
        self.assertEqual(other_room.room_id, self.room2, "assigned patients stay")

    def test_take_next_two_on_duty_and_rights(self):
        record = self.walk_in("Dvě ve službě")
        self.duty(self.room1, self.doc_a)
        self.duty(self.room1, self.doc_b)
        result = self.api(self.nurse).take_next_patient(self.room1.id)
        self.assertEqual(result["record_id"], record.id)
        self.assertEqual({d["id"] for d in result["needs_doctor"]}, {self.doc_a.id, self.doc_b.id})
        with self.assertRaises(UserError):
            self.api(self.reception).take_next_patient(False)
        with self.assertRaises(AccessError):
            self.api(self.outsider).take_next_patient(self.room1.id)
        # done and other days' visits are never taken
        done = self.walk_in("Hotový dnes")
        self.as_user(self.nurse).mark_done(done.id)
        self.assertFalse(self.api(self.reception).take_next_patient(self.room2.id))

    def test_assign_only_today_drafts(self):
        record = self.walk_in("Hotový")
        self.as_user(self.nurse).mark_done(record.id)
        with self.assertRaises(UserError):
            self.api(self.reception).assign_room(record.id, self.room1.id)
        with self.assertRaises(UserError):
            self.api(self.reception).assign_room(self.walk_in("Neznámá ordinace").id, 999999999)

    # ---------------------------------------------------------------- doctor from the roster
    def test_doctor_from_roster_one_on_duty(self):
        self.duty(self.room1, self.doc_a)
        self.duty(self.room2, self.doc_b)
        record = self.walk_in("Jedna lékařka")
        result = self.api(self.reception).assign_room(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_a)
        self.assertEqual(result["needs_doctor"], [])
        # moving it on keeps the doctor it already has
        self.api(self.reception).assign_room(record.id, self.room2.id)
        self.assertEqual(record.doctor_id, self.doc_a)

    def test_doctor_from_roster_two_on_duty(self):
        self.duty(self.room1, self.doc_a, 0.0, 24.0)
        self.duty(self.room1, self.doc_b, 0.0, 24.0)
        record = self.walk_in("Dvě lékařky")
        result = self.api(self.reception).assign_room(record.id, self.room1.id)
        self.assertEqual(record.room_id, self.room1)
        self.assertFalse(record.doctor_id)
        self.assertEqual({d["id"] for d in result["needs_doctor"]}, {self.doc_a.id, self.doc_b.id})
        result = self.api(self.reception).assign_room(record.id, self.room1.id, self.doc_b.id)
        self.assertEqual((record.doctor_id, result["needs_doctor"]), (self.doc_b, []))

    def test_doctor_from_roster_none_on_duty(self):
        # a shift that is not now: patched clock 12:00, shift 6–8
        self.duty(self.room1, self.doc_a, 6.0, 8.0)
        record = self.walk_in("Nikdo ve službě")
        with patch("%s._clinic_hour_now" % RECEPTION_MODEL, return_value=12.0):
            result = self.api(self.reception).assign_room(record.id, self.room1.id)
            self.assertFalse(record.doctor_id)
            self.assertEqual(result["needs_doctor"], [])
            board = self.api(self.reception).room_board()
        column = self.column(board, self.room1)
        self.assertEqual(column["on_duty"], [])
        self.assertEqual(column["shifts"], [{"doctor": self.doc_a.name, "label": "6:00–8:00", "now": False}])

    def test_existing_doctor_kept(self):
        self.duty(self.room1, self.doc_a)
        record = self.walk_in("Vlastní lékařka", doctor_id=self.doc_b.id)
        self.api(self.reception).assign_room(record.id, self.room1.id)
        self.assertEqual(record.doctor_id, self.doc_b)

    # ---------------------------------------------------------------- Zavolat
    def test_call_in_a_room(self):
        self.duty(self.room2, self.doc_a)
        record = self.walk_in("Zavolaný do ordinace")
        result = self.api(self.room_user).call_patient(record.id, self.room2.id)
        self.assertEqual((record.visit_stage, record.room_id, record.doctor_id), ("in_room", self.room2, self.doc_a))
        self.assertEqual(result["needs_doctor"], [])
        self.assertEqual(result["stage"], "in_room")

    def test_call_with_two_on_duty_asks(self):
        self.duty(self.room1, self.doc_a)
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Volaný dvěma")
        result = self.api(self.room_user).call_patient(record.id, self.room1.id)
        self.assertEqual(record.visit_stage, "in_room")
        self.assertFalse(record.doctor_id)
        self.assertEqual(len(result["needs_doctor"]), 2)
        result = self.api(self.room_user).call_patient(record.id, self.room1.id, self.doc_a.id)
        self.assertEqual(record.doctor_id, self.doc_a)

    def test_call_without_room_keeps_old_behaviour(self):
        """Ruling R17 (Moji pacienti dnes): no room -> the doctor matched by the caller's name."""
        record = self.walk_in("Volaný postaru")
        result = self.api(self.doctor_user).call_patient(record.id)
        self.assertEqual(record.doctor_id, self.doctor)
        self.assertFalse(record.room_id)
        self.assertEqual(result["needs_doctor"], [])

    def test_call_uses_the_record_room(self):
        self.duty(self.room1, self.doc_b)
        record = self.walk_in("Volaný z karty")
        self.api(self.reception).assign_room(record.id, self.room1.id)
        record.doctor_id = False
        self.api(self.nurse).call_patient(record.id)
        self.assertEqual(record.doctor_id, self.doc_b)

    # ---------------------------------------------------------------- room_board
    def test_room_board_shape(self):
        self.duty(self.room1, self.doc_a)
        reception = self.api(self.reception)
        booked = self.reservation(15, 0, pet=self.new_pet("Objednaný T15"), room_id=self.room1.id)
        arrived = self.reservation(8, 0, pet=self.new_pet("Přišlý T15"), room_id=self.room1.id)
        rec_arrived = self.Record.browse(reception.check_in(arrived.id)["record_id"])
        unassigned = self.walk_in("Nepřiřazený T15")
        in_room = self.walk_in("V ordinaci T15")
        self.api(self.room_user).call_patient(in_room.id, self.room1.id)
        done = self.walk_in("Hotový T15", room_id=self.room1.id)
        self.as_user(self.nurse).mark_done(done.id)

        data = reception.room_board()
        self.assertEqual(data["date"], clinic_today().isoformat())
        self.assertTrue(data["is_today"])
        self.assertEqual(data["columns"][0]["key"], "unassigned")
        self.assertEqual(data["columns"][0]["name"], "Nepřiřazení")
        room_ids = [r["id"] for r in data["rooms"]]
        self.assertLess(room_ids.index(self.room1.id), room_ids.index(self.room2.id), "rooms in sequence")
        self.assertEqual([c["room_id"] for c in data["columns"][1:]], room_ids)

        free = self.column(data, None)
        self.assertIn("r%d" % unassigned.id, self.keys(free, "waiting"))
        col1 = self.column(data, self.room1)
        self.assertEqual(col1["on_duty"], [{"id": self.doc_a.id, "name": self.doc_a.name}])
        self.assertEqual(self.keys(col1, "in_room"), ["r%d" % in_room.id])
        self.assertEqual(self.keys(col1, "waiting"), ["r%d" % rec_arrived.id])
        self.assertIn("b%d" % booked.id, self.keys(col1, "booked"))
        self.assertIn("r%d" % done.id, self.keys(col1, "done"))
        self.assertEqual(col1["counts"]["in_room"], 1)
        self.assertEqual(self.column(data, self.room2)["on_duty"], [])

        card = col1["sections"]["waiting"][0]
        self.assertEqual((card["pet_name"], card["stage"], card["reservation_time"]), ("Přišlý T15", "waiting", "08:00"))
        self.assertTrue(card["draggable"])
        self.assertIsInstance(card["waiting_minutes"], int)
        self.assertEqual(card["owner"], self.owner.name)
        self.assertEqual(card["doctor"], self.doctor.name)
        booked_card = next(i for i in col1["sections"]["booked"] if i["key"] == "b%d" % booked.id)
        self.assertFalse(booked_card["draggable"])
        self.assertIsNone(booked_card["record_id"])
        self.assertEqual(booked_card["time"], "15:00")
        self.assertEqual(data["perms"], {"can_call": False, "user_room_id": None,
                                         "member_account": False, "roster_room_id": None})
        self.assertEqual(self.api(self.room_user).room_board()["perms"],
                         {"can_call": True, "user_room_id": self.room1.id,
                          "member_account": False, "roster_room_id": None})

    # ---------------------------------------------------------------- rights
    def test_rights(self):
        record = self.walk_in("Práva T15")
        for method, args in (("room_board", []), ("assign_room", [record.id, self.room1.id])):
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(self.api(self.outsider), method)(*args)
        for user in (self.reception, self.nurse, self.doctor_user, self.manager):
            with self.subTest(user=user.login):
                self.api(user).room_board()
                self.api(user).assign_room(record.id, self.room1.id)
        with self.assertRaises(AccessError):
            self.api(self.reception).call_patient(record.id, self.room1.id)

    # ---------------------------------------------------------------- room account
    def test_room_account_home_action(self):
        self.assertEqual(self.room_user.action_id.id, self.room_action.id)
        card_action = self.env.ref("elite_vet_clinic.action_patient_card")
        self.room_user.elite_vet_room_id = False
        self.assertEqual(self.room_user.action_id.id, card_action.id)
        self.room_user.elite_vet_room_id = self.room2
        self.assertEqual(self.room_user.action_id.id, self.room_action.id)
        # Vedení keeps its own home even with a room
        self.room_user.write({"groups_id": [(4, self.env.ref(MANAGER).id)]})
        self.assertEqual(self.room_user.action_id.id, self.env.ref("elite_vet_winvet.action_winvet_dashboard").id)

    def test_room_menu_for_every_role(self):
        menu = self.env.ref("elite_vet_reception.menu_room_board")
        root = self.env.ref("elite_vet_clinic.menu_clinic_root")
        self.assertEqual(menu.parent_id, root)
        children = self.env["ir.ui.menu"].search([("parent_id", "=", root.id)], order="sequence, id")
        self.assertEqual(children[:1], menu, "first item of Ordinace")
        for user in (self.reception, self.nurse, self.doctor_user, self.manager, self.room_user):
            with self.subTest(user=user.login):
                loaded = self.env["ir.ui.menu"].with_user(user).load_menus(False)
                self.assertIn(menu.id, loaded)
        self.assertNotIn(menu.id, self.env["ir.ui.menu"].with_user(self.outsider).load_menus(False))

    # ---------------------------------------------------------------- POS Dnes
    def test_today_data_shows_the_visit_room(self):
        record = self.walk_in("Dnes s ordinací")
        reception = self.api(self.reception)
        row = next(w for w in reception.today_data()["waiting"] if w["record_id"] == record.id)
        self.assertIsNone(row["room"])
        reception.assign_room(record.id, self.room2.id)
        row = next(w for w in reception.today_data()["waiting"] if w["record_id"] == record.id)
        self.assertEqual(row["room"], self.room2.name)
