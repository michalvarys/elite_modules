from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, local_time

from .common import ReceptionCase


@tagged("post_install", "-at_install")
class TestBoard(ReceptionCase):
    """Board inside the till (Task 9): event detail, move and cancel."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_slot_step": 15,
            "booking_block_weekends": False, "booking_block_holidays": False})
        cls.room2 = cls.env["elite.vet.room"].create({"name": "Ordinace test tabule 2"})
        cls.room3 = cls.env["elite.vet.room"].create({"name": "Ordinace test tabule 3"})
        cls.doctor.accepts_bookings = True
        cls.board_proc = cls.env["elite.vet.procedure"].create({
            "name": "Tabule test recepce", "duration": 20, "symbol": "T", "color": "green",
            "room_ids": [(6, 0, [cls.room.id, cls.room2.id])]})
        # one doctor cannot serve in two rooms at once: room 8-10, room 2 10-12
        for room, hour_from, hour_to in ((cls.room, 8.0, 10.0), (cls.room2, 10.0, 12.0)):
            cls.env["elite.vet.doctor.assignment"].create({
                "doctor_id": cls.doctor.id, "room_id": room.id, "date": clinic_today(),
                "hour_from": hour_from, "hour_to": hour_to})
        cls.outsider = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez role tabule", "login": "board_outsider_test",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])]})

    def board_res(self, hour, minute=0, pet=None, **vals):
        vals.setdefault("procedure_id", self.board_proc.id)
        return self.reservation(hour, minute, pet=pet, **vals)

    def mails_of(self, reservation):
        return self.env["mail.mail"].search_count([
            ("model", "=", "elite.vet.reservation"), ("res_id", "=", reservation.id)])

    # ---------------------------------------------------------------- detail
    def test_detail_of_a_reservation_and_after_check_in(self):
        pet = self.new_pet("Tabulový")
        res = self.board_res(9, 0, pet=pet)
        data = self.api(self.reception).board_reservation(res.id)
        self.assertEqual(data["reservation_id"], res.id)
        self.assertEqual(data["main_id"], res.id)
        self.assertEqual((data["pet_id"], data["partner_id"]), (pet.id, self.owner.id))
        self.assertEqual(data["procedure_id"], self.board_proc.id)
        self.assertEqual(data["doctor_id"], self.doctor.id)
        self.assertEqual(data["room_id"], self.room.id)
        self.assertEqual(data["time"], local_time(res.start))
        self.assertEqual(data["state_label"], "Potvrzená")
        self.assertTrue(data["is_today"])
        self.assertTrue(data["can_check_in"] and data["can_move"] and data["can_cancel"])
        self.assertFalse(data["has_record"])
        self.assertFalse(data["payment_state"])

        self.api(self.reception).check_in(res.id)
        data = self.api(self.reception).board_reservation(res.id)
        self.assertTrue(data["has_record"])
        self.assertEqual(data["visit_label"], "Čeká")
        self.assertFalse(data["can_check_in"] or data["can_move"] or data["can_cancel"])

    def test_detail_of_a_web_reservation_without_pet(self):
        res = self.board_res(9, 30, source="web", contact_name="Webová Tabule", pet_name="Neznámý")
        data = self.api(self.reception).board_reservation(res.id)
        self.assertTrue(data["needs_match"])
        self.assertFalse(data["can_check_in"], "a web reservation is matched first (Klient…)")
        self.assertEqual(data["owner"], "Webová Tabule")
        self.assertEqual(data["pet_name"], "Neznámý")

    def test_detail_of_a_second_room_copy_uses_the_main_reservation(self):
        pet = self.new_pet("Dvouordinační")
        res = self.board_res(10, 0, pet=pet)
        second = res.add_second_room(self.room2, self.doctor)
        data = self.api(self.reception).board_reservation(second.id)
        self.assertEqual(data["reservation_id"], second.id)
        self.assertEqual(data["main_id"], res.id)
        self.assertTrue(data["is_second_room"])
        self.assertEqual(data["pet_id"], pet.id)
        self.assertFalse(data["can_move"], "the copy moves with the main reservation")
        self.assertTrue(self.api(self.reception).board_reservation(res.id)["can_move"])
        with self.assertRaises(UserError):
            self.api(self.reception).move_reservation(second.id, str(clinic_today()), 11 * 60, self.room2.id)
        events = {e["id"]: e for e in self.env["elite.vet.reservation"].board_data(str(clinic_today()))["events"]}
        self.assertTrue(events[second.id]["is_second_room"])
        self.assertFalse(events[res.id]["is_second_room"])

    def test_detail_of_a_block_is_refused(self):
        block = self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "room_id": self.room.id, "block_reason": "Úklid",
            "start": self.today_utc(11, 0), "stop": self.today_utc(11, 30)})
        with self.assertRaises(UserError):
            self.api(self.reception).board_reservation(block.id)

    def test_blocks_on_the_till_board_are_for_the_manager_only(self):
        """Task 16: the till does not move or cancel a block, the board says who may edit blocks,
        and the backend board_move refuses a block for every role below Vedení."""
        block = self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "room_id": self.room.id, "block_reason": "Úklid T16",
            "start": self.today_utc(11, 0), "stop": self.today_utc(11, 30)})
        for user in (self.reception, self.nurse, self.doctor_user):
            with self.assertRaises(UserError):
                self.api(user).move_reservation(block.id, str(clinic_today()), 12 * 60, self.room2.id)
            with self.assertRaises(UserError):
                self.api(user).cancel_reservation(block.id)
            with self.assertRaisesRegex(AccessError, "Blokace může měnit jen správce rezervací."):
                self.env["elite.vet.reservation"].with_user(user).board_move(
                    block.id, str(clinic_today()), 12 * 60, self.room2.id)
            data = self.env["elite.vet.reservation"].with_user(user).board_data(str(clinic_today()))
            self.assertFalse(data["can_edit_blocks"], user.login)
            self.assertIn(block.id, [e["id"] for e in data["events"]])
        self.assertEqual((block.room_id, block.start, block.state), (self.room, self.today_utc(11, 0), "confirmed"))
        Rm = self.env["elite.vet.reservation"].with_user(self.manager)
        self.assertTrue(Rm.board_data(str(clinic_today()))["can_edit_blocks"])
        Rm.board_move(block.id, str(clinic_today()), 12 * 60, self.room2.id)
        self.assertEqual(block.room_id, self.room2)

    # ---------------------------------------------------------------- move
    def test_move_to_another_time_and_room(self):
        pet = self.new_pet("Stěhovaný")
        res = self.board_res(9, 0, pet=pet)
        data = self.api(self.reception).move_reservation(res.id, str(clinic_today()), 10 * 60 + 30, self.room2.id)
        self.assertEqual(res.room_id, self.room2)
        self.assertEqual(local_time(res.start), "10:30")
        self.assertEqual(res.duration_minutes, 20, "the length stays")
        self.assertEqual(res.doctor_id, self.doctor, "she is on duty there")
        self.assertEqual((data["room_id"], data["time"]), (self.room2.id, "10:30"))

    def test_move_keeps_the_board_rules(self):
        pet = self.new_pet("Neposlušný")
        res = self.board_res(9, 0, pet=pet)
        self.board_res(10, 0, pet=self.new_pet("Překážka"))
        api = self.api(self.reception)
        with self.assertRaises(UserError, msg="the procedure is not done in room 3"):
            api.move_reservation(res.id, str(clinic_today()), 9 * 60, self.room3.id)
        with self.assertRaises(UserError, msg="overlap with the other reservation"):
            api.move_reservation(res.id, str(clinic_today()), 10 * 60, self.room.id)
        with self.assertRaises(UserError):
            api.move_reservation(res.id, str(clinic_today()), "deset", self.room.id)
        self.assertEqual(local_time(res.start), "09:00")
        self.assertEqual(res.room_id, self.room)

    def test_move_refused_after_check_in_and_for_cancelled(self):
        pet = self.new_pet("Přijatý tabule")
        res = self.board_res(9, 0, pet=pet)
        api = self.api(self.reception)
        api.check_in(res.id)
        with self.assertRaises(UserError):
            api.move_reservation(res.id, str(clinic_today()), 11 * 60, self.room.id)
        other = self.board_res(11, 0, pet=self.new_pet("Zrušený tabule"))
        other.action_cancel()
        with self.assertRaises(UserError):
            api.move_reservation(other.id, str(clinic_today()), 11 * 60, self.room.id)

    # ---------------------------------------------------------------- cancel
    def test_cancel_with_and_without_email(self):
        api = self.api(self.reception)
        res = self.board_res(9, 0, pet=self.new_pet("Rušený"), contact_email="rusena@example.invalid")
        self.assertTrue(api.board_reservation(res.id)["cancel_sends_email"])
        result = api.cancel_reservation(res.id)
        self.assertEqual(result, {"reservation_id": res.id, "state": "cancelled", "email_sent": True})
        self.assertEqual((res.state, res.cancel_reason), ("cancelled", "clinic"))
        self.assertTrue(self.mails_of(res), "same e-mail rule as the backend cancel")
        quiet = self.board_res(9, 30, pet=self.new_pet("Tichý"))
        self.assertFalse(api.board_reservation(quiet.id)["cancel_sends_email"])
        self.assertFalse(api.cancel_reservation(quiet.id)["email_sent"])
        self.assertEqual(quiet.state, "cancelled")
        self.assertFalse(self.mails_of(quiet))
        with self.assertRaises(UserError, msg="already cancelled"):
            api.cancel_reservation(quiet.id)

    def test_cancel_refused_after_check_in(self):
        res = self.board_res(9, 0, pet=self.new_pet("Už přijatý"))
        api = self.api(self.reception)
        api.check_in(res.id)
        with self.assertRaises(UserError):
            api.cancel_reservation(res.id)
        self.assertEqual(res.state, "confirmed")

    def test_cancel_of_a_second_room_copy_cancels_the_reservation(self):
        res = self.board_res(10, 0, pet=self.new_pet("Společný"))
        second = res.add_second_room(self.room2, self.doctor)
        result = self.api(self.reception).cancel_reservation(second.id)
        self.assertEqual(result["reservation_id"], res.id)
        self.assertEqual((res.state, second.state), ("cancelled", "cancelled"))

    # ---------------------------------------------------------------- roles
    def test_board_api_requires_reception(self):
        res = self.board_res(9, 0, pet=self.new_pet("Chráněný"))
        api = self.api(self.outsider)
        with self.assertRaises(AccessError):
            api.board_reservation(res.id)
        with self.assertRaises(AccessError):
            api.move_reservation(res.id, str(clinic_today()), 10 * 60, self.room.id)
        with self.assertRaises(AccessError):
            api.cancel_reservation(res.id)
        self.assertEqual(res.state, "confirmed")

    # ---------------------------------------------------------------- Nedorazil (task 19)
    def test_no_show_from_the_till_board(self):
        owner = self.env["res.partner"].create({"name": "Nedorazil T23", "phone": "+420 777 333 444"})
        pet = self.new_pet("Ztracený T23", owner=owner)
        res = self.board_res(9, 0, pet=pet, contact_email="nedorazil@example.invalid")
        api = self.api(self.reception)
        self.assertTrue(api.board_reservation(res.id)["can_no_show"])
        self.assertEqual(api.owner_data(owner.id)["no_shows"]["count"], 0)
        mails = self.mails_of(res)   # the confirmation of the new reservation, if any
        result = api.no_show_reservation(res.id)
        self.assertEqual(result, {"reservation_id": res.id, "state": "no_show"})
        self.assertEqual((res.state, res.cancel_reason), ("no_show", "no_show"))
        self.assertEqual(self.mails_of(res), mails, "the backend Nedorazil sends no e-mail either")
        self.assertEqual(api.owner_data(owner.id)["no_shows"]["count"], 1)
        detail = api.board_reservation(res.id)
        self.assertFalse(detail["can_no_show"] or detail["can_move"] or detail["can_cancel"])
        with self.assertRaises(UserError):
            api.no_show_reservation(res.id)
        # an earlier day works too
        past = self.board_res(9, 0, pet=self.new_pet("Včerejší T23", owner=owner),
                              start=self.today_utc(9) - timedelta(days=1),
                              stop=self.today_utc(9, 20) - timedelta(days=1))
        self.assertTrue(api.board_reservation(past.id)["can_no_show"])
        api.no_show_reservation(past.id)
        self.assertEqual(past.state, "no_show")

    def test_no_show_refused(self):
        api = self.api(self.reception)
        future = self.board_res(9, 0, pet=self.new_pet("Zítřejší T23"),
                                start=self.today_utc(9) + timedelta(days=1),
                                stop=self.today_utc(9, 20) + timedelta(days=1))
        self.assertFalse(api.board_reservation(future.id)["can_no_show"])
        with self.assertRaises(UserError):
            api.no_show_reservation(future.id)
        received = self.board_res(9, 30, pet=self.new_pet("Přijatý T23"))
        api.check_in(received.id)
        self.assertFalse(api.board_reservation(received.id)["can_no_show"])
        with self.assertRaises(UserError):
            api.no_show_reservation(received.id)
        main = self.board_res(10, 0, pet=self.new_pet("Dvojitý T23"))
        second = main.add_second_room(self.room2, self.doctor)
        self.assertFalse(api.board_reservation(second.id)["can_no_show"])
        with self.assertRaises(UserError):
            api.no_show_reservation(second.id)
        block = self.env["elite.vet.reservation"].create({
            "kind": "block", "state": "confirmed", "room_id": self.room.id, "block_reason": "Porada T23",
            "start": self.today_utc(11, 0), "stop": self.today_utc(11, 30)})
        with self.assertRaises(UserError):
            api.no_show_reservation(block.id)
        cancelled = self.board_res(11, 30, pet=self.new_pet("Zrušený T23"))
        cancelled.action_cancel("clinic")
        with self.assertRaises(UserError):
            api.no_show_reservation(cancelled.id)
        self.assertEqual((future.state, received.state, main.state, block.state),
                         ("confirmed", "confirmed", "confirmed", "confirmed"))
        with self.assertRaises(AccessError):
            self.api(self.outsider).no_show_reservation(main.id)
        self.assertEqual(main.state, "confirmed")
