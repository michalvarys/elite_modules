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
items           catalog   VARIANTA, VARIANTA_CENIK (price list 1)
owners          owners    PARTNER
contacts        owners    PARTNER_KONTAKT
patients        patients  PACIENT
vaccinations    patients  VAKCINACE_ODCERVENI
visits          clinical  DENNI_ZAZNAM (incl. DEKURS -> notes, see :mod:`winvet_bridge.rvf`)
vitals          clinical  DENNI_ZAZNAM_HODNOTA
sale_documents  sales     DOKLAD
sale_lines      sales     DOKLAD_POLOZKA_UM, DOKLAD (sales), DENNI_ZAZNAM (clinical)
payments        sales     PLATBA
bundles         templates SABLONA_VYKONU
bundle_lines    templates SABLONA_VYKONU_POLOZKA
phrases         templates FRAZE
stock_lots      stock     DOKLAD_POLOZKA_SK (receipt lines, minus issues), DOKLAD (sales, supplier/date)
stock_totals    stock     VARIANTA_SKLAD_STAV
calendar_*      calendar  KALENDAR_NEW_KALENDAR, ORD_CINNOST, KALENDAR_NEW (window read, see
                          :mod:`winvet_bridge.scheduler`)
=============== ========= ==========================================

Foreign keys (``*_id``, ``entered_by``) with WinVet's "no reference" values 0 / negative are sent as
``null``.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import ENTITY_ORDER
from .normalize import (
    read_blob,
    combine_datetime,
    flag_equals,
    flag_not_equals,
    norm_value,
    to_float,
    to_int,
    to_ref,
)
from .rvf import rvf_or_plain, rvf_to_text
from .scheduler import EventBuilder, Window, delphi_color, make_window

log = logging.getLogger(__name__)

ID_CHUNK = 250  # ids per "IN (...)" (Firebird allows at most 1500 list elements)

CLASSIFICATION = {0: "group", 1: "product", 2: "set", 3: "kit", 4: "service", 5: "operation", 6: "alias"}
OWNER_KIND = {0: "company", 1: "person", 2: "group"}
CONTACT_TYPE = {-1: "mobile", -2: "phone", -3: "fax", -4: "email", -5: "web"}
PAYMENT_METHOD = {"HOT": "cash", "PLATK": "card", "PREV": "transfer"}
#: VARIANTA_CENIK.ID_CENIK of the price list whose prices are sent with items ("Ordinace").
ITEM_PRICE_LIST = 1
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
        "price": to_float(r["PRICE"]),
        "price_untaxed": to_float(r["PRICE_UNTAXED"]),
        "vat_rate": to_float(r["DPH_PRODEJ"]),
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
        "notes": rvf_to_text(r["DEKURS"]),
    }


def _vitals(r: dict) -> dict:
    return {
        "id": to_int(r["ID_DENNI_ZAZNAM_HODNOTA"]),
        "visit_id": to_ref(r["ID_DENNI_ZAZNAM"]),
        "time": norm_value(r["CAS"]),
        "temperature": to_float(r["TEPLOTA"]),
        "heart_rate": to_int(r["TEP"]),
        "respiratory_rate": to_int(r["DECH"]),
        "weight": to_float(r["HMOTNOST"]),
        "bp_systolic": to_int(r["TLAK_SYS"]),
        "bp_diastolic": to_int(r["TLAK_DIA"]),
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


def _bundles(r: dict) -> dict:
    return {
        "id": to_int(r["ID_SABLONA_VYKONU"]),
        "code": norm_value(r["SABLONA_VYKONU"]),
        "name": norm_value(r["SABLONA_VYKONU_NAZEV"]),
        "description": rvf_or_plain(r["POPIS"]),
    }


def _bundle_lines(r: dict) -> dict:
    return {
        "id": to_int(r["ID_SABLONA_VYKONU_POLOZKA"]),
        "bundle_id": to_ref(r["ID_SABLONA_VYKONU"]),
        "item_id": to_ref(r["ID_VARIANTA"]),
        "item_name": norm_value(r["VARIANTA_NAZEV"]),
        "quantity": to_float(r["MNOZSTVI"]),
        "unit": norm_value(r["MERNA_JEDNOTKA"]),
        "sequence": to_int(r["PORADI"]),
    }


def _phrases(r: dict) -> dict:
    return {
        "id": to_int(r["ID_FRAZE"]),
        "name": norm_value(r["FRAZE"]),
        "group": norm_value(r["PREDEK"]),
        "text": rvf_or_plain(r["TEXT"]),
    }


def _stock_lots(r: dict) -> dict:
    return {
        "id": to_int(r["ID_DOKLAD_POLOZKA"]),
        "item_id": to_ref(r["ID_VARIANTA"]),
        "lot": norm_value(r["VYROBNI_CISLO"]),
        "expiry": norm_value(r["DATUM_EXPIRACE"]),
        "received": norm_value(r["RECEIVED"]),
        "quantity": to_float(r["QUANTITY"]),
        "unit_cost": to_float(r["CENA_MJ"]),
        "vat_rate": to_float(r["SAZBA_DPH"]),
        "cost_includes_vat": flag_equals(r["S_DPH"], "A"),
        "supplier": norm_value(r["PARTNER_NAZEV"]),
    }


def _stock_totals(r: dict) -> dict:
    return {
        "id": to_int(r["ID_VARIANTA_SKLAD_STAV"]),
        "item_id": to_ref(r["ID_VARIANTA"]),
        "total": to_float(r["STAV_CELKEM"]),
    }


def _calendar_resources(r: dict) -> dict:
    return {
        "id": to_int(r["ID_KALENDAR_NEW_KALENDAR"]),
        "name": norm_value(r["KALENDAR_NAZEV"]),
        "color": delphi_color(r["BARVA"]),
        "visible": flag_equals(r["ZOBRAZIT"], "A"),
        "work_from": norm_value(r["PRACOVNI_DOBA_OD"]),
        "work_to": norm_value(r["PRACOVNI_DOBA_DO"]),
        "sequence": to_int(r["PORADI"]),
    }


def _calendar_activities(r: dict) -> dict:
    return {
        "id": to_int(r["ID_ORD_CINNOST"]),
        "name": norm_value(r["ORD_CINNOST_NAZEV"]),
        "duration": to_int(r["DOBA"]),
        "color": delphi_color(r["BARVA"]),
        "symbol": norm_value(r["SYMBOL"]),
        "web": flag_equals(r["USE_WEB"], "A"),
    }


def _calendar_events(r: dict) -> dict:  # pragma: no cover - rows go through EventBuilder
    raise NotImplementedError("calendar_events are built by CalendarEventReader")


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
    tables=("VARIANTA", "VARIANTA_CENIK"),
    # price: the first row (lowest ID_VARIANTA_CENIK) of price list ITEM_PRICE_LIST - one row per stock
    sql=(
        "select v.ID_VARIANTA, v.VARIANTA, v.VARIANTA_NAZEV, v.ID_KLASIFIKACE_VYROBKU, v.USE_SKLAD, "
        "v.SLEDOVANE_LECIVO, v.MERNA_JEDNOTKA_VY, v.CAROVY_KOD, v.AKTIVNI, v.DPH_PRODEJ, "
        "c.CENA_S_DPH as PRICE, c.CENA as PRICE_UNTAXED "
        "from VARIANTA v "
        "left join VARIANTA_CENIK c on c.ID_VARIANTA_CENIK = ("
        "select min(c1.ID_VARIANTA_CENIK) from VARIANTA_CENIK c1 "
        f"where c1.ID_VARIANTA = v.ID_VARIANTA and c1.ID_CENIK = {ITEM_PRICE_LIST})"
    ),
    id_expr="v.ID_VARIANTA",
    mapper=_items,
    keys=(
        "id", "code", "name", "classification", "stock_tracked", "tracked_drug", "unit", "barcode", "active",
        "price", "price_untaxed", "vat_rate",
    ),
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
        "z.ID_ZALOZIL, z.ID_DOKLAD, z.DEKURS from DENNI_ZAZNAM z"
    ),
    id_expr="z.ID_DENNI_ZAZNAM",
    mapper=_visits,
    keys=(
        "id", "patient_id", "date", "time", "case_name", "diagnosis_code", "diagnosis_name",
        "entered_by", "document_id", "notes",
    ),
)
_spec(
    name="vitals",
    group="clinical",
    tables=("DENNI_ZAZNAM_HODNOTA",),
    sql=(
        "select h.ID_DENNI_ZAZNAM_HODNOTA, h.ID_DENNI_ZAZNAM, h.CAS, h.TEPLOTA, h.TEP, h.DECH, h.HMOTNOST, "
        "h.TLAK_SYS, h.TLAK_DIA from DENNI_ZAZNAM_HODNOTA h"
    ),
    id_expr="h.ID_DENNI_ZAZNAM_HODNOTA",
    mapper=_vitals,
    keys=(
        "id", "visit_id", "time", "temperature", "heart_rate", "respiratory_rate", "weight", "bp_systolic",
        "bp_diastolic",
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
_spec(
    name="bundles",
    group="templates",
    tables=("SABLONA_VYKONU",),
    sql=(
        "select s.ID_SABLONA_VYKONU, s.SABLONA_VYKONU, s.SABLONA_VYKONU_NAZEV, s.POPIS "
        "from SABLONA_VYKONU s"
    ),
    id_expr="s.ID_SABLONA_VYKONU",
    mapper=_bundles,
    keys=("id", "code", "name", "description"),
)
_spec(
    name="bundle_lines",
    group="templates",
    tables=("SABLONA_VYKONU_POLOZKA",),
    sql=(
        "select b.ID_SABLONA_VYKONU_POLOZKA, b.ID_SABLONA_VYKONU, b.ID_VARIANTA, b.VARIANTA_NAZEV, "
        "b.MNOZSTVI, b.MERNA_JEDNOTKA, b.PORADI from SABLONA_VYKONU_POLOZKA b"
    ),
    id_expr="b.ID_SABLONA_VYKONU_POLOZKA",
    mapper=_bundle_lines,
    keys=("id", "bundle_id", "item_id", "item_name", "quantity", "unit", "sequence"),
)
_spec(
    name="phrases",
    group="templates",
    tables=("FRAZE",),
    sql="select f.ID_FRAZE, f.FRAZE, f.PREDEK, f.TEXT from FRAZE f",
    id_expr="f.ID_FRAZE",
    mapper=_phrases,
    keys=("id", "name", "group", "text"),
)
_spec(
    name="stock_lots",
    group="stock",
    tables=("DOKLAD_POLOZKA_SK", "DOKLAD"),
    # receipt lines (ZNAMENKO = 1) of every document type; issued quantity = issue lines (ZNAMENKO = -1)
    # pointing to the receipt line via ID_DOKLAD_POLOZKA_PRIJEM (correlated subquery in the SELECT)
    sql=(
        "select s.ID_DOKLAD_POLOZKA, s.ID_VARIANTA, s.VYROBNI_CISLO, s.DATUM_EXPIRACE, s.CENA_MJ, "
        "s.SAZBA_DPH, s.S_DPH, d.DATUM_DOKLADU as RECEIVED, d.PARTNER_NAZEV, "
        "s.MNOZSTVI - coalesce(("
        "select sum(i.MNOZSTVI) from DOKLAD_POLOZKA_SK i "
        "where i.ZNAMENKO = -1 and i.ID_DOKLAD_POLOZKA_PRIJEM = s.ID_DOKLAD_POLOZKA), 0) as QUANTITY "
        "from DOKLAD_POLOZKA_SK s "
        "left join DOKLAD d on d.ID_DOKLAD = s.ID_DOKLAD"
    ),
    where="s.ZNAMENKO = 1",
    id_expr="s.ID_DOKLAD_POLOZKA",
    mapper=_stock_lots,
    keys=(
        "id", "item_id", "lot", "expiry", "received", "quantity", "unit_cost", "vat_rate",
        "cost_includes_vat", "supplier",
    ),
)
_spec(
    name="stock_totals",
    group="stock",
    tables=("VARIANTA_SKLAD_STAV",),
    sql="select t.ID_VARIANTA_SKLAD_STAV, t.ID_VARIANTA, t.STAV_CELKEM from VARIANTA_SKLAD_STAV t",
    id_expr="t.ID_VARIANTA_SKLAD_STAV",
    mapper=_stock_totals,
    keys=("id", "item_id", "total"),
)

_spec(
    name="calendar_resources",
    group="calendar",
    tables=("KALENDAR_NEW_KALENDAR",),
    sql=(
        "select c.ID_KALENDAR_NEW_KALENDAR, c.KALENDAR_NAZEV, c.BARVA, c.ZOBRAZIT, c.PRACOVNI_DOBA_OD, "
        "c.PRACOVNI_DOBA_DO, c.PORADI from KALENDAR_NEW_KALENDAR c"
    ),
    id_expr="c.ID_KALENDAR_NEW_KALENDAR",
    mapper=_calendar_resources,
    keys=("id", "name", "color", "visible", "work_from", "work_to", "sequence"),
)
_spec(
    name="calendar_activities",
    group="calendar",
    tables=("ORD_CINNOST",),
    sql=(
        "select o.ID_ORD_CINNOST, o.ORD_CINNOST_NAZEV, o.BARVA, o.DOBA, o.SYMBOL, o.USE_WEB "
        "from ORD_CINNOST o"
    ),
    id_expr="o.ID_ORD_CINNOST",
    mapper=_calendar_activities,
    keys=("id", "name", "duration", "color", "symbol", "web"),
)
_spec(
    name="calendar_events",
    group="calendar",
    # The reader also reads the resource names with the calendar_resources SQL (an event may store
    # the name instead of the id); that table is in the same fingerprint group "calendar".
    tables=("KALENDAR_NEW",),
    # TITULEK = title (client names: personal data), ZPRAVA (notes) is never read.
    sql=(
        "select k.ID_KALENDAR, k.ID_PREDEK, k.TYP, k.ZACATEK, k.KONEC, k.VOLBY, k.TITULEK, "
        "k.OPAKOVANI_INDEX, k.OPAKOVANI_INFO, k.ZDROJ_INFO, k.STAV, k.ID_PARTNER, k.ID_PACIENT, "
        "k.ID_ORD_CINNOST, k.VYRIZENO, k.POSLEDNI_MODIFIKACE, k.POSLEDNI_MODIFIKACE_TS "
        "from KALENDAR_NEW k"
    ),
    # every recurrence row (patterns and their exceptions are few) + plain events near the window;
    # the parameters are the window end and start with one day of margin (all-day storage at 23:00)
    where="coalesce(k.TYP, 0) <> 0 or (k.ZACATEK < ? and k.KONEC > ?)",
    id_expr="k.ID_KALENDAR",
    mapper=_calendar_events,
    keys=(
        "key", "id", "pattern_id", "recurring", "occurrence_date", "start", "end", "all_day", "resource_ids",
        "activity_id", "owner_id", "patient_id", "title", "busy_status", "done", "modified",
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


class CalendarEventReader(EntityReader):
    """``calendar_events``: the occurrences of one window (recurrences expanded), contract v4.

    One read-only transaction reads the resource names and the KALENDAR_NEW rows;
    :class:`winvet_bridge.scheduler.EventBuilder` does the rest in memory. ``window`` of the last
    read is pushed with every batch so Odoo can remove events that disappeared from WinVet.
    """

    def __init__(self, spec: EntitySpec, db, chunk_size: int = 500, days_back: int = 1, days_ahead: int = 60,
                 today: Optional[Callable[[], _dt.date]] = None):
        super().__init__(spec, db, chunk_size)
        self.days_back, self.days_ahead = days_back, days_ahead
        self._today = today
        self.window: Optional[Window] = None
        self.problems: Dict[str, int] = {}

    def current_window(self) -> Window:
        today = self._today() if self._today else _dt.date.today()
        return make_window(today, self.days_back, self.days_ahead)

    def read_all(self) -> List[dict]:
        window = self.current_window()
        margin = _dt.timedelta(days=1)
        names_spec = SPECS["calendar_resources"]
        sql = build_sql(self.spec)
        with self.db.transaction() as tx:
            names = {}
            for r in tx.query_dicts(build_sql(names_spec), (), self.chunk_size):
                name = norm_value(r["KALENDAR_NAZEV"])
                if name:
                    names.setdefault(name.lower(), to_int(r["ID_KALENDAR_NEW_KALENDAR"]))
            rows = []
            for r in tx.query_dicts(sql, (window.end_dt + margin, window.start_dt - margin), self.chunk_size):
                # BLOBs must be read before the next fetch
                rows.append({k: (read_blob(v) if k in ("OPAKOVANI_INFO", "ZDROJ_INFO") else v) for k, v in r.items()})
        builder = EventBuilder(window, names)
        records = builder.build(rows)
        self.window, self.problems = window, builder.problems
        if builder.problems:  # counts only, never record data
            log.warning("calendar_events: %s", ", ".join(f"{k} x{v}" for k, v in sorted(builder.problems.items())))
        return records

    def read_ids(self, ids: Iterable[int]) -> List[dict]:
        raise NotImplementedError("calendar_events are always read for the whole window")


def _reader(spec: EntitySpec, db, chunk_size: int, calendar: Optional[Mapping] = None) -> EntityReader:
    if spec.name == "calendar_events":
        return CalendarEventReader(spec, db, chunk_size, **(calendar or {}))
    return EntityReader(spec, db, chunk_size)


def get_reader(entity: str, db, chunk_size: int = 500, calendar: Optional[Mapping] = None) -> EntityReader:
    if entity not in SPECS:
        raise KeyError(f"Unknown entity {entity!r}; known: {', '.join(SPECS)}")
    return _reader(SPECS[entity], db, chunk_size, calendar)


def all_readers(db, chunk_size: int = 500, calendar: Optional[Mapping] = None) -> Dict[str, EntityReader]:
    """``calendar``: keyword arguments of :class:`CalendarEventReader` (days_back, days_ahead)."""
    return {name: _reader(spec, db, chunk_size, calendar) for name, spec in SPECS.items()}


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
