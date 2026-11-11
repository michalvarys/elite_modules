"""Formatting of EET 2.0 message attributes (patterns from EETXMLSchema.xsd 4.1)."""
import re
import unicodedata
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")

AMOUNT_RE = re.compile(r"((0|-?[1-9]\d{0,7})\.\d\d|-0\.(0[1-9]|[1-9]\d))")
EIC_RE = re.compile(r"CZ[0-9]{8,10}")
ID_JEDNOTKY_RE = re.compile(r"[1-9][0-9]{0,8}")
TEXT20_RE = re.compile(r"[0-9a-zA-Z.,:;/#\-_ ]{1,20}")
TEXT25_RE = re.compile(r"[0-9a-zA-Z.,:;/#\-_ ]{1,25}")

_DISALLOWED = re.compile(r"[^0-9a-zA-Z.,:;/#\-_ ]")
_SPACES = re.compile(r" {2,}")
_MAX_AMOUNT = Decimal("99999999.99")


def format_amount(value):
    """Return the amount with exactly two decimals, never "-0.00"."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(amount) > _MAX_AMOUNT:
        raise ValueError(f"Amount out of EET range: {value}")
    if amount == 0:
        return "0.00"
    return f"{amount:.2f}"


def format_datetime(dt_utc):
    """Convert a naive UTC datetime (Odoo convention) to Prague time with offset."""
    local = dt_utc.replace(tzinfo=timezone.utc, microsecond=0).astimezone(PRAGUE)
    return local.isoformat(timespec="seconds")


def sanitize_text(value, max_len):
    """Reduce text to the characters EET allows, removing diacritics."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = _SPACES.sub(" ", _DISALLOWED.sub("-", ascii_text)).strip()[:max_len].strip()
    if not cleaned:
        raise ValueError(f"Text has no characters allowed by EET: {value!r}")
    return cleaned
