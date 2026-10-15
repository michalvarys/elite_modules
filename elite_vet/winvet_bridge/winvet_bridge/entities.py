"""Entity readers: WinVet tables -> contract record dicts.

Every reader selects explicit columns from base tables only (no views, no stored procedures, no
``select *``). Each ``read_all()`` / ``read_ids()`` call runs in its own short read-only
transaction.

Entity -> primary fingerprint group (documentation; blocking is derived from *all* tables an entity
reads, see :data:`ENTITY_TABLES` and :func:`winvet_bridge.guard.entity_groups`):

=============== ========= ==========================================
entity          group     tables read
=============== ========= ==========================================
users           catalog   UZIVATEL_NEW
items           catalog   VARIANTA
owners          owners    PARTNER
contacts        owners    PARTNER_KONTAKT
patients        patients  PACIENT
vaccinations    patients  VAKCINACE_ODCERVENI
visits          clinical  DENNI_ZAZNAM
sale_documents  sales     DOKLAD
sale_lines      sales     DOKLAD_POLOZKA_UM, DOKLAD (sales), DENNI_ZAZNAM (clinical)
payments        sales     PLATBA
=============== ========= ==========================================

Foreign keys (``*_id``, ``entered_by``) with WinVet's "no reference" values 0 / negative are sent as
``null``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import ENTITY_ORDER
from .normalize import (
    combine_datetime,
    flag_equals,
    flag_not_equals,
    norm_value,
    to_float,
    to_int,
    to_ref,
)

ID_CHUNK = 250  # ids per "IN (...)" (Firebird allows at most 1500 list elements)

CLASSIFICATION = {0: "group", 1: "product", 2: "set", 3: "kit", 4: "service", 5: "operation", 6: "alias"}
OWNER_KIND = {0: "company", 1: "person", 2: "group"}
CONTACT_TYPE = {-1: "mobile", -2: "phone", -3: "fax", -4: "email", -5: "web"}
PAYMENT_METHOD = {"HOT": "cash", "PLATK": "card", "PREV": "transfer"}
SALE_DOCUMENT_TYPES = ("UM", "PODP", "FAV", "VRAT")


def map_classification(value) -> Optional[str]:
    value = to_int(value)
    if value is None:
        return None
    return CLASSIFICATION.get(value, "other")


def map_owner_kind(value) -> Optional[str]:
    value = to_int(value)
    return None if value is None else OWNER_KIND.get(value)


def map_contact_type(value) -> Optional[str]:
    value = to_int(value)
    if value is None:
        return None
    return CONTACT_TYPE.get(value, "other")


def map_payment_method(value) -> Optional[str]:
    value = norm_value(value)
    if value is None:
        return None
    return PAYMENT_METHOD.get(value.upper(), value.lower())


# --------------------------------------------------------------------------- row mappers


def _users(r: dict) -> dict:
    return {
        "id": to_int(r["ID_UZIVATEL"]),
        "name": norm_value(r["UZIVATEL_NAZEV"]),
        "code": norm_value(r["ZKRATKA"]),
        "active": flag_equals(r["AKTIVNI"], "A"),
    }


def _items(r: dict) -> dict:
    return {
        "id": to_int(r["ID_VARIANTA"]),
        "code": norm_value(r["VARIANTA"]),
        "name": norm_value(r["VARIANTA_NAZEV"]),
        "classification": map_classification(r["ID_KLASIFIKACE_VYROBKU"]),
        "stock_tracked": flag_equals(r["USE_SKLAD"], "A"),
        "tracked_drug": flag_equals(r["SLEDOVANE_LECIVO"], "A"),
        "unit": norm_value(r["MERNA_JEDNOTKA_VY"]),
        "barcode": norm_value(r["CAROVY_KOD"]),
        "active": flag_not_equals(r["AKTIVNI"], "N"),
    }


def _owners(r: dict) -> dict:
    return {
        "id": to_int(r["ID_PARTNER"]),
        "kind": map_owner_kind(r["ID_TRIDA_PARTNERA"]),
        "name": norm_value(r["PARTNER_NAZEV"]),
        "first_name": norm_value(r["JMENO"]),
        "last_name": norm_value(r["PRIJMENI"]),
        "title": norm_value(r["TITUL"]),
        "street": norm_value(r["ULICE"]),
        "zip": norm_value(r["PSC"]),
        "city": norm_value(r["OBEC"]),
        "country": norm_value(r["STAT_NAZEV"]),
        "company_reg": norm_value(r["IDENTIFIKATOR"]),
        "vat": norm_value(r["DIC"]),
        "note": norm_value(r["POZNAMKA"]),
        "important_note": flag_equals(r["POZNAMKA_DULEZITE"], "A"),
        "active": flag_not_equals(r["AKTIVNI"], "N"),
        "created": norm_value(r["ZALOZENI_ZAZNAMU"]),
        "modified": combine_datetime(r["POSLEDNI_MODIFIKACE"], r["CAS"]),
    }


def _contacts(r: dict) -> dict:
    return {
        "id": to_int(r["ID_PARTNER_KONTAKT"]),
        "owner_id": to_ref(r["ID_PARTNER"]),
        "type": map_contact_type(r["ID_TYP_KONTAKTU"]),
        "value": norm_value(r["PARTNER_KONTAKT"]),
        "label": norm_value(r["PARTNER_KONTAKT_NAZEV"]),
    }


def _patients(r: dict) -> dict:
    return {
        "id": to_int(r["ID_PACIENT"]),
        "owner_id": to_ref(r["ID_PARTNER"]),
        "name": norm_value(r["PACIENT_NAZEV"]),
        "species": norm_value(r["DRUH"]),
        "breed": norm_value(r["RASA"]),
        "sex": norm_value(r["POHLAVI"]),
        "color": norm_value(r["BARVA"]),
        "birth_date": norm_value(r["DATUM_NAROZENI"]),
        "birth_year": to_int(r["ROK_NAROZENI"]),
        "chip": norm_value(r["KOD_RID"]),
        "tattoo": norm_value(r["KOD_TETOVACI"]),
        "passport": norm_value(r["CISLO_PASU"]),
        "weight": to_float(r["HMOTNOST"]),
        "deceased": flag_equals(r["UHYN"], "A"),
        "death_date": norm_value(r["EUTHANAZIE_DATUM"]),
        "active": flag_not_equals(r["AKTIVNI"], "N"),
        "registered": norm_value(r["DATUM_REGISTRACE"]),
        "next_vaccination": norm_value(r["PRISTI_VAKCINACE"]),
        "next_deworming": norm_value(r["PRISTI_ODCERVENI"]),
        "important": norm_value(r["DULEZITE"]),
        "note": norm_value(r["POZNAMKA"]),
        "created": norm_value(r["ZALOZENI_ZAZNAMU"]),
        "modified": combine_datetime(r["POSLEDNI_MODIFIKACE"], r["CAS"]),
    }


def _vaccinations(r: dict) -> dict:
    return {
        "id": to_int(r["ID_VAKCINACE_ODCERVENI"]),
        "patient_id": to_ref(r["ID_PACIENT"]),
        "date": norm_value(r["DATUM"]),
        "next_date": norm_value(r["DATUM_PRISTI"]),
        "item_id": to_ref(r["ID_VARIANTA"]),
        "item_name": norm_value(r["VARIANTA_NAZEV"]),
        "quantity": to_float(r["MNOZSTVI"]),
        "unit": norm_value(r["MERNA_JEDNOTKA"]),
        "kind": to_int(r["TYP"]),
    }


def _visits(r: dict) -> dict:
    return {
        "id": to_int(r["ID_DENNI_ZAZNAM"]),
        "patient_id": to_ref(r["ID_PACIENT"]),
        "date": norm_value(r["DATUM"]),
        "time": norm_value(r["CAS"]),
        "case_name": norm_value(r["PRIPAD"]),
        "diagnosis_code": norm_value(r["DIAGNOZA"]),
        "diagnosis_name": norm_value(r["DIAGNOZA_NAZEV"]),
        "entered_by": to_ref(r["ID_ZALOZIL"]),
        "document_id": to_ref(r["ID_DOKLAD"]),
    }


def _sale_documents(r: dict) -> dict:
    return {
        "id": to_int(r["ID_DOKLAD"]),
        "type": norm_value(r["TYP_DOKLADU"]),
        "number": norm_value(r["DOKLAD"]),
        "parent_id": to_ref(r["ID_PREDEK"]),
        "owner_id": to_ref(r["ID_PARTNER"]),
        "date": norm_value(r["DATUM_DOKLADU"]),
        "total": to_float(r["CENA"]),
        "paid": to_float(r["ZAPLACENO"]),
        "from_deposit": to_float(r["ZE_ZALOHY"]),
        "state": norm_value(r["TABLE_STATUS"]),
        "entered_by": to_ref(r["ID_ZALOZIL"]),
    }


def _sale_lines(r: dict) -> dict:
    return {
        "id": to_int(r["ID_DOKLAD_POLOZKA"]),
        "document_id": to_ref(r["ID_DOKLAD"]),
        "visit_id": to_ref(r["ID_DENNI_ZAZNAM"]),
        "item_id": to_ref(r["ID_VARIANTA"]),
        "item_code": norm_value(r["VARIANTA"]),
        "item_name": norm_value(r["VARIANTA_NAZEV"]),
        "quantity": to_float(r["MNOZSTVI"]),
        "unit": norm_value(r["MERNA_JEDNOTKA"]),
        "unit_price": to_float(r["CENA_MJ"]),
        "amount": to_float(r["CENA"]),
        "vat_rate": to_float(r["SAZBA_DPH"]),
        "date": norm_value(r["LINE_DATE"]),
        "entered_by": to_ref(r["ID_ZALOZIL"]),
    }


def _payments(r: dict) -> dict:
    return {
        "id": to_int(r["ID_PLATBA"]),
        "document_id": to_ref(r["ID_DOKLAD"]),
        "owner_id": to_ref(r["ID_PARTNER"]),
        "date": norm_value(r["DATUM"]),
        "time": norm_value(r["CAS"]),
        "method": map_payment_method(r["FORMA_UHRADY"]),
        "amount": to_float(r["ZAPLACENO"]),
        "from_deposit": to_float(r["ZE_ZALOHY"]),
        "state": norm_value(r["TABLE_STATUS"]),
        "refunded_date": norm_value(r["DATUM_VRACENO"]),
    }


# --------------------------------------------------------------------------- specs


@dataclass(frozen=True)
class EntitySpec:
    name: str
    group: str
    tables: Tuple[str, ...]
    sql: str  # SELECT ... FROM ... (no WHERE)
    id_expr: str
    mapper: Callable[[dict], dict]
    keys: Tuple[str, ...]
    where: Optional[str] = None


_TYPES_IN = ", ".join(f"'{t}'" for t in SALE_DOCUMENT_TYPES)

SPECS: Dict[str, EntitySpec] = {}


def _spec(**kwargs) -> None:
    spec = EntitySpec(**kwargs)
    SPECS[spec.name] = spec


_spec(
    name="users",
    group="catalog",
    tables=("UZIVATEL_NEW",),
    sql="select u.ID_UZIVATEL, u.UZIVATEL_NAZEV, u.ZKRATKA, u.AKTIVNI from UZIVATEL_NEW u",
    id_expr="u.ID_UZIVATEL",
    mapper=_users,
    keys=("id", "name", "code", "active"),
)
_spec(
    name="items",
    group="catalog",
    tables=("VARIANTA",),
    sql=(
        "select v.ID_VARIANTA, v.VARIANTA, v.VARIANTA_NAZEV, v.ID_KLASIFIKACE_VYROBKU, v.USE_SKLAD, "
        "v.SLEDOVANE_LECIVO, v.MERNA_JEDNOTKA_VY, v.CAROVY_KOD, v.AKTIVNI from VARIANTA v"
    ),
    id_expr="v.ID_VARIANTA",
    mapper=_items,
    keys=("id", "code", "name", "classification", "stock_tracked", "tracked_drug", "unit", "barcode", "active"),
)
_spec(
    name="owners",
    group="owners",
    tables=("PARTNER",),
    sql=(
        "select p.ID_PARTNER, p.ID_TRIDA_PARTNERA, p.PARTNER_NAZEV, p.JMENO, p.PRIJMENI, p.TITUL, "
        "p.ULICE, p.PSC, p.OBEC, p.STAT_NAZEV, p.IDENTIFIKATOR, p.DIC, p.POZNAMKA, p.POZNAMKA_DULEZITE, "
        "p.AKTIVNI, p.ZALOZENI_ZAZNAMU, p.POSLEDNI_MODIFIKACE, p.CAS from PARTNER p"
    ),
    id_expr="p.ID_PARTNER",
    mapper=_owners,
    keys=(
        "id", "kind", "name", "first_name", "last_name", "title", "street", "zip", "city", "country",
        "company_reg", "vat", "note", "important_note", "active", "created", "modified",
    ),
)
_spec(
    name="contacts",
    group="owners",
    tables=("PARTNER_KONTAKT",),
    sql=(
        "select k.ID_PARTNER_KONTAKT, k.ID_PARTNER, k.ID_TYP_KONTAKTU, k.PARTNER_KONTAKT, "
        "k.PARTNER_KONTAKT_NAZEV from PARTNER_KONTAKT k"
    ),
    id_expr="k.ID_PARTNER_KONTAKT",
    mapper=_contacts,
    keys=("id", "owner_id", "type", "value", "label"),
)
_spec(
    name="patients",
    group="patients",
    tables=("PACIENT",),
    sql=(
        "select a.ID_PACIENT, a.ID_PARTNER, a.PACIENT_NAZEV, a.DRUH, a.RASA, a.POHLAVI, a.BARVA, "
        "a.DATUM_NAROZENI, a.ROK_NAROZENI, a.KOD_RID, a.KOD_TETOVACI, a.CISLO_PASU, a.HMOTNOST, a.UHYN, "
        "a.EUTHANAZIE_DATUM, a.AKTIVNI, a.DATUM_REGISTRACE, a.PRISTI_VAKCINACE, a.PRISTI_ODCERVENI, "
        "a.DULEZITE, a.POZNAMKA, a.ZALOZENI_ZAZNAMU, a.POSLEDNI_MODIFIKACE, a.CAS from PACIENT a"
    ),
    id_expr="a.ID_PACIENT",
    mapper=_patients,
    keys=(
        "id", "owner_id", "name", "species", "breed", "sex", "color", "birth_date", "birth_year", "chip",
        "tattoo", "passport", "weight", "deceased", "death_date", "active", "registered",
        "next_vaccination", "next_deworming", "important", "note", "created", "modified",
    ),
)
_spec(
    name="vaccinations",
    group="patients",
    tables=("VAKCINACE_ODCERVENI",),
    sql=(
        "select o.ID_VAKCINACE_ODCERVENI, o.ID_PACIENT, o.DATUM, o.DATUM_PRISTI, o.ID_VARIANTA, "
        "o.VARIANTA_NAZEV, o.MNOZSTVI, o.MERNA_JEDNOTKA, o.TYP from VAKCINACE_ODCERVENI o"
    ),
    id_expr="o.ID_VAKCINACE_ODCERVENI",
    mapper=_vaccinations,
    keys=("id", "patient_id", "date", "next_date", "item_id", "item_name", "quantity", "unit", "kind"),
)
_spec(
    name="visits",
    group="clinical",
    tables=("DENNI_ZAZNAM",),
    sql=(
        "select z.ID_DENNI_ZAZNAM, z.ID_PACIENT, z.DATUM, z.CAS, z.PRIPAD, z.DIAGNOZA, z.DIAGNOZA_NAZEV, "
        "z.ID_ZALOZIL, z.ID_DOKLAD from DENNI_ZAZNAM z"
    ),
    id_expr="z.ID_DENNI_ZAZNAM",
    mapper=_visits,
    keys=(
        "id", "patient_id", "date", "time", "case_name", "diagnosis_code", "diagnosis_name",
        "entered_by", "document_id",
    ),
)
_spec(
    name="sale_documents",
    group="sales",
    tables=("DOKLAD",),
    sql=(
        "select d.ID_DOKLAD, d.TYP_DOKLADU, d.DOKLAD, d.ID_PREDEK, d.ID_PARTNER, d.DATUM_DOKLADU, d.CENA, "
        "d.ZAPLACENO, d.ZE_ZALOHY, d.TABLE_STATUS, d.ID_ZALOZIL from DOKLAD d"
    ),
    where=f"trim(d.TYP_DOKLADU) in ({_TYPES_IN})",
    id_expr="d.ID_DOKLAD",
    mapper=_sale_documents,
    keys=(
        "id", "type", "number", "parent_id", "owner_id", "date", "total", "paid", "from_deposit", "state",
        "entered_by",
    ),
)
_spec(
    name="sale_lines",
    group="sales",
    tables=("DOKLAD_POLOZKA_UM", "DOKLAD", "DENNI_ZAZNAM"),
    sql=(
        "select l.ID_DOKLAD_POLOZKA, l.ID_DOKLAD, l.ID_DENNI_ZAZNAM, l.ID_VARIANTA, l.VARIANTA, "
        "l.VARIANTA_NAZEV, l.MNOZSTVI, l.MERNA_JEDNOTKA, l.CENA_MJ, l.CENA, l.SAZBA_DPH, l.ID_ZALOZIL, "
        "coalesce(z.DATUM, d.DATUM_DOKLADU) as LINE_DATE "
        "from DOKLAD_POLOZKA_UM l "
        "left join DENNI_ZAZNAM z on z.ID_DENNI_ZAZNAM = l.ID_DENNI_ZAZNAM "
        "left join DOKLAD d on d.ID_DOKLAD = l.ID_DOKLAD"
    ),
    id_expr="l.ID_DOKLAD_POLOZKA",
    mapper=_sale_lines,
    keys=(
        "id", "document_id", "visit_id", "item_id", "item_code", "item_name", "quantity", "unit",
        "unit_price", "amount", "vat_rate", "date", "entered_by",
    ),
)
_spec(
    name="payments",
    group="sales",
    tables=("PLATBA",),
    sql=(
        "select p.ID_PLATBA, p.ID_DOKLAD, p.ID_PARTNER, p.DATUM, p.CAS, p.FORMA_UHRADY, p.ZAPLACENO, "
        "p.ZE_ZALOHY, p.TABLE_STATUS, p.DATUM_VRACENO from PLATBA p"
    ),
    id_expr="p.ID_PLATBA",
    mapper=_payments,
    keys=(
        "id", "document_id", "owner_id", "date", "time", "method", "amount", "from_deposit", "state",
        "refunded_date",
    ),
)

assert tuple(SPECS) == ENTITY_ORDER

#: entity -> tables it reads (input of the guard's dependency rule)
ENTITY_TABLES: Dict[str, Tuple[str, ...]] = {name: spec.tables for name, spec in SPECS.items()}


def build_sql(spec: EntitySpec, id_count: int = 0) -> str:
    conditions = []
    if spec.where:
        conditions.append(f"({spec.where})")
    if id_count:
        conditions.append(f"{spec.id_expr} in ({', '.join('?' * id_count)})")
    sql = spec.sql
    if conditions:
        sql += " where " + " and ".join(conditions)
    return sql + f" order by {spec.id_expr}"


def _chunks(seq: Sequence[int], size: int) -> Iterable[Sequence[int]]:
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


class EntityReader:
    """Reads one entity; ``db`` is a :class:`winvet_bridge.db.ReadOnlyDatabase`."""

    def __init__(self, spec: EntitySpec, db, chunk_size: int = 500):
        self.spec = spec
        self.db = db
        self.chunk_size = chunk_size

    @property
    def name(self) -> str:
        return self.spec.name

    def read_all(self) -> List[dict]:
        with self.db.transaction() as tx:
            return [self.spec.mapper(r) for r in tx.query_dicts(build_sql(self.spec), (), self.chunk_size)]

    def read_ids(self, ids: Iterable[int]) -> List[dict]:
        wanted = sorted({int(i) for i in ids})
        out: List[dict] = []
        if not wanted:
            return out
        with self.db.transaction() as tx:
            for part in _chunks(wanted, ID_CHUNK):
                sql = build_sql(self.spec, len(part))
                out.extend(self.spec.mapper(r) for r in tx.query_dicts(sql, part, self.chunk_size))
        return out


def get_reader(entity: str, db, chunk_size: int = 500) -> EntityReader:
    if entity not in SPECS:
        raise KeyError(f"Unknown entity {entity!r}; known: {', '.join(SPECS)}")
    return EntityReader(SPECS[entity], db, chunk_size)


def all_readers(db, chunk_size: int = 500) -> Dict[str, EntityReader]:
    return {name: EntityReader(spec, db, chunk_size) for name, spec in SPECS.items()}


# --------------------------------------------------------------------------- used columns

_ALIAS_RE = re.compile(r"\b(?:from|join)\s+([A-Z_][A-Z0-9_$]*)\s+([a-z][a-z0-9_]*)\b", re.IGNORECASE)
_COLUMN_RE = re.compile(r"\b([a-z][a-z0-9_]*)\.([A-Z_][A-Z0-9_$]*)\b")


def used_columns(specs: Mapping[str, EntitySpec] = None) -> Dict[str, Set[str]]:
    """table -> columns the readers actually select/join/filter on (derived from the SQL).

    The schema guard fingerprints only these columns, so a new column or a change of an unused
    column in WinVet does not block synchronisation.
    """
    out: Dict[str, Set[str]] = {}
    for spec in (specs or SPECS).values():
        text = " ".join(x for x in (spec.sql, spec.id_expr, spec.where or "") if x)
        aliases = {alias.lower(): table.upper() for table, alias in _ALIAS_RE.findall(spec.sql)}
        for table in spec.tables:
            out.setdefault(table.upper(), set())
        for alias, column in _COLUMN_RE.findall(text):
            table = aliases.get(alias.lower())
            if table is None:
                raise ValueError(f"Unknown alias {alias!r} in SQL of entity {spec.name}")
            out.setdefault(table, set()).add(column.upper())
    return out
