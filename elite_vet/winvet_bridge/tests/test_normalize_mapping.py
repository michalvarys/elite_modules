"""Unit tests: value normalisation and row -> contract record mapping (no database)."""

import datetime as dt
import unittest
from decimal import Decimal

from winvet_bridge import ENTITY_ORDER
from winvet_bridge.entities import (
    SPECS,
    build_sql,
    map_classification,
    map_contact_type,
    map_owner_kind,
    map_payment_method,
)
from winvet_bridge.normalize import combine_datetime, flag_equals, flag_not_equals, norm_value, to_ref

CONTRACT_KEYS = {
    "users": {"id", "name", "code", "active"},
    "items": {"id", "code", "name", "classification", "stock_tracked", "tracked_drug", "unit", "barcode", "active"},
    "owners": {"id", "kind", "name", "first_name", "last_name", "title", "street", "zip", "city", "country",
               "company_reg", "vat", "note", "important_note", "active", "created", "modified"},
    "contacts": {"id", "owner_id", "type", "value", "label"},
    "patients": {"id", "owner_id", "name", "species", "breed", "sex", "color", "birth_date", "birth_year", "chip",
                 "tattoo", "passport", "weight", "deceased", "death_date", "active", "registered",
                 "next_vaccination", "next_deworming", "important", "note", "created", "modified"},
    "vaccinations": {"id", "patient_id", "date", "next_date", "item_id", "item_name", "quantity", "unit", "kind"},
    "visits": {"id", "patient_id", "date", "time", "case_name", "diagnosis_code", "diagnosis_name", "entered_by",
               "document_id"},
    "sale_documents": {"id", "type", "number", "parent_id", "owner_id", "date", "total", "paid", "from_deposit",
                       "state", "entered_by"},
    "sale_lines": {"id", "document_id", "visit_id", "item_id", "item_code", "item_name", "quantity", "unit",
                   "unit_price", "amount", "vat_rate", "date", "entered_by"},
    "payments": {"id", "document_id", "owner_id", "date", "time", "method", "amount", "from_deposit", "state",
                 "refunded_date"},
}


class FakeBlob:
    def __init__(self, text):
        self.text, self.closed = text, False

    def read(self):
        return self.text

    def close(self):
        self.closed = True


def select_columns(sql: str):
    """Column aliases of a reader SELECT (the part between SELECT and the first FROM)."""
    head = sql[len("select "):sql.lower().index(" from ")]
    out = []
    for part in head.split(", "):
        part = part.strip()
        if " as " in part.lower():
            out.append(part.split()[-1].upper())
        else:
            out.append(part.split(".")[-1].upper())
    return out


class NormalizeTest(unittest.TestCase):
    def test_strings(self):
        self.assertEqual(norm_value("  Rex  "), "Rex")
        self.assertIsNone(norm_value("   "))
        self.assertIsNone(norm_value(""))
        self.assertIsNone(norm_value(None))

    def test_dates_times(self):
        self.assertEqual(norm_value(dt.date(2026, 1, 5)), "2026-01-05")
        self.assertEqual(norm_value(dt.datetime(2026, 1, 5, 7, 8, 9, 123)), "2026-01-05 07:08:09")
        self.assertEqual(norm_value(dt.time(7, 8, 9, 500)), "07:08:09")
        self.assertEqual(combine_datetime(dt.date(2026, 1, 5), dt.time(13, 4, 5, 999)), "2026-01-05 13:04:05")
        self.assertEqual(combine_datetime(dt.date(2026, 1, 5), None), "2026-01-05 00:00:00")
        self.assertIsNone(combine_datetime(None, dt.time(1, 2, 3)))
        # WinVet contains typo years such as 218 - still exactly YYYY-MM-DD
        self.assertEqual(norm_value(dt.date(218, 10, 25)), "0218-10-25")

    def test_numbers(self):
        self.assertEqual(norm_value(Decimal("12.50")), 12.5)
        self.assertIsInstance(norm_value(Decimal("12.50")), float)
        self.assertEqual(norm_value(3), 3)
        self.assertEqual(to_ref(0), None)
        self.assertEqual(to_ref(-1), None)
        self.assertEqual(to_ref(7), 7)

    def test_blobs(self):
        blob = FakeBlob("  long note \r\n")
        self.assertEqual(norm_value(blob), "long note")
        self.assertTrue(blob.closed)
        self.assertEqual(norm_value("Žluťoučký kůň".encode("cp1250")), "Žluťoučký kůň")

    def test_flags(self):
        self.assertTrue(flag_equals("A"))
        self.assertTrue(flag_equals("a "))
        self.assertFalse(flag_equals("N"))
        self.assertFalse(flag_equals(None))
        self.assertTrue(flag_not_equals(None))
        self.assertTrue(flag_not_equals("A"))
        self.assertFalse(flag_not_equals("N"))

    def test_code_maps(self):
        self.assertEqual([map_classification(i) for i in range(0, 8)],
                         ["group", "product", "set", "kit", "service", "operation", "alias", "other"])
        self.assertEqual(map_classification(11), "other")
        self.assertEqual(map_classification(-1), "other")
        self.assertIsNone(map_classification(None))
        self.assertEqual([map_owner_kind(i) for i in (0, 1, 2, 9)], ["company", "person", "group", None])
        self.assertEqual([map_contact_type(i) for i in (-1, -2, -3, -4, -5, -9)],
                         ["mobile", "phone", "fax", "email", "web", "other"])
        self.assertEqual([map_payment_method(m) for m in ("HOT", "PLATK", "PREV", "SLOZ ", None)],
                         ["cash", "card", "transfer", "sloz", None])


class MappingTest(unittest.TestCase):
    def test_specs_cover_contract_in_order(self):
        self.assertEqual(tuple(SPECS), ENTITY_ORDER)
        for name, spec in SPECS.items():
            self.assertEqual(set(spec.keys), CONTRACT_KEYS[name], name)

    def test_mapper_returns_exact_contract_keys(self):
        for name, spec in SPECS.items():
            row = {col: None for col in select_columns(spec.sql)}
            record = spec.mapper(row)
            self.assertEqual(set(record), CONTRACT_KEYS[name], name)
            self.assertEqual(list(record), list(spec.keys), name)

    def test_owner_mapping(self):
        spec = SPECS["owners"]
        row = {col: None for col in select_columns(spec.sql)}
        row.update(ID_PARTNER=5, ID_TRIDA_PARTNERA=1, PARTNER_NAZEV=" Novák Jan ", POZNAMKA=FakeBlob("x"),
                   POZNAMKA_DULEZITE="A", AKTIVNI="N", ZALOZENI_ZAZNAMU=dt.date(2020, 2, 3),
                   POSLEDNI_MODIFIKACE=dt.date(2024, 5, 6), CAS=dt.time(10, 11, 12))
        rec = spec.mapper(row)
        self.assertEqual(rec["kind"], "person")
        self.assertEqual(rec["name"], "Novák Jan")
        self.assertTrue(rec["important_note"])
        self.assertFalse(rec["active"])
        self.assertEqual(rec["created"], "2020-02-03")
        self.assertEqual(rec["modified"], "2024-05-06 10:11:12")
        self.assertIsNone(rec["street"])

    def test_sale_line_mapping(self):
        spec = SPECS["sale_lines"]
        row = {col: None for col in select_columns(spec.sql)}
        row.update(ID_DOKLAD_POLOZKA=9, ID_DOKLAD=3, ID_DENNI_ZAZNAM=0, ID_VARIANTA=-10, CENA=Decimal("150.00"),
                   MNOZSTVI=2.0, CENA_MJ=75.0, SAZBA_DPH=21.0, LINE_DATE=dt.date(2026, 3, 1))
        rec = spec.mapper(row)
        self.assertEqual(rec["amount"], 150.0)
        self.assertIsNone(rec["visit_id"])
        self.assertIsNone(rec["item_id"])
        self.assertEqual(rec["date"], "2026-03-01")

    def test_build_sql(self):
        sql = build_sql(SPECS["sale_documents"], 3)
        self.assertIn("trim(d.TYP_DOKLADU) in ('UM', 'PODP', 'FAV', 'VRAT')", sql)
        self.assertIn("d.ID_DOKLAD in (?, ?, ?)", sql)
        self.assertTrue(sql.endswith("order by d.ID_DOKLAD"))
        self.assertNotIn(" where ", build_sql(SPECS["owners"]))


if __name__ == "__main__":
    unittest.main()


class ControlCharactersTest(unittest.TestCase):
    def test_nul_and_control_characters_removed(self):
        from winvet_bridge.normalize import norm_value
        self.assertEqual(norm_value("Vak\x00cína\x07 "), "Vakcína")
        self.assertEqual(norm_value("řádek 1\nřádek 2\tx"), "řádek 1\nřádek 2\tx")
        self.assertIsNone(norm_value("\x00\x00"))
