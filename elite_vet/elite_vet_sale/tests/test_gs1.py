from datetime import date

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_vet_sale.models import gs1

GS = "\x1d"


def without_raw(parsed):
    return {k: v for k, v in parsed.items() if k != "raw"}


@tagged("post_install", "-at_install")
class TestGs1(BaseCase):

    def test_datamatrix_with_symbology_prefix(self):
        parsed = gs1.parse("]d201085950016019611727033110A1B2")
        self.assertEqual(parsed["gtin"], "08595001601961")
        self.assertEqual(parsed["expiry"], date(2027, 3, 31))
        self.assertEqual(parsed["lot"], "A1B2")
        self.assertIsNone(parsed["serial"])
        self.assertEqual(parsed["raw"], "]d201085950016019611727033110A1B2")

    def test_fnc1_brackets_and_prefixes_give_the_same_result(self):
        expected = without_raw(gs1.parse("]d201085950016019611727033110A1B2"))
        for code in [
            "0108595001601961" + "10A1B2" + GS + "17270331",       # variable lot in the middle
            "]C1" + "0108595001601961" + "10A1B2" + GS + "17270331",
            "]Q3" + "0108595001601961" + "17270331" + "10A1B2",
            "(01)08595001601961(17)270331(10)A1B2",
            "(01)08595001601961(10)A1B2(17)270331",
            " ]d2(01)08595001601961(10)A1B2(17)270331\n",
        ]:
            self.assertEqual(without_raw(gs1.parse(code)), expected, repr(code))

    def test_day_00_is_the_last_day_of_the_month(self):
        self.assertEqual(gs1.parse("010859500160196117270300")["expiry"], date(2027, 3, 31))
        self.assertEqual(gs1.parse("010859500160196117280200")["expiry"], date(2028, 2, 29))

    def test_serial_number(self):
        parsed = gs1.parse("0108595001601961" + "21SN123" + GS + "10L5" + GS + "17261130")
        self.assertEqual(parsed["serial"], "SN123")
        self.assertEqual(parsed["lot"], "L5")
        self.assertEqual(parsed["expiry"], date(2026, 11, 30))

    def test_plain_ean_and_other_codes_are_not_gs1(self):
        for code in ["8595001601961", "08595001601961", "ABC-123", "0123456789012", ""]:
            parsed = gs1.parse(code)
            self.assertEqual(parsed, {"gtin": None, "lot": None, "expiry": None, "serial": None,
                                      "raw": code.strip()}, repr(code))

    def test_invalid_date_is_dropped(self):
        parsed = gs1.parse("0108595001601961" + "17271332" + "10X")
        self.assertEqual(parsed["gtin"], "08595001601961")
        self.assertIsNone(parsed["expiry"])
        self.assertEqual(parsed["lot"], "X")

    def test_unknown_ai_is_skipped_to_the_next_separator(self):
        # 712 = NHRN (national healthcare reimbursement number), variable length
        for code in ["]d2" + "0108595001601961" + "712ABC12345" + GS + "17270331" + "10L7",
                     "0108595001601961" + "17270331" + "712X9" + GS + "10L7",
                     "(01)08595001601961(712)ABC12345(17)270331(10)L7"]:
            parsed = gs1.parse(code)
            self.assertEqual(parsed["gtin"], "08595001601961", repr(code))
            self.assertEqual(parsed["lot"], "L7", repr(code))
            self.assertEqual(parsed["expiry"], date(2027, 3, 31), repr(code))

    def test_gs1_shape(self):
        self.assertTrue(gs1.is_gs1_shaped(gs1.parse("]d2" + "0108595001601961" + "17270331")))
        self.assertTrue(gs1.is_gs1_shaped(gs1.parse("(01)08595001601961")))
        for code in ["8595001601961", "08595001601961", "ABC-123"]:
            self.assertFalse(gs1.is_gs1_shaped(gs1.parse(code)), repr(code))

    def test_gtin_lookup_forms(self):
        self.assertEqual(gs1.lookup_codes("08595001601961", "x"), ["08595001601961", "8595001601961", "x"])
        self.assertEqual(gs1.lookup_codes(None, "8595001601961"), ["8595001601961", "08595001601961"])
        self.assertEqual(gs1.lookup_codes(None, "08595001601961"), ["08595001601961", "8595001601961"])
        self.assertEqual(gs1.lookup_codes(None, "ABC"), ["ABC"])
