from datetime import datetime
from decimal import Decimal

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import message

NS = "{http://fs.gov.cz/eet/schema/v4}"
UUID = "03965780-6457-4842-bd80-5f9195c0b8c8"


def sale_data(**kw):
    vals = dict(
        eic_popl="CZ00000019",
        id_jednotky="303",
        id_pokl="Pokladna 1",
        porad_cis="Arena/0001",
        dat_trzby=datetime(2027, 1, 15, 8, 0, 0),
        celk_trzba=Decimal("250"),
    )
    vals.update(kw)
    return message.SaleData(**vals)


def build(data, **kw):
    args = dict(uuid=UUID, sent_at=datetime(2027, 1, 15, 8, 0, 1), first=True, verification=False)
    args.update(kw)
    return message.build_trzba(data, **args)


@tagged("post_install", "-at_install")
class TestEetMessage(BaseCase):
    def test_build_valid_minimal(self):
        trzba = build(sale_data())
        head = trzba.find(NS + "Hlavicka")
        data = trzba.find(NS + "Data")
        self.assertEqual(head.get("uuid_zpravy"), UUID)
        self.assertEqual(head.get("dat_odesl"), "2027-01-15T09:00:01+01:00")
        self.assertEqual(head.get("prvni_zaslani"), "true")
        self.assertEqual(head.get("overeni"), "false")
        self.assertEqual(data.get("celk_trzba"), "250.00")
        self.assertEqual(data.get("dat_trzby"), "2027-01-15T09:00:00+01:00")
        self.assertIsNone(data.get("urceno_cerp_zuct"))
        self.assertIsNone(data.get("eic_poverujiciho"))

    def test_build_resend_and_verification_flags(self):
        head = build(sale_data(), first=False, verification=True).find(NS + "Hlavicka")
        self.assertEqual(head.get("prvni_zaslani"), "false")
        self.assertEqual(head.get("overeni"), "true")

    def test_build_with_vouchers(self):
        data = build(sale_data(urceno_cerp_zuct=25, cerp_zuct=302)).find(NS + "Data")
        self.assertEqual(data.get("urceno_cerp_zuct"), "25.00")
        self.assertEqual(data.get("cerp_zuct"), "302.00")

    def test_build_omits_zero_vouchers(self):
        data = build(sale_data(urceno_cerp_zuct=0, cerp_zuct=0.0)).find(NS + "Data")
        self.assertIsNone(data.get("urceno_cerp_zuct"))
        self.assertIsNone(data.get("cerp_zuct"))

    def test_build_negative_amount(self):
        data = build(sale_data(celk_trzba=-120)).find(NS + "Data")
        self.assertEqual(data.get("celk_trzba"), "-120.00")

    def test_build_rejects_bad_eic(self):
        with self.assertRaises(message.MessageError):
            build(sale_data(eic_popl="CZ12"))

    def test_build_rejects_bad_id_pokl(self):
        with self.assertRaises(message.MessageError):
            build(sale_data(id_pokl="Bar č.1"))
