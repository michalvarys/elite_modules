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
    "items": {"id", "code", "name", "classification", "stock_tracked", "tracked_drug", "unit", "barcode", "active",
              "price", "price_untaxed", "vat_rate"},
    "owners": {"id", "kind", "name", "first_name", "last_name", "title", "street", "zip", "city", "country",
               "company_reg", "vat", "note", "important_note", "active", "created", "modified"},
    "contacts": {"id", "owner_id", "type", "value", "label"},
    "patients": {"id", "owner_id", "name", "species", "breed", "sex", "color", "birth_date", "birth_year", "chip",
                 "tattoo", "passport", "weight", "deceased", "death_date", "active", "registered",
                 "next_vaccination", "next_deworming", "important", "note", "created", "modified"},
    "vaccinations": {"id", "patient_id", "date", "next_date", "item_id", "item_name", "quantity", "unit", "kind"},
    "visits": {"id", "patient_id", "date", "time", "case_name", "diagnosis_code", "diagnosis_name", "entered_by",
               "document_id", "notes"},
    "vitals": {"id", "visit_id", "time", "temperature", "heart_rate", "respiratory_rate", "weight", "bp_systolic",
               "bp_diastolic"},
    "sale_documents": {"id", "type", "number", "parent_id", "owner_id", "date", "total", "paid", "from_deposit",
                       "state", "entered_by", "method"},
    "sale_lines": {"id", "document_id", "visit_id", "item_id", "item_code", "item_name", "quantity", "unit",
                   "unit_price", "amount", "vat_rate", "date", "entered_by"},
    "payments": {"id", "document_id", "owner_id", "date", "time", "method", "amount", "from_deposit", "state",
                 "refunded_date"},
    "bundles": {"id", "code", "name", "description"},
    "bundle_lines": {"id", "bundle_id", "item_id", "item_name", "quantity", "unit", "sequence"},
    "phrases": {"id", "name", "group", "text"},
    "stock_lots": {"id", "item_id", "lot", "expiry", "received", "quantity", "unit_cost", "vat_rate",
                   "cost_includes_vat", "supplier"},
    "stock_totals": {"id", "item_id", "total"},
    # contract v4
    "calendar_resources": {"id", "name", "color", "visible", "work_from", "work_to", "sequence"},
    "calendar_activities": {"id", "name", "duration", "color", "symbol", "web"},
    "calendar_events": {"key", "id", "pattern_id", "recurring", "occurrence_date", "start", "end", "all_day",
                        "resource_ids", "activity_id", "owner_id", "patient_id", "title", "busy_status", "done",
                        "modified"},
    # contract v5
    "deposits": {"id", "owner_id", "date", "amount", "sign", "method", "document_id", "used", "refunded",
                 "refunded_date", "balance", "note", "state"},
    "deposit_uses": {"id", "deposit_id", "document_id", "document_number", "date", "amount", "state"},
}


class FakeBlob:
    def __init__(self, text):
        self.text, self.closed = text, False

    def read(self):
        return self.text

    def close(self):
        self.closed = True


def select_columns(sql: str):
    """Column aliases of a reader SELECT (top-level part between SELECT and the first top-level FROM)."""
    parts, depth, current, lower = [], 0, [], sql.lower()
    i = len("select ")
    while i < len(sql):
        ch = sql[i]
        if depth == 0 and lower.startswith(" from ", i):
            break
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current))
    out = []
    for part in parts:
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
            if name == "calendar_events":
                continue  # built by scheduler.EventBuilder (test_calendar)
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

    def test_item_price_mapping_and_sql(self):
        spec = SPECS["items"]
        row = {col: None for col in select_columns(spec.sql)}
        row.update(ID_VARIANTA=4, PRICE=Decimal("121.00"), PRICE_UNTAXED=Decimal("100.00"), DPH_PRODEJ=Decimal("21"))
        rec = spec.mapper(row)
        self.assertEqual((rec["price"], rec["price_untaxed"], rec["vat_rate"]), (121.0, 100.0, 21.0))
        row.update(PRICE=None, PRICE_UNTAXED=None)  # no row in price list 1
        rec = spec.mapper(row)
        self.assertEqual((rec["price"], rec["price_untaxed"]), (None, None))
        self.assertIn("left join VARIANTA_CENIK c", spec.sql)
        self.assertIn("min(c1.ID_VARIANTA_CENIK)", spec.sql)
        self.assertIn("c1.ID_CENIK = 1", spec.sql)
        self.assertEqual(spec.tables, ("VARIANTA", "VARIANTA_CENIK"))

    def test_visit_notes_from_rvf_bytes(self):
        spec = SPECS["visits"]
        row = {col: None for col in select_columns(spec.sql)}
        rvf = "-8 1 3 1\r\n-9 0 0 0 0 0 7\r\n0 2 0 0 0 0\r\nKašel 3 dny\r\nBez horečky\r\n"
        row.update(ID_DENNI_ZAZNAM=1, DEKURS=rvf.encode("cp1250"))
        self.assertEqual(spec.mapper(row)["notes"], "Kašel 3 dny\nBez horečky")
        row.update(DEKURS=None)
        self.assertIsNone(spec.mapper(row)["notes"])
        row.update(DEKURS=b"\x00\xff\x10garbage")
        self.assertIsNone(spec.mapper(row)["notes"])

    def test_vitals_bundles_phrases_mapping(self):
        row = {col: None for col in select_columns(SPECS["vitals"].sql)}
        row.update(ID_DENNI_ZAZNAM_HODNOTA=3, ID_DENNI_ZAZNAM=0, CAS=dt.time(9, 5, 0), TEPLOTA=Decimal("38.5"),
                   TEP=120, HMOTNOST=Decimal("12.40"))
        rec = SPECS["vitals"].mapper(row)
        self.assertEqual(rec, {"id": 3, "visit_id": None, "time": "09:05:00", "temperature": 38.5, "heart_rate": 120,
                               "respiratory_rate": None, "weight": 12.4, "bp_systolic": None, "bp_diastolic": None})
        row = {col: None for col in select_columns(SPECS["bundle_lines"].sql)}
        row.update(ID_SABLONA_VYKONU_POLOZKA=8, ID_SABLONA_VYKONU=2, ID_VARIANTA=-1, VARIANTA_NAZEV=" Vakcína ",
                   MNOZSTVI=Decimal("1.000"), MERNA_JEDNOTKA="ks", PORADI=3)
        rec = SPECS["bundle_lines"].mapper(row)
        self.assertEqual((rec["bundle_id"], rec["item_id"], rec["item_name"], rec["quantity"], rec["sequence"]),
                         (2, None, "Vakcína", 1.0, 3))
        row = {col: None for col in select_columns(SPECS["bundles"].sql)}
        row.update(ID_SABLONA_VYKONU=2, SABLONA_VYKONU="KAST", POPIS=FakeBlob(" Plain description\r\nline 2 "))
        self.assertEqual(SPECS["bundles"].mapper(row)["description"], "Plain description\nline 2")
        row = {col: None for col in select_columns(SPECS["phrases"].sql)}
        row.update(ID_FRAZE=1, FRAZE="Odčervení", PREDEK="Texty",
                   TEXT="-8 1 3 1\r\n-9 0 0 0 0 0 7\r\n11 1 0 0 0 0\r\nDávka:\r\n0 1 -1 1 0 0\r\n 1 tbl/10 kg\r\n")
        rec = SPECS["phrases"].mapper(row)
        self.assertEqual(rec, {"id": 1, "name": "Odčervení", "group": "Texty", "text": "Dávka: 1 tbl/10 kg"})
        row.update(TEXT="Vážený zákazníku,\r\nplain text")
        self.assertEqual(SPECS["phrases"].mapper(row)["text"], "Vážený zákazníku,\nplain text")

    def test_stock_mapping(self):
        row = {col: None for col in select_columns(SPECS["stock_lots"].sql)}
        row.update(ID_DOKLAD_POLOZKA=7, ID_VARIANTA=3, VYROBNI_CISLO="  ", DATUM_EXPIRACE=dt.date(2027, 3, 31),
                   RECEIVED=dt.date(2026, 1, 5), QUANTITY=Decimal("4.000"), CENA_MJ=Decimal("10.50"),
                   SAZBA_DPH=Decimal("21"), S_DPH="A", PARTNER_NAZEV=" Fake Supplier s.r.o. ")
        rec = SPECS["stock_lots"].mapper(row)
        self.assertIsNone(rec["lot"])
        self.assertEqual(rec, {"id": 7, "item_id": 3, "lot": None, "expiry": "2027-03-31",
                               "received": "2026-01-05", "quantity": 4.0, "unit_cost": 10.5, "vat_rate": 21.0,
                               "cost_includes_vat": True, "supplier": "Fake Supplier s.r.o."})
        row.update(VYROBNI_CISLO=" L-1 ", S_DPH="N", ID_VARIANTA=0, DATUM_EXPIRACE=None, RECEIVED=None, PARTNER_NAZEV=None)
        rec = SPECS["stock_lots"].mapper(row)
        self.assertEqual((rec["lot"], rec["cost_includes_vat"], rec["item_id"], rec["expiry"], rec["supplier"]),
                         ("L-1", False, None, None, None))
        row = {col: None for col in select_columns(SPECS["stock_totals"].sql)}
        row.update(ID_VARIANTA_SKLAD_STAV=1, ID_VARIANTA=2, STAV_CELKEM=Decimal("12.500"))
        rec = SPECS["stock_totals"].mapper(row)
        self.assertEqual(tuple(rec), ("id", "item_id", "total"))
        self.assertEqual(rec, {"id": 1, "item_id": 2, "total": 12.5})

    def test_stock_entities_are_always_full_group_stock(self):
        from winvet_bridge.guard import GROUP_TABLES
        from winvet_bridge.sync import ALWAYS_FULL
        for name in ("stock_lots", "stock_totals"):
            self.assertIn(name, ALWAYS_FULL)
            self.assertEqual(SPECS[name].group, "stock")
        self.assertEqual(tuple(GROUP_TABLES["stock"]), ("DOKLAD_POLOZKA_SK", "VARIANTA_SKLAD_STAV"))

    def test_deposit_mapping(self):
        row = {col: None for col in select_columns(SPECS["deposits"].sql)}
        row.update(ID_PARTNER_ZALOHA=4, ID_PARTNER=12, DATUM=dt.date(2026, 9, 21), CASTKA=Decimal("2000"),
                   ZNAMENKO=1, FORMA_UHRADY="HOT ", ID_DOKLAD=-1, CERPANO=0.0, VRACENO=2000.0,
                   VRACENO_DATUM=dt.date(2026, 9, 29), ZUSTATEK=0.0, POZNAMKA="  ", ST="E")
        rec = SPECS["deposits"].mapper(row)
        self.assertEqual(list(rec), list(SPECS["deposits"].keys))
        self.assertEqual(rec, {"id": 4, "owner_id": 12, "date": "2026-09-21", "amount": 2000.0, "sign": 1,
                               "method": "cash", "document_id": None, "used": 0.0, "refunded": 2000.0,
                               "refunded_date": "2026-09-29", "balance": 0.0, "note": None, "state": "E"})
        self.assertIn("z.ID_PARTNER_ZALOHA > 0", build_sql(SPECS["deposits"]))
        row = {col: None for col in select_columns(SPECS["deposit_uses"].sql)}
        row.update(ID_PARTNER_ZALOHA_CERPANI=7, ID_PARTNER_ZALOHA=4, ID_DOKLAD=513, DOKLAD=" 2026000159",
                   DATUM=dt.date(2026, 9, 19), CASTKA=2000.0, ST="I")
        rec = SPECS["deposit_uses"].mapper(row)
        self.assertEqual(rec, {"id": 7, "deposit_id": 4, "document_id": 513, "document_number": "2026000159",
                               "date": "2026-09-19", "amount": 2000.0, "state": "I"})

    def test_sale_document_method(self):
        row = {col: None for col in select_columns(SPECS["sale_documents"].sql)}
        row.update(ID_DOKLAD=467, TYP_DOKLADU="VRAT", FORMA_UHRADY="HOT")
        self.assertEqual(SPECS["sale_documents"].mapper(row)["method"], "cash")
        row.update(FORMA_UHRADY=None)
        self.assertIsNone(SPECS["sale_documents"].mapper(row)["method"])

    def test_deposit_entities_group_and_journal(self):
        from winvet_bridge import DEPOSIT_ENTITIES
        from winvet_bridge.guard import GROUP_TABLES
        from winvet_bridge.journal import JOURNAL_TABLES
        from winvet_bridge.sync import ALWAYS_FULL
        self.assertEqual(ENTITY_ORDER[-2:], DEPOSIT_ENTITIES)
        self.assertEqual(tuple(GROUP_TABLES["deposits"]), ("PARTNER_ZALOHA", "PARTNER_ZALOHA_CERPANI"))
        for name in DEPOSIT_ENTITIES:
            self.assertEqual(SPECS[name].group, "deposits")
        self.assertEqual(JOURNAL_TABLES["PARTNER_ZALOHA"], "deposits")
        self.assertNotIn("PARTNER_ZALOHA_CERPANI", JOURNAL_TABLES)
        self.assertIn("deposit_uses", ALWAYS_FULL)
        self.assertNotIn("deposits", ALWAYS_FULL)

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
