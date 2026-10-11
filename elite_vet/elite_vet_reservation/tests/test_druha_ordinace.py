"""Zákrok pro dvě lékařky (druhá ordinace), lékařka ve službě v průvodci
a světlé / vlastní barvy úkonů."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from ..models.procedure import SVETLE_BARVY
from .common import ReservationCase


@tagged("post_install", "-at_install")
class TestDruhaOrdinace(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = cls.env["elite.vet.reservation"]
        cls.day = fields.Date.today() + timedelta(days=10)

    def hlavni(self, **vals):
        return self.reservation(start=self.dt(self.day, 9, 0), doctor_id=self.dr_a.id, **vals)

    def mails(self):
        return self.env["mail.mail"].search([("email_to", "ilike", "klient@example.cz")])

    def test_pridat_kopiruje_a_propoji(self):
        r = self.hlavni()
        pocet = len(self.mails())
        d = r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        self.assertEqual((d.room_id, d.doctor_id, d.start, d.stop), (self.room2, self.dr_b, r.start, r.stop))
        self.assertEqual((d.partner_id, d.pet_name, d.procedure_id), (r.partner_id, r.pet_name, r.procedure_id))
        self.assertEqual((r.spojena_id, d.spojena_id), (d, r))
        self.assertTrue(d.druha_ordinace and not r.druha_ordinace)
        self.assertEqual(len(self.mails()), pocet, "klientovi nic dalšího nepřijde")

    def test_obsazena_druha_ordinace(self):
        self.reservation(start=self.dt(self.day, 9, 0), room_id=self.room2.id)
        r = self.hlavni()
        with self.assertRaises(ValidationError):
            r.pridat_druhou_ordinaci(self.room2, self.dr_b)

    def test_nejde_dvakrat_ani_do_stejne(self):
        r = self.hlavni()
        with self.assertRaises(UserError):
            r.pridat_druhou_ordinaci(self.room1)
        d = r.pridat_druhou_ordinaci(self.room2)
        with self.assertRaises(UserError):
            r.pridat_druhou_ordinaci(self.sal)
        with self.assertRaises(UserError):
            d.pridat_druhou_ordinaci(self.sal)

    def test_presun_posune_obe(self):
        r = self.hlavni()
        d = r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        r.action_reschedule(self.dt(self.day, 11, 0))
        self.assertEqual((d.start, d.stop, d.room_id), (r.start, r.stop, self.room2))
        d.action_reschedule(self.dt(self.day, 13, 0))
        self.assertEqual(r.start, self.dt(self.day, 13, 0))

    def test_presun_do_obsazene_druhe_ordinace_selze(self):
        r = self.hlavni()
        r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        self.reservation(start=self.dt(self.day, 11, 0), room_id=self.room2.id)
        with self.assertRaises(ValidationError):
            r.action_reschedule(self.dt(self.day, 11, 0))

    def test_zruseni_hlavni_zrusi_obe_jeden_email(self):
        r = self.hlavni()
        d = r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        pocet = len(self.mails())
        r.action_cancel()
        self.assertEqual((r.state, d.state), ("cancelled", "cancelled"))
        self.assertEqual(len(self.mails()), pocet + 1)

    def test_zruseni_jen_druhe(self):
        r = self.hlavni()
        d = r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        pocet = len(self.mails())
        d.action_cancel()
        self.assertEqual((r.state, d.state), ("confirmed", "cancelled"))
        self.assertFalse(r.spojena_id)
        self.assertEqual(len(self.mails()), pocet)
        r.pridat_druhou_ordinaci(self.sal)   # jde znovu

    def test_probehla_a_presun_druhe_bez_emailu(self):
        r = self.hlavni()
        d = r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        pocet = len(self.mails())
        r.action_reschedule(self.dt(self.day, 10, 0))
        self.assertEqual(len(self.mails()), pocet + 1, "jen jeden e-mail o přesunu")
        r.action_done()
        self.assertEqual(d.state, "done")

    def test_tabule_ukaze_spojeni(self):
        r = self.hlavni()
        r.pridat_druhou_ordinaci(self.room2, self.dr_b)
        ev = {e["id"]: e for e in self.R.board_data(fields.Date.to_string(self.day))["events"]}
        self.assertEqual(ev[r.id]["spojena"], "Ordinace 2 · " + self.dr_b.name)
        self.assertEqual(ev[r.spojena_id.id]["spojena"], "Ordinace 1 · " + self.dr_a.name)

    def test_pruvodce_predvyplni_lekarku_ve_sluzbe(self):
        r = self.hlavni()
        self.assign(self.dr_b, self.room2, self.day, 8.0, 12.0)
        w = Form(self.env["elite.vet.reservation.druha.wizard"].with_context(default_reservation_id=r.id))
        w.room_id = self.room2
        self.assertEqual(w.doctor_id, self.dr_b)
        w.save().action_pridat()
        self.assertEqual(r.spojena_id.doctor_id, self.dr_b)


@tagged("post_install", "-at_install")
class TestLekarkaVeSluzbe(ReservationCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = fields.Date.today() + timedelta(days=10)
        cls.W = cls.env["elite.vet.reservation.wizard"]
        for wd in range(7):
            cls.hours(cls, cls.room1, wd, 8.0, 19.0)
        cls.env["elite.vet.setting"].nastaveni().write({
            "booking_require_doctor": False, "booking_max_days_ahead": 60, "booking_slot_step": 15})

    def form(self, minute):
        ctx = {"default_date": fields.Date.to_string(self.day), "default_minute": minute,
               "default_room_id": self.room1.id}
        f = Form(self.W.with_context(**ctx))
        f.procedure_id = self.vacc
        return f

    def test_jedna_ve_sluzbe_vybere_se_sama(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        self.assign(self.dr_b, self.room1, self.day, 14.0, 19.0)
        self.assertEqual(self.form(9 * 60).doctor_id, self.dr_a)
        self.assertEqual(self.form(15 * 60).doctor_id, self.dr_b)

    def test_prekryv_nabidne_vyber(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        self.assign(self.dr_b, self.room1, self.day, 12.0, 19.0)
        f = self.form(13 * 60)
        self.assertFalse(f.doctor_id)
        self.assertEqual(set(f.lekarky_ve_sluzbe_ids.ids), {self.dr_a.id, self.dr_b.id})
        f.lekarka_sluzby_id = self.dr_b
        self.assertEqual(f.doctor_id, self.dr_b)
        w = f.save()
        w.action_krok_cas()
        self.assertEqual((w.step, w.slot_doctor_id), ("klient", self.dr_b))

    def test_bez_kliku_z_tabule_nic(self):
        self.assign(self.dr_a, self.room1, self.day, 8.0, 14.0)
        f = Form(self.W.with_context(default_date=fields.Date.to_string(self.day)))
        f.procedure_id = self.vacc
        self.assertFalse(f.doctor_id)


@tagged("post_install", "-at_install")
class TestBarvyUkonu(ReservationCase):

    def test_svetla_a_vlastni_barva(self):
        self.vacc.color = "light_yellow"
        self.assertEqual(self.vacc.color_hex, SVETLE_BARVY["light_yellow"][1])
        self.vacc.barva_vlastni = "#ffeedd"
        self.assertEqual(self.vacc.color_hex, "#ffeedd")
        with Form(self.vacc) as f:
            f.color = "light_blue"
            self.assertFalse(f.barva_vlastni)
        self.assertEqual(self.vacc.color_hex, SVETLE_BARVY["light_blue"][1])
