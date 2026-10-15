"""Conversion of raw Firebird values to the JSON types required by the contract."""

from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal
from typing import Any, Optional

def format_date(value: _dt.date) -> str:
    # not strftime: "%Y" is not zero-padded for years < 1000 on every platform (WinVet has typos
    # such as year 218); the contract wants exactly YYYY-MM-DD.
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"


def format_time(value: _dt.time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"


def format_datetime(value: _dt.datetime) -> str:
    return format_date(value) + " " + format_time(value)


def read_blob(value: Any) -> Any:
    """Materialise a streamed BLOB (``BlobReader``) into ``str``/``bytes``.

    Small BLOBs are returned by firebird-driver directly as ``str`` (text) or ``bytes``; large ones
    as a reader object with ``read()`` that must be consumed before the next fetch.
    """
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return value
    read = getattr(value, "read", None)
    if callable(read):
        try:
            return read()
        finally:
            close = getattr(value, "close", None)
            if callable(close):
                close()
    return value


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def norm_value(value: Any) -> Any:
    """Normalise one value: trimmed str or None, ISO date/time strings, float for numbers."""
    value = read_blob(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (bytes, bytearray)):
        # Text BLOBs are transliterated by the driver; raw bytes only appear for BLOBs without
        # a character set. WinVet text is WIN1250.
        value = bytes(value).decode("cp1250", errors="replace")
    if isinstance(value, str):
        # WinVet text sometimes contains NUL / control characters (PostgreSQL rejects NUL).
        value = _CONTROL_CHARS.sub("", value).strip()
        return value or None
    if isinstance(value, _dt.datetime):
        return format_datetime(value)
    if isinstance(value, _dt.date):
        return format_date(value)
    if isinstance(value, _dt.time):
        return format_time(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    return value


def to_float(value: Any) -> Optional[float]:
    value = norm_value(value)
    if value is None:
        return None
    return float(value)


def to_int(value: Any) -> Optional[int]:
    value = norm_value(value)
    if value is None:
        return None
    return int(value)


def flag_equals(value: Any, expected: str = "A") -> bool:
    """``COLUMN = 'A'`` semantics: True only when the trimmed value equals ``expected``."""
    value = norm_value(value)
    return value is not None and str(value).upper() == expected


def flag_not_equals(value: Any, rejected: str = "N") -> bool:
    """``COLUMN <> 'N'`` semantics with NULL treated as *not* 'N' (i.e. True)."""
    value = norm_value(value)
    return value is None or str(value).upper() != rejected


def combine_datetime(date_value: Any, time_value: Any) -> Optional[str]:
    """Combine a DATE and a TIME column into ``YYYY-MM-DD HH:MM:SS`` (time defaults to 00:00:00)."""
    date_value = read_blob(date_value)
    if date_value is None:
        return None
    if isinstance(date_value, _dt.datetime):
        date_value = date_value.date()
    if isinstance(time_value, _dt.datetime):
        time_value = time_value.time()
    if not isinstance(time_value, _dt.time):
        time_value = _dt.time(0, 0, 0)
    return format_date(date_value) + " " + format_time(time_value)


def to_ref(value: Any) -> Optional[int]:
    """Foreign key: WinVet stores 0 / negative ids as "no reference" -> None."""
    value = to_int(value)
    if value is None or value <= 0:
        return None
    return value
