"""GS1 element strings from DataMatrix / GS1-128 scanners (pure functions, no ORM).

Supported forms of the same content:
- raw with FNC1 separators: ``0108595001601961`` ``10A1B2`` ``\\x1d`` ``17270331``
- bracket notation: ``(01)08595001601961(17)270331(10)A1B2``
- either one behind a symbology identifier ``]d2`` (DataMatrix), ``]C1`` (GS1-128), ``]Q3`` (QR).

Read AIs: 01 GTIN, 10 lot, 17 expiry (YYMMDD, day 00 = last day of the month), 21 serial.
Other AIs are skipped; an unknown AI (e.g. 712 NHRN) is skipped up to the next GS separator.
Anything that is not a GS1 string (EAN-13, a supplier code...)
comes back with ``gtin`` None and the code in ``raw``.
"""
import calendar
import re
from datetime import date

GS = "\x1d"
PREFIXES = ("]d2", "]C1", "]Q3")
# AIs with a fixed data length (GS1 general specifications, figure 3.2-1)
FIXED = {"00": 18, "01": 14, "02": 14, "11": 6, "12": 6, "13": 6, "15": 6, "16": 6, "17": 6, "20": 2}
# AIs with variable data (max. length), terminated by FNC1 or the end of the string
VARIABLE = {"10": 20, "21": 20, "22": 20, "30": 8, "37": 8, "240": 30, "241": 30, "250": 30, "251": 30,
            "400": 30, "90": 30, "91": 90, "92": 90, "93": 90, "94": 90, "95": 90, "96": 90, "97": 90,
            "98": 90, "99": 90}
BRACKET_RE = re.compile(r"\((\d{2,4})\)([^(]*)")


def _empty(raw):
    return {"gtin": None, "lot": None, "expiry": None, "serial": None, "raw": raw}


def _expiry(value):
    """YYMMDD -> date; day 00 = last day of the month; invalid -> None."""
    if not re.fullmatch(r"\d{6}", value or ""):
        return None
    year, month, day = 2000 + int(value[:2]), int(value[2:4]), int(value[4:])
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    if day == 0:
        day = last
    if day > last:
        return None
    return date(year, month, day)


def _elements_brackets(body):
    if not body.startswith("("):
        return None
    elements = BRACKET_RE.findall(body)
    if not elements or "".join("(%s)%s" % e for e in elements) != body:
        return None
    return [(ai, value.strip(GS)) for ai, value in elements]


def _elements_raw(body):
    """[(ai, value)] of an FNC1-separated string; None when it does not start like GS1."""
    elements, pos = [], 0
    while pos < len(body):
        if body[pos] == GS:
            pos += 1
            continue
        for length in (2, 3):
            ai = body[pos:pos + length]
            if ai in FIXED or ai in VARIABLE:
                break
        else:
            # Unknown AI (length unknown): its data ends at the next FNC1; without one, stop.
            end = body.find(GS, pos)
            if end < 0:
                break
            pos = end
            continue
        pos += len(ai)
        if ai in FIXED:
            value = body[pos:pos + FIXED[ai]]
            if len(value) != FIXED[ai] or not value.isdigit():
                return elements or None
            pos += FIXED[ai]
        else:
            end = body.find(GS, pos)
            end = len(body) if end < 0 else end
            value = body[pos:end]
            pos = end
        elements.append((ai, value))
    return elements or None


def _split_prefix(raw):
    for prefix in PREFIXES:
        if raw.startswith(prefix):
            return raw[len(prefix):], True
    return raw, False


def is_gs1_shaped(parsed):
    """The scanned code is a GS1 element string (symbology prefix, FNC1, bracket notation or
    a GTIN read from it), even if it carried no lot."""
    body, prefixed = _split_prefix(parsed["raw"] or "")
    return bool(parsed["gtin"] or prefixed or GS in body or _elements_brackets(body))


def parse(code):
    """GS1 content of a scanned code -> {gtin, lot, expiry (date), serial, raw}."""
    raw = (code or "").strip()
    body, prefixed = _split_prefix(raw)
    elements = _elements_brackets(body)
    if elements is None:
        # Without a symbology prefix or an FNC1, only "01 + 14 digits + more" is taken as GS1,
        # so plain EAN-13 / GTIN-14 codes stay plain codes.
        looks_gs1 = prefixed or GS in body or (body.startswith("01") and len(body) > 16
                                               and body[2:16].isdigit())
        elements = _elements_raw(body) if looks_gs1 else None
    if not elements:
        return _empty(raw)
    values = dict(elements)
    gtin = values.get("01")
    if not (gtin and len(gtin) == 14 and gtin.isdigit()):
        gtin = None
    result = _empty(raw)
    result.update({
        "gtin": gtin,
        "lot": values.get("10") or None,
        "expiry": _expiry(values.get("17")),
        "serial": values.get("21") or None,
    })
    if not any(result[k] for k in ("gtin", "lot", "expiry", "serial")):
        return _empty(raw)
    return result


def lookup_codes(gtin, raw):
    """Codes a product may be stored under: the GTIN-14 and its EAN-13 form (one leading 0
    stripped), and vice versa for a plain 13/14-digit code; other codes as they are."""
    codes = []
    if gtin:
        codes += [gtin] + ([gtin[1:]] if gtin.startswith("0") else [])
    if raw and raw not in codes:
        codes.append(raw)
        if not gtin and raw.isdigit():
            if len(raw) == 13:
                codes.append("0" + raw)
            elif len(raw) == 14 and raw.startswith("0"):
                codes.append(raw[1:])
    return codes
