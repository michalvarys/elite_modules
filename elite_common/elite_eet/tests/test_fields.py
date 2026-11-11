from datetime import datetime

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import fields as eet_fields


@tagged("post_install", "-at_install")
class TestEetFields(BaseCase):
    def test_format_amount(self):
        cases = {
            250: "250.00",
            0.1 + 0.2: "0.30",
            -0.004: "0.00",
            -12.5: "-12.50",
            1.005: "1.01",
            0: "0.00",
            -0.05: "-0.05",
            99999999.99: "99999999.99",
        }
        for value, expected in cases.items():
            result = eet_fields.format_amount(value)
            self.assertEqual(result, expected, value)
            self.assertTrue(eet_fields.AMOUNT_RE.fullmatch(result), result)
        with self.assertRaises(ValueError):
            eet_fields.format_amount(100_000_000)

    def test_format_datetime_winter_summer_dst(self):
        f = eet_fields.format_datetime
        self.assertEqual(f(datetime(2027, 1, 15, 8, 0, 0)), "2027-01-15T09:00:00+01:00")
        self.assertEqual(f(datetime(2027, 7, 1, 8, 0, 0)), "2027-07-01T10:00:00+02:00")
        self.assertEqual(f(datetime(2027, 3, 28, 1, 30, 0)), "2027-03-28T03:30:00+02:00")
        self.assertEqual(f(datetime(2027, 3, 28, 0, 30, 0, 999999)), "2027-03-28T01:30:00+01:00")

    def test_sanitize_text(self):
        s = eet_fields.sanitize_text
        self.assertEqual(s("Pokladna Bar č. 1", 20), "Pokladna Bar c. 1")
        self.assertEqual(s("Arena/0001 REFUND", 25), "Arena/0001 REFUND")
        self.assertEqual(s("Účet (VIP)", 20), "Ucet -VIP-")
        self.assertEqual(s("x" * 30, 25), "x" * 25)
        self.assertEqual(s("ěěě", 20), "eee")
        self.assertEqual(s("a   b", 20), "a b")
        with self.assertRaises(ValueError):
            s("   ", 20)
        self.assertTrue(eet_fields.TEXT20_RE.fullmatch(s("Pokladna Bar č. 1", 20)))

    def test_patterns(self):
        self.assertTrue(eet_fields.EIC_RE.fullmatch("CZ00000019"))
        self.assertFalse(eet_fields.EIC_RE.fullmatch("CZ12"))
        self.assertTrue(eet_fields.ID_JEDNOTKY_RE.fullmatch("303"))
        self.assertFalse(eet_fields.ID_JEDNOTKY_RE.fullmatch("0303"))
        self.assertTrue(eet_fields.TEXT25_RE.fullmatch("00/2224/SO57"))
        self.assertFalse(eet_fields.TEXT20_RE.fullmatch("x" * 21))
