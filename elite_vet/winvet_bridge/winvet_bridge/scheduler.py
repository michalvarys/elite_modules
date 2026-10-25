"""WinVet calendar (KALENDAR_NEW) -> contract v4 ``calendar_events``.

WinVet's calendar is a DevExpress ExpressScheduler storage. The bridge reads it read-only like
every other entity; this module only decodes the two binary columns and expands recurrences.

Binary columns (BLOB SUB_TYPE 1 with the WIN1250 character set, so the driver hands them over as
text decoded from WIN1250; :func:`blob_bytes` turns that text back into the stored bytes):

``ZDROJ_INFO`` - the event's resource(s) = KALENDAR_NEW_KALENDAR ids, a streamed Delphi variant::

    uint32  0x0000200C (variant array of variants)
    uint32  total length of the blob in bytes
    value   one resource, or a list:  0x01, <count as int value>, <count values>

    value tags (Delphi TValueType): 0x02 int8, 0x03 int16, 0x04 int32, 0x13 int64,
    0x06 string (uint8 length, ANSI), 0x0C long string (uint32 length, ANSI),
    0x12 wide string (uint32 length in characters, UTF-16LE), 0x14 UTF-8 string (uint32 length).

    Seen on the analysis copy: one id as a wide string ("5"), a list of one to three wide strings
    ("5", "4") and once the resource *name* ("ORDINACE 1") instead of the id. Numeric strings are
    ids; other strings are resolved by the calendar name (case-insensitive) by the caller.

``OPAKOVANI_INFO`` - recurrence of a pattern (TYP 1), the packed record
``TcxSchedulerEventRecurrenceInfoData`` (little endian, 40 bytes)::

    int32  Count            > 0 number of occurrences, 0 = until Finish, -1 = no end
    int32  DayNumber        day of month / week number (monthly, yearly; 5 = last)
    uint8  DayType          0 day, 1 every day, 2 weekday, 3 weekend day, 4..10 Sunday..Saturday
    double Finish           TDateTime (days since 1899-12-30) of the last day, -1 = none
    uint8  OccurDays        weekly: set of days, bit 0 Sunday .. bit 6 Saturday
    int32  Periodicity      every n days / weeks / months; yearly: the month
    uint8  Recurrence       0 daily, 1 weekly, 2 monthly, 3 yearly
    double Start            (not used, 0)
    int32  YearPeriodicity  yearly: every n years
    uint8  (unknown, 1)
    int32  DismissDate      (reminders, not used)

Rows of a recurring event: TYP 1 = the pattern (its ZACATEK/KONEC are the first occurrence),
TYP 3 = a changed occurrence and TYP 4 = a deleted occurrence; both point to the pattern with
ID_PREDEK and to the occurrence with OPAKOVANI_INDEX (0 = the first occurrence), like DevExpress
itself matches them. A changed occurrence is a complete row with its own time and data.

All-day events (VOLBY bit 0) are stored from 23:00 of the previous day to 23:00 of the last day;
they are normalised to local midnights (rounded to the nearest midnight), see :func:`day_bounds`.
Recurrences of all-day events are expanded on those real days (a weekly "Wednesday" all-day pattern
is stored from Tuesday 23:00; its deleted occurrences are stored the same way).
"""

from __future__ import annotations

import datetime as _dt
import logging
import struct
from dataclasses import dataclass
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .normalize import format_date, format_datetime, norm_value, read_blob, to_int, to_ref

log = logging.getLogger(__name__)

DELPHI_EPOCH = _dt.datetime(1899, 12, 30)
#: Safety net for broken patterns: never generate more occurrences than this per pattern.
MAX_OCCURRENCES = 5000
TYP_NORMAL, TYP_PATTERN, TYP_CHANGED, TYP_DELETED = 0, 1, 3, 4
OPTION_ALL_DAY = 1

DAILY, WEEKLY, MONTHLY, YEARLY = 0, 1, 2, 3
DAY_DAY, DAY_EVERY_DAY, DAY_WEEKDAY, DAY_WEEKEND = 0, 1, 2, 3
# DayType 4..10 = Sunday..Saturday; Python weekday(): Monday 0 .. Sunday 6.
DAYTYPE_WEEKDAY = {4 + i: (i - 1) % 7 for i in range(7)}


class CalendarDecodeError(ValueError):
    """A binary calendar column could not be decoded."""


# --------------------------------------------------------------------------- binary helpers


def blob_bytes(value) -> Optional[bytes]:
    """Bytes of a WIN1250 text BLOB as stored (the driver decodes it to ``str``)."""
    value = read_blob(value)
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    out = bytearray()
    for char in str(value):
        try:
            out += char.encode("cp1250")
        except UnicodeEncodeError:
            # the five bytes undefined in WIN1250 come back as the same code point
            if ord(char) < 256:
                out.append(ord(char))
            else:
                raise CalendarDecodeError("character outside WIN1250 in a binary column") from None
    return bytes(out)


class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise CalendarDecodeError("unexpected end of data")
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def unpack(self, fmt: str):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))[0]


def _read_value(reader: _Reader, depth: int = 0):
    if depth > 4:
        raise CalendarDecodeError("nesting too deep")
    tag = reader.unpack("B")
    if tag == 0x00:
        return None
    if tag == 0x01:  # list: count, then the values
        count = _read_value(reader, depth + 1)
        if not isinstance(count, int) or not 0 <= count <= 100:
            raise CalendarDecodeError("bad list length")
        return [_read_value(reader, depth + 1) for _ in range(count)]
    if tag == 0x02:
        return reader.unpack("b")
    if tag == 0x03:
        return reader.unpack("h")
    if tag == 0x04:
        return reader.unpack("i")
    if tag == 0x13:
        return reader.unpack("q")
    if tag == 0x06:
        return reader.take(reader.unpack("B")).decode("cp1250", errors="replace")
    if tag == 0x0C:
        return reader.take(reader.unpack("I")).decode("cp1250", errors="replace")
    if tag == 0x12:
        return reader.take(2 * reader.unpack("I")).decode("utf-16-le", errors="replace")
    if tag == 0x14:
        return reader.take(reader.unpack("I")).decode("utf-8", errors="replace")
    raise CalendarDecodeError(f"unknown value tag 0x{tag:02x}")


def decode_resources(data: Optional[bytes]) -> List[str]:
    """ZDROJ_INFO -> list of resource values as strings (ids or names), in stored order."""
    if not data:
        return []
    reader = _Reader(data)
    reader.unpack("I")  # variant type, 0x200C
    total = reader.unpack("I")
    if total != len(data):
        raise CalendarDecodeError("length field does not match")
    value = _read_value(reader)
    values = value if isinstance(value, list) else [value]
    out = []
    for item in values:
        text = None if item is None else str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def resolve_resources(values: Sequence[str], names: Mapping[str, int]) -> List[int]:
    """Resource values -> KALENDAR_NEW_KALENDAR ids; names via ``names`` (lower-case name -> id)."""
    out = []
    for value in values:
        ref = int(value) if value.lstrip("-").isdigit() else names.get(value.strip().lower())
        if ref and ref > 0 and ref not in out:
            out.append(ref)
    return out


def delphi_datetime(value: float) -> Optional[_dt.datetime]:
    if value is None or value < 0:
        return None
    try:
        return DELPHI_EPOCH + _dt.timedelta(days=value)
    except OverflowError:
        return None


def nearest_midnight(value: _dt.datetime) -> _dt.date:
    """23:00 of the previous day and 00:00 both mean the day itself (all-day storage)."""
    return (value + _dt.timedelta(hours=12)).date()


@dataclass(frozen=True)
class Recurrence:
    count: int
    day_number: int
    day_type: int
    finish: Optional[_dt.date]
    occur_days: int
    periodicity: int
    kind: int
    year_periodicity: int


def decode_recurrence(data: Optional[bytes]) -> Recurrence:
    if not data or len(data) < 35:
        raise CalendarDecodeError("recurrence info too short")
    r = _Reader(data)
    count = r.unpack("i")
    day_number = r.unpack("i")
    day_type = r.unpack("B")
    finish = delphi_datetime(r.unpack("d"))
    occur_days = r.unpack("B")
    periodicity = r.unpack("i")
    kind = r.unpack("B")
    r.unpack("d")  # Start, unused
    year_periodicity = r.unpack("i")
    return Recurrence(
        count=count,
        day_number=day_number,
        day_type=day_type,
        finish=nearest_midnight(finish) if finish else None,
        occur_days=occur_days,
        periodicity=max(1, periodicity),
        kind=kind,
        year_periodicity=max(1, year_periodicity),
    )


# --------------------------------------------------------------------------- recurrence expansion


def _days_in_month(year: int, month: int) -> int:
    nxt = _dt.date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


def _nth_day_in_month(year: int, month: int, day_type: int, number: int) -> Optional[_dt.date]:
    """Monthly / yearly by DayType: the n-th (5 = last) matching day of the month."""
    last = _days_in_month(year, month)
    if day_type == DAY_DAY:
        return _dt.date(year, month, min(max(1, number), last))
    days = [_dt.date(year, month, d) for d in range(1, last + 1)]
    if day_type == DAY_EVERY_DAY:
        matching = days
    elif day_type == DAY_WEEKDAY:
        matching = [d for d in days if d.weekday() < 5]
    elif day_type == DAY_WEEKEND:
        matching = [d for d in days if d.weekday() >= 5]
    elif day_type in DAYTYPE_WEEKDAY:
        matching = [d for d in days if d.weekday() == DAYTYPE_WEEKDAY[day_type]]
    else:
        return None
    if not matching:
        return None
    if number >= 5 or number > len(matching):
        return matching[-1]
    return matching[max(1, number) - 1]


def _candidate_dates(rule: Recurrence, first: _dt.date) -> Iterator[_dt.date]:
    """All dates the rule produces from ``first`` on (ascending, possibly endless)."""
    if rule.kind == DAILY:
        if rule.day_type == DAY_WEEKDAY:
            day = first
            while True:
                if day.weekday() < 5:
                    yield day
                day += _dt.timedelta(days=1)
        else:
            day = first
            while True:
                yield day
                day += _dt.timedelta(days=rule.periodicity)
    elif rule.kind == WEEKLY:
        # bit 0 Sunday .. bit 6 Saturday -> Python weekdays; weeks start on Monday (Czech locale)
        weekdays = sorted((bit - 1) % 7 for bit in range(7) if rule.occur_days & (1 << bit))
        if not weekdays:
            weekdays = [first.weekday()]
        monday = first - _dt.timedelta(days=first.weekday())
        while True:
            for weekday in weekdays:
                day = monday + _dt.timedelta(days=weekday)
                if day >= first:
                    yield day
            monday += _dt.timedelta(weeks=rule.periodicity)
    elif rule.kind in (MONTHLY, YEARLY):
        if rule.kind == MONTHLY:
            year, month, step = first.year, first.month, rule.periodicity
        else:
            year, month, step = first.year, min(12, max(1, rule.periodicity)), 12 * rule.year_periodicity
        while year <= 9999:
            day = _nth_day_in_month(year, month, rule.day_type, rule.day_number)
            if day is not None and day >= first:
                yield day
            month += step
            year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    else:
        raise CalendarDecodeError(f"unknown recurrence type {rule.kind}")


def occurrences(rule: Recurrence, first: _dt.date, until: _dt.date, min_index: int = -1) -> List[Tuple[int, _dt.date]]:
    """(index, date) of the occurrences up to ``until`` (inclusive) or the rule's end.

    ``min_index``: keep generating at least up to this index even after ``until`` (to find the
    original date of a changed occurrence that moved into the window).
    """
    out = []
    for index, day in enumerate(_candidate_dates(rule, first)):
        if index >= MAX_OCCURRENCES:
            break
        if rule.count > 0 and index >= rule.count:
            break
        if rule.count == 0 and rule.finish and day > rule.finish:
            break
        if day > until and index > min_index:
            break
        out.append((index, day))
    return out


# --------------------------------------------------------------------------- events


@dataclass
class Window:
    start: _dt.date  # first day (inclusive)
    end: _dt.date  # last day (inclusive)

    @property
    def start_dt(self) -> _dt.datetime:
        return _dt.datetime.combine(self.start, _dt.time())

    @property
    def end_dt(self) -> _dt.datetime:  # exclusive
        return _dt.datetime.combine(self.end + _dt.timedelta(days=1), _dt.time())

    def overlaps(self, start: _dt.datetime, end: _dt.datetime) -> bool:
        return start < self.end_dt and end > self.start_dt

    def payload(self) -> dict:
        return {"from": format_date(self.start), "to": format_date(self.end)}


def make_window(today: _dt.date, days_back: int, days_ahead: int) -> Window:
    return Window(today - _dt.timedelta(days=max(0, days_back)), today + _dt.timedelta(days=max(0, days_ahead)))


def _as_datetime(value) -> Optional[_dt.datetime]:
    value = read_blob(value)
    if isinstance(value, _dt.datetime):
        return value.replace(microsecond=0, tzinfo=None)
    if isinstance(value, _dt.date):
        return _dt.datetime.combine(value, _dt.time())
    return None


def day_bounds(start: _dt.datetime, end: _dt.datetime) -> Tuple[_dt.datetime, _dt.datetime]:
    """All-day event -> [first midnight, last midnight) in local time (at least one day)."""
    first = nearest_midnight(start)
    last = nearest_midnight(end)
    if last <= first:
        last = first + _dt.timedelta(days=1)
    return _dt.datetime.combine(first, _dt.time()), _dt.datetime.combine(last, _dt.time())


def _modified(row: Mapping) -> Optional[str]:
    stamp = _as_datetime(row.get("POSLEDNI_MODIFIKACE_TS"))
    if stamp is None:
        stamp = _as_datetime(row.get("POSLEDNI_MODIFIKACE"))
    return format_datetime(stamp) if stamp else None


class EventBuilder:
    """Turns the read KALENDAR_NEW rows into ``calendar_events`` records for one window."""

    def __init__(self, window: Window, resource_names: Optional[Mapping[str, int]] = None):
        self.window = window
        self.resource_names = {k.lower(): v for k, v in (resource_names or {}).items()}
        #: counts of problems (no record data) for the log
        self.problems: Dict[str, int] = {}

    def _problem(self, what: str) -> None:
        self.problems[what] = self.problems.get(what, 0) + 1

    def _resources(self, row: Mapping) -> List[int]:
        try:
            return resolve_resources(decode_resources(blob_bytes(row.get("ZDROJ_INFO"))), self.resource_names)
        except CalendarDecodeError:
            self._problem("resource info not decodable")
            return []

    def record(self, row: Mapping, key: str, start: _dt.datetime, end: _dt.datetime,
               recurring: bool, occurrence_date: Optional[_dt.date] = None) -> dict:
        all_day = bool((to_int(row.get("VOLBY")) or 0) & OPTION_ALL_DAY)
        if all_day:
            start, end = day_bounds(start, end)
        return {
            "key": key,
            "id": to_int(row["ID_KALENDAR"]),
            "pattern_id": to_ref(row.get("ID_PREDEK")) if to_int(row.get("TYP")) == TYP_CHANGED
            else (to_int(row["ID_KALENDAR"]) if recurring else None),
            "recurring": recurring,
            "occurrence_date": format_date(occurrence_date) if occurrence_date else None,
            "start": format_datetime(start),
            "end": format_datetime(end),
            "all_day": all_day,
            "resource_ids": self._resources(row),
            "activity_id": to_ref(row.get("ID_ORD_CINNOST")),
            "owner_id": to_ref(row.get("ID_PARTNER")),
            "patient_id": to_ref(row.get("ID_PACIENT")),
            "title": norm_value(row.get("TITULEK")),
            "busy_status": to_int(row.get("STAV")),
            "done": str(norm_value(row.get("VYRIZENO")) or "").upper() == "A",
            "modified": _modified(row),
        }

    def _in_window(self, row: Mapping, start: _dt.datetime, end: _dt.datetime) -> bool:
        if (to_int(row.get("VOLBY")) or 0) & OPTION_ALL_DAY:
            start, end = day_bounds(start, end)
        return self.window.overlaps(start, end)

    def build(self, rows: Sequence[Mapping]) -> List[dict]:
        out: Dict[str, dict] = {}
        patterns, exceptions, plain = {}, {}, []
        for row in rows:
            typ = to_int(row.get("TYP")) or 0
            if typ == TYP_PATTERN:
                patterns[to_int(row["ID_KALENDAR"])] = row
            elif typ in (TYP_CHANGED, TYP_DELETED):
                exceptions.setdefault(to_ref(row.get("ID_PREDEK")), []).append(row)
            elif typ == TYP_NORMAL:
                plain.append(row)
            else:
                self._problem(f"unknown event type {typ}")

        for row in plain:
            start, end = _as_datetime(row.get("ZACATEK")), _as_datetime(row.get("KONEC"))
            if start is None or end is None:
                self._problem("event without time")
                continue
            if end <= start:
                end = start + _dt.timedelta(minutes=1)
            if self._in_window(row, start, end):
                key = str(to_int(row["ID_KALENDAR"]))
                out[key] = self.record(row, key, start, end, recurring=False)

        for parent, rows_ in exceptions.items():
            if parent not in patterns:
                self._problem("occurrence without pattern")
                for row in rows_:
                    if to_int(row.get("TYP")) == TYP_CHANGED:
                        self._changed(row, parent, None, out)
        for pattern_id, pattern in patterns.items():
            self._expand(pattern_id, pattern, exceptions.get(pattern_id, []), out)
        return sorted(out.values(), key=lambda r: (r["start"], r["key"]))

    def _changed(self, row: Mapping, parent: Optional[int], original: Optional[_dt.date], out: Dict[str, dict]):
        start, end = _as_datetime(row.get("ZACATEK")), _as_datetime(row.get("KONEC"))
        if start is None or end is None:
            self._problem("event without time")
            return
        if end <= start:
            end = start + _dt.timedelta(minutes=1)
        if not self._in_window(row, start, end):
            return
        day = original or start.date()
        key = f"{parent or to_int(row['ID_KALENDAR'])}-{day.strftime('%Y%m%d')}"
        out[key] = self.record(row, key, start, end, recurring=True, occurrence_date=day)

    def _expand(self, pattern_id: int, pattern: Mapping, exceptions: Sequence[Mapping], out: Dict[str, dict]):
        start, end = _as_datetime(pattern.get("ZACATEK")), _as_datetime(pattern.get("KONEC"))
        if start is None or end is None:
            self._problem("event without time")
            return
        if (to_int(pattern.get("VOLBY")) or 0) & OPTION_ALL_DAY:
            # all-day: the rule works on the real days (stored from 23:00 of the previous day)
            start, end = day_bounds(start, end)
        duration = max(end - start, _dt.timedelta(minutes=1))
        try:
            rule = decode_recurrence(blob_bytes(pattern.get("OPAKOVANI_INFO")))
        except CalendarDecodeError:
            self._problem("recurrence info not decodable")
            return
        by_index = {}
        for row in exceptions:
            index = to_int(row.get("OPAKOVANI_INDEX"))
            if index is not None and index >= 0:
                by_index[index] = row
        until = self.window.end + _dt.timedelta(days=1)  # an occurrence of the evening before may reach in
        try:
            dates = occurrences(rule, start.date(), until, max(by_index, default=-1))
        except CalendarDecodeError:
            self._problem("unknown recurrence type")
            return
        dates_by_index = dict(dates)
        for index, day in dates:
            if index in by_index:
                continue  # changed (emitted below) or deleted occurrence
            occ_start = _dt.datetime.combine(day, start.time())
            occ_end = occ_start + duration
            if self._in_window(pattern, occ_start, occ_end):
                key = f"{pattern_id}-{day.strftime('%Y%m%d')}"
                out[key] = self.record(pattern, key, occ_start, occ_end, recurring=True, occurrence_date=day)
        for index, row in by_index.items():
            if to_int(row.get("TYP")) == TYP_CHANGED:
                self._changed(row, pattern_id, dates_by_index.get(index), out)


# --------------------------------------------------------------------------- small entities


def delphi_color(value) -> Optional[str]:
    """Delphi TColor (0x00BBGGRR) -> '#rrggbb'; system/default colours -> None."""
    value = to_int(value)
    if value is None or value < 0 or value > 0xFFFFFF:
        return None
    red, green, blue = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
    return f"#{red:02x}{green:02x}{blue:02x}"
