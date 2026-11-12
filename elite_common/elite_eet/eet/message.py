"""Building of the EET 2.0 "Trzba" message (XSD 4.1)."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lxml import etree

from . import fields, paths

NS_V4 = "http://fs.gov.cz/eet/schema/v4"

_schema = None


class MessageError(Exception):
    """The message cannot be built or sent as it is (local, never retried)."""


@dataclass
class SaleData:
    eic_popl: str
    id_jednotky: str
    id_pokl: str
    porad_cis: str
    dat_trzby: datetime
    celk_trzba: Decimal | float
    urceno_cerp_zuct: Decimal | float | None = None
    cerp_zuct: Decimal | float | None = None


def _get_schema():
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(file=paths.SCHEMA_XSD)
    return _schema


def _bool(value):
    return "true" if value else "false"


def build_trzba(data, uuid, sent_at, first, verification):
    """Return a validated v4:Trzba element for one sale."""
    try:
        trzba = etree.Element(f"{{{NS_V4}}}Trzba", nsmap={"v4": NS_V4})
        head = etree.SubElement(trzba, f"{{{NS_V4}}}Hlavicka")
        head.set("uuid_zpravy", uuid)
        head.set("dat_odesl", fields.format_datetime(sent_at))
        head.set("prvni_zaslani", _bool(first))
        head.set("overeni", _bool(verification))
        body = etree.SubElement(trzba, f"{{{NS_V4}}}Data")
        body.set("eic_popl", data.eic_popl or "")
        body.set("id_jednotky", str(data.id_jednotky or ""))
        body.set("id_pokl", data.id_pokl or "")
        body.set("porad_cis", data.porad_cis or "")
        body.set("dat_trzby", fields.format_datetime(data.dat_trzby))
        body.set("celk_trzba", fields.format_amount(data.celk_trzba))
        for name in ("urceno_cerp_zuct", "cerp_zuct"):
            value = getattr(data, name)
            if value:
                body.set(name, fields.format_amount(value))
    except ValueError as e:
        raise MessageError(str(e)) from None
    schema = _get_schema()
    if not schema.validate(trzba):
        raise MessageError("Zpráva neodpovídá schématu EET: %s" % schema.error_log.last_error)
    return trzba
