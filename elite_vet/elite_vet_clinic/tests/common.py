from datetime import datetime, time, timedelta

import pytz

from odoo.tests import TransactionCase

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

# WinVet ids far above real data and the elite_vet_winvet tests (9_000_000+).
BASE = 9_500_000
TZ = pytz.timezone("Europe/Prague")


class ClinicCase(TransactionCase):
    """Own users, doctor, owner, pet and price list items; independent of the data in ev_test."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sync = cls.env["elite.vet.winvet.sync"]
        cls.Record = cls.env["elite.vet.clinical.record"]
        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def user(login, name, *groups):
            return Users.create({"name": name, "login": login, "email": "%s@example.invalid" % login,
                                 "groups_id": [(6, 0, [cls.env.ref("base.group_user").id]
                                                + [cls.env.ref(g).id for g in groups])]})

        cls.reception = user("clinic_reception_test", "Recepční Klinická",
                             "elite_vet_reservation.group_reservation_reception")
        cls.nurse = user("clinic_nurse_test", "Sestra Klinická", "elite_vet_clinic.group_clinic_nurse")
        cls.doctor_user = user("clinic_doctor_test", "Zdeňka Ordinační-Testová",
                               "elite_vet_clinic.group_clinic_doctor")
        cls.manager = user("clinic_manager_test", "Správce Klinický",
                           "elite_vet_reservation.group_reservation_manager")
        cls.doctor = cls.env["elite.vet.doctor"].create({"name": "MVDr. Zdeňka Ordinační-Testová"})
        cls.owner = cls.env["res.partner"].create({
            "name": "Majitelka Klinická-Testová", "phone": "+420 602 111 987", "mobile": "777 654 321",
            "email": "majitelka.clinic@example.invalid", "is_vet_client": True})
        cls.pet = cls.env["elite.vet.pet"].create({
            "name": "Azor Klinický", "partner_id": cls.owner.id, "species": "dog", "breed": "bígl",
            "sex": "pes", "chip": "203 098 100 555 777", "birth_date": clinic_today() - timedelta(days=7 * 365 + 30),
            "weight": 15.0})
        cls.push_ok("items", [
            cls.item_payload(1, "service", name="Klinické vyšetření testovací", price=450.0),
            cls.item_payload(2, "product", name="Vakcína testovací DHPPi", price=620.5, unit="dávka"),
            cls.item_payload(3, "product", name="Odčervení testovací tableta", price=85.0, unit="tbl"),
            cls.item_payload(4, "group", name="Skupina testovací"),
        ])
        Item = cls.env["elite.vet.winvet.item"]
        cls.exam, cls.vaccine, cls.dewormer, cls.group_item = [
            Item.search([("winvet_ref", "=", BASE + n)]) for n in (1, 2, 3, 4)]

    @classmethod
    def item_payload(cls, n, classification, **over):
        rec = {"id": BASE + n, "code": "KT%s" % n, "name": "Položka %s" % n, "classification": classification,
               "stock_tracked": classification == "product", "tracked_drug": False, "unit": "ks",
               "barcode": None, "active": True, "price": 100.0, "price_untaxed": 82.64, "vat_rate": 21}
        rec.update(over)
        return rec

    @classmethod
    def push_ok(cls, entity, records, mode="incremental", deleted=None, batch=1, batches=1, run_id="clinic-run"):
        res = cls.env["elite.vet.winvet.sync"].push({
            "entity": entity, "mode": mode, "records": records, "deleted": deleted or [],
            "batch": batch, "batches": batches, "run_id": run_id})
        assert res.get("ok"), res
        return res

    def as_user(self, user):
        return self.Record.with_user(user)

    def today_utc(self, hour, minute=0):
        local = TZ.localize(datetime.combine(clinic_today(), time(hour, minute)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)
